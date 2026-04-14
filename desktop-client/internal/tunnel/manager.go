package tunnel

import (
	"archive/tar"
	"archive/zip"
	"compress/gzip"
	"context"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"

	"campus-cloud-connect/internal/api"
)

const frpcVersion = "0.61.1"

// Phase values exposed to the UI so it can render spinners / progress bars.
const (
	PhaseIdle        = "idle"
	PhasePreparing   = "preparing"   // creating dirs, fetching config
	PhaseExcluding   = "excluding"   // asking for UAC to add Defender exclusion
	PhaseDownloading = "downloading" // downloading frpc archive
	PhaseExtracting  = "extracting"  // extracting frpc binary from archive
	PhaseStarting    = "starting"    // spawning frpc process
	PhaseRunning     = "running"
	PhaseStopping    = "stopping"
	PhaseError       = "error"
)

// Status represents the current state of the tunnel manager.
type Status struct {
	Running bool           `json:"running"`
	Tunnels []TunnelStatus `json:"tunnels"`
	Error   string         `json:"error,omitempty"`
	// Phase is a machine-readable state (see Phase* constants).
	Phase string `json:"phase,omitempty"`
	// Message is a human-readable status string to display next to a spinner.
	Message string `json:"message,omitempty"`
	// DownloadTotal/DownloadDone track bytes for the frpc download progress bar.
	// Zero when not downloading or when total size is unknown.
	DownloadTotal int64 `json:"download_total,omitempty"`
	DownloadDone  int64 `json:"download_done,omitempty"`
}

type TunnelStatus struct {
	ProxyName string `json:"proxy_name"`
	Service   string `json:"service"`
	VMID      int    `json:"vmid"`
	VMName    string `json:"vm_name"`
	LocalPort int    `json:"local_port"`
}

type Manager struct {
	mu         sync.Mutex
	cmd        *exec.Cmd
	cancel     context.CancelFunc
	status     Status
	dataDir    string
	frpcPath   string
	configPath string
}

func NewManager() *Manager {
	// Use a directory next to the executable
	exePath, _ := os.Executable()
	dataDir := filepath.Join(filepath.Dir(exePath), "frpc-data")
	return &Manager{dataDir: dataDir}
}

func (m *Manager) GetStatus() Status {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.status
}

// setPhase updates Phase + Message atomically.
func (m *Manager) setPhase(phase, message string) {
	m.mu.Lock()
	m.status.Phase = phase
	m.status.Message = message
	m.mu.Unlock()
}

// setError transitions to the error phase and stores the message.
func (m *Manager) setError(message string) {
	m.mu.Lock()
	m.status.Phase = PhaseError
	m.status.Running = false
	m.status.Error = message
	m.status.Message = message
	m.mu.Unlock()
}

// isBusy reports whether a start is already in progress or frpc is running.
// Caller must hold m.mu.
func (m *Manager) isBusy() bool {
	if m.cmd != nil {
		return true
	}
	switch m.status.Phase {
	case PhasePreparing, PhaseExcluding, PhaseDownloading, PhaseExtracting, PhaseStarting:
		return true
	}
	return false
}

// Start kicks off the tunnel startup pipeline asynchronously and returns
// immediately. The UI should poll GetStatus() to observe phase transitions
// (preparing → excluding → downloading → extracting → starting → running).
func (m *Manager) Start(config *api.TunnelConfig) error {
	m.mu.Lock()
	if m.isBusy() {
		m.mu.Unlock()
		return fmt.Errorf("tunnel already running or starting")
	}
	// Reset status to preparing so the UI immediately shows a spinner.
	m.status = Status{Phase: PhasePreparing, Message: "準備中..."}
	m.mu.Unlock()

	go m.startAsync(config)
	return nil
}

func (m *Manager) startAsync(config *api.TunnelConfig) {
	if err := os.MkdirAll(m.dataDir, 0o755); err != nil {
		m.setError("建立資料夾失敗: " + err.Error())
		return
	}

	// Ensure frpc binary exists. On Windows the binary is embedded in this
	// executable (see frpc_embed_windows.go), so this is just a local file
	// write — no network download, no SmartScreen, no Defender URL block.
	// On non-Windows it still falls back to a runtime download.
	frpcPath := filepath.Join(m.dataDir, frpcBinaryName())
	if _, err := os.Stat(frpcPath); os.IsNotExist(err) {
		m.setPhase(PhaseDownloading, "正在安裝 frpc...")
		if err := m.installFrpc(frpcPath); err != nil {
			m.setError("安裝 frpc 失敗: " + err.Error())
			return
		}
	}
	m.frpcPath = frpcPath

	// Write visitor config (pre-built by backend, just write to disk)
	m.setPhase(PhaseStarting, "正在啟動 frpc...")
	configPath := filepath.Join(m.dataDir, "frpc-visitor.toml")
	if err := os.WriteFile(configPath, []byte(config.FrpcConfig), 0o600); err != nil {
		m.setError("寫入設定失敗: " + err.Error())
		return
	}
	m.configPath = configPath

	// Start frpc
	ctx, cancel := context.WithCancel(context.Background())
	cmd := exec.CommandContext(ctx, frpcPath, "-c", configPath)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Start(); err != nil {
		cancel()
		m.setError("啟動 frpc 失敗: " + err.Error())
		return
	}

	// Build tunnel status list
	tunnels := make([]TunnelStatus, 0, len(config.Tunnels))
	for _, t := range config.Tunnels {
		tunnels = append(tunnels, TunnelStatus{
			ProxyName: t.ProxyName,
			Service:   t.Service,
			VMID:      t.VMID,
			VMName:    t.VMName,
			LocalPort: t.VisitorPort,
		})
	}

	m.mu.Lock()
	m.cmd = cmd
	m.cancel = cancel
	m.status = Status{
		Running: true,
		Phase:   PhaseRunning,
		Message: "已連線",
		Tunnels: tunnels,
	}
	m.mu.Unlock()

	// Monitor process in background
	go func() {
		_ = cmd.Wait()
		m.mu.Lock()
		m.status.Running = false
		m.status.Phase = PhaseIdle
		m.status.Message = ""
		m.cmd = nil
		m.cancel = nil
		m.mu.Unlock()
	}()
}

