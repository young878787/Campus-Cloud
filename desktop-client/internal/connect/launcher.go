package connect

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
)

func LaunchRDP(host string) error {
	if runtime.GOOS != "windows" {
		return fmt.Errorf("RDP launch only supported on Windows")
	}
	return exec.Command("mstsc", "/v:"+host).Start()
}

func LaunchSSH(user, host string) error {
	sshPath := findWindowsSSH()
	if sshPath == "" {
		return fmt.Errorf("找不到 ssh.exe，請確認已安裝 OpenSSH Client：\n設定 → 應用程式 → 選用功能 → 新增功能 → OpenSSH 用戶端")
	}
	cmd := exec.Command(sshPath, fmt.Sprintf("%s@%s", user, host))
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Start()
}

func findWindowsSSH() string {
	// Check common Windows paths
	candidates := []string{
		filepath.Join(os.Getenv("SystemRoot"), "System32", "OpenSSH", "ssh.exe"),
		`C:\Windows\System32\OpenSSH\ssh.exe`,
	}
	for _, p := range candidates {
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	// Fallback to PATH
	if p, err := exec.LookPath("ssh"); err == nil {
		return p
	}
	return ""
}
