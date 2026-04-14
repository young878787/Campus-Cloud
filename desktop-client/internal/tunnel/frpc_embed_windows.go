//go:build windows

package tunnel

import (
	_ "embed"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// embeddedFrpc is the frpc.exe binary compiled into the desktop client,
// so we don't need to download it at runtime (and trigger SmartScreen /
// Windows Defender SmartScreen blocks).
//
//go:embed frpc.exe
var embeddedFrpc []byte

// installFrpc writes the embedded frpc binary to destPath. If Windows
// Defender (or another AV) blocks the write as "virus or unwanted software",
// we try to add a Defender exclusion (via UAC) and retry once.
func (m *Manager) installFrpc(destPath string) error {
	// Best-effort progress: treat the install as "download complete" so the UI
	// shows a full progress bar briefly even though there's no real download.
	m.mu.Lock()
	m.status.DownloadTotal = int64(len(embeddedFrpc))
	m.status.DownloadDone = int64(len(embeddedFrpc))
	m.mu.Unlock()

	if err := writeFileAtomic(destPath, embeddedFrpc); err == nil {
		return nil
	} else if !isAVBlockedError(err) {
		return err
	}

	// Defender blocked the initial write — try to add an exclusion via UAC,
	// then retry.
	m.setPhase(PhaseExcluding, "請在 UAC 視窗按「是」以加入 Defender 排除…")
	if exclErr := ensureDefenderExclusion(filepath.Dir(destPath)); exclErr != nil {
		return fmt.Errorf(
			"Defender 攔截了 frpc；加入排除也失敗: %v。"+
				"請手動以系統管理員執行：Add-MpPreference -ExclusionPath '%s'",
			exclErr, filepath.Dir(destPath),
		)
	}
	m.setPhase(PhaseStarting, "重試安裝 frpc…")
	return writeFileAtomic(destPath, embeddedFrpc)
}

// writeFileAtomic writes data to a temp file in the same directory as destPath,
// then renames it into place. Avoids leaving a partial file if Defender zaps
// the write mid-flight.
func writeFileAtomic(destPath string, data []byte) error {
	dir := filepath.Dir(destPath)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	tmp, err := os.CreateTemp(dir, "frpc-install-*")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	if _, err := tmp.Write(data); err != nil {
		tmp.Close()
		os.Remove(tmpName)
		return err
	}
	if err := tmp.Close(); err != nil {
		os.Remove(tmpName)
		return err
	}
	// Rename over the destination (replaces if it exists).
	if err := os.Rename(tmpName, destPath); err != nil {
		os.Remove(tmpName)
		return err
	}
	return nil
}

// isAVBlockedError returns true if err looks like a Windows "file contains a
// virus" block from Defender / SmartScreen.
func isAVBlockedError(err error) bool {
	if err == nil {
		return false
	}
	msg := strings.ToLower(err.Error())
	return strings.Contains(msg, "virus") ||
		strings.Contains(msg, "unwanted software")
}