func (m *Manager) Stop() {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.cancel != nil {
		m.cancel()
		m.cancel = nil
	}
	m.cmd = nil
	m.status.Running = false
	m.status.Tunnels = nil
	m.status.Phase = PhaseIdle
	m.status.Message = ""
	m.status.DownloadTotal = 0
	m.status.DownloadDone = 0
}

func frpcBinaryName() string {
	if runtime.GOOS == "windows" {
		return "frpc.exe"
	}
	return "frpc"
}

// progressWriter wraps an io.Writer to report bytes-written progress via a callback.
type progressWriter struct {
	w      io.Writer
	onCopy func(n int64)
}

func (pw *progressWriter) Write(p []byte) (int, error) {
	n, err := pw.w.Write(p)
	if n > 0 && pw.onCopy != nil {
		pw.onCopy(int64(n))
	}
	return n, err
}

// downloadFrpcWithProgress downloads and extracts frpc, updating m.status.DownloadDone
// as bytes are copied so the UI can render a progress bar.
func (m *Manager) downloadFrpcWithProgress(destPath string) error {
	osName := runtime.GOOS
	arch := runtime.GOARCH
	// frpc doesn't provide 386 builds; use amd64 which works on 64-bit Windows
	if arch == "386" {
		arch = "amd64"
	}

	var ext string
	if osName == "windows" {
		ext = "zip"
	} else {
		ext = "tar.gz"
	}
	archiveURL := fmt.Sprintf(
		"https://github.com/fatedier/frp/releases/download/v%s/frp_%s_%s_%s.%s",
		frpcVersion, frpcVersion, osName, arch, ext,
	)

	resp, err := http.Get(archiveURL)
	if err != nil {
		return fmt.Errorf("download: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return fmt.Errorf("download HTTP %d from %s", resp.StatusCode, archiveURL)
	}

	// Seed progress with Content-Length so the UI can show a determinate bar.
	m.mu.Lock()
	m.status.DownloadTotal = resp.ContentLength
	m.status.DownloadDone = 0
	m.mu.Unlock()

	// Save to temp file with progress tracking
	tmpFile, err := os.CreateTemp(filepath.Dir(destPath), "frpc-download-*")
	if err != nil {
		return err
	}
	defer os.Remove(tmpFile.Name())

	pw := &progressWriter{
		w: tmpFile,
		onCopy: func(n int64) {
			m.mu.Lock()
			m.status.DownloadDone += n
			m.mu.Unlock()
		},
	}
	if _, err := io.Copy(pw, resp.Body); err != nil {
		tmpFile.Close()
		return err
	}
	tmpFile.Close()

	// Extracting is fast — show it as its own phase so the UI updates message.
	m.setPhase(PhaseExtracting, "解壓縮中...")

	if ext == "zip" {
		return extractFromZip(tmpFile.Name(), destPath)
	}
	return extractFromTarGz(tmpFile.Name(), destPath)
}

func extractFromZip(zipPath, destPath string) error {
	r, err := zip.OpenReader(zipPath)
	if err != nil {
		return err
	}
	defer r.Close()

	target := frpcBinaryName()
	for _, f := range r.File {
		// The archive has a directory like frp_0.61.1_windows_amd64/frpc.exe
		if strings.HasSuffix(f.Name, "/"+target) || f.Name == target {
			rc, err := f.Open()
			if err != nil {
				return err
			}
			defer rc.Close()
			out, err := os.OpenFile(destPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o755)
			if err != nil {
				return err
			}
			defer out.Close()
			_, err = io.Copy(out, rc)
			return err
		}
	}
	return fmt.Errorf("frpc binary not found in zip")
}

func extractFromTarGz(tgzPath, destPath string) error {
	f, err := os.Open(tgzPath)
	if err != nil {
		return err
	}
	defer f.Close()

	gz, err := gzip.NewReader(f)
	if err != nil {
		return err
	}
	defer gz.Close()

	tr := tar.NewReader(gz)
	target := frpcBinaryName()
	for {
		hdr, err := tr.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return err
		}
		if strings.HasSuffix(hdr.Name, "/"+target) || hdr.Name == target {
			out, err := os.OpenFile(destPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o755)
			if err != nil {
				return err
			}
			defer out.Close()
			_, err = io.Copy(out, tr)
			return err
		}
	}
	return fmt.Errorf("frpc binary not found in tar.gz")
}
