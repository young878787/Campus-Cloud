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

// Status represents the current state of the tunnel manager.
type Status struct {
	Running bool           `json:"running"`
	Tunnels []TunnelStatus `json:"tunnels"`
	Error   string         `json:"error,omitempty"`
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

// Start downloads frpc if needed, writes visitor config, and starts the frpc process.
func (m *Manager) Start(config *api.TunnelConfig) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.cmd != nil {
		return fmt.Errorf("tunnel already running")
	}

	if err := os.MkdirAll(m.dataDir, 0o755); err != nil {
		return fmt.Errorf("create data dir: %w", err)
	}

	// Ensure frpc binary exists
	frpcPath := filepath.Join(m.dataDir, frpcBinaryName())
	if _, err := os.Stat(frpcPath); os.IsNotExist(err) {
		m.status.Error = "正在下載 frpc..."
		if err := downloadFrpc(frpcPath); err != nil {
			m.status.Error = "下載 frpc 失敗: " + err.Error()
			return fmt.Errorf("download frpc: %w", err)
		}
	}
	m.frpcPath = frpcPath

	// Write visitor config (pre-built by backend, just write to disk)
	configPath := filepath.Join(m.dataDir, "frpc-visitor.toml")
	if err := os.WriteFile(configPath, []byte(config.FrpcConfig), 0o600); err != nil {
		m.status.Error = "寫入設定失敗: " + err.Error()
		return fmt.Errorf("write config: %w", err)
	}
	m.configPath = configPath

	// Start frpc
	ctx, cancel := context.WithCancel(context.Background())
	m.cancel = cancel

	cmd := exec.CommandContext(ctx, frpcPath, "-c", configPath)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Start(); err != nil {
		cancel()
		m.status.Error = "啟動 frpc 失敗: " + err.Error()
		return fmt.Errorf("start frpc: %w", err)
	}
	m.cmd = cmd

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
	m.status = Status{Running: true, Tunnels: tunnels}

	// Monitor process in background
	go func() {
		_ = cmd.Wait()
		m.mu.Lock()
		m.status.Running = false
		m.cmd = nil
		m.cancel = nil
		m.mu.Unlock()
	}()

	return nil
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
}

func frpcBinaryName() string {
	if runtime.GOOS == "windows" {
		return "frpc.exe"
	}
	return "frpc"
}

func downloadFrpc(destPath string) error {
	osName := runtime.GOOS
	arch := runtime.GOARCH
	// frpc doesn't provide 386 builds; use amd64 which works on 64-bit Windows
	if arch == "386" {
		arch = "amd64"
	}

	var archiveURL string
	var ext string
	if osName == "windows" {
		ext = "zip"
	} else {
		ext = "tar.gz"
	}
	archiveURL = fmt.Sprintf(
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

	// Save to temp file
	tmpFile, err := os.CreateTemp(filepath.Dir(destPath), "frpc-download-*")
	if err != nil {
		return err
	}
	defer os.Remove(tmpFile.Name())

	if _, err := io.Copy(tmpFile, resp.Body); err != nil {
		tmpFile.Close()
		return err
	}
	tmpFile.Close()

	// Extract frpc binary
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
