//go:build windows

package tunnel

import (
	"fmt"
	"log"
	"os/exec"
	"strings"
	"syscall"
	"unsafe"
)

// ensureDefenderExclusion adds frpcDataDir to Windows Defender's exclusion list
// if it isn't already excluded. Triggers a UAC prompt on first call.
//
// Errors are non-fatal — the caller should still attempt the download.
// If the user denies UAC or Defender blocks the download anyway, the caller
// can fall back to a manual-instructions message.
func ensureDefenderExclusion(frpcDataDir string) error {
	// Skip if the folder is already in the exclusion list (no UAC needed)
	if isAlreadyExcluded(frpcDataDir) {
		return nil
	}

	if err := addExclusionElevated(frpcDataDir); err != nil {
		return err
	}

	// Verify it was actually added (user may have cancelled UAC)
	if !isAlreadyExcluded(frpcDataDir) {
		return fmt.Errorf("Defender 排除未加入（可能已取消 UAC）")
	}
	return nil
}

// isAlreadyExcluded queries Defender's current exclusion list (doesn't need admin).
// Matches exact path, case-insensitive. Also returns true if Defender isn't
// running (e.g. third-party AV) — no point harassing the user with UAC.
func isAlreadyExcluded(path string) bool {
	// IMPORTANT: force UTF-8 output. PowerShell's default redirected-stdout
	// encoding is the OEM code page (e.g. CP950 on zh-TW, CP936 on zh-CN),
	// which would mangle any non-ASCII path like `C:\Users\陳洋\...`. Without
	// this, the bytes we read back can't match our UTF-8 target, so we'd
	// mistakenly think the exclusion wasn't added even when it was.
	cmd := exec.Command("powershell", "-NoProfile", "-Command",
		`[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;`+
			`(Get-MpPreference).ExclusionPath`)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	out, err := cmd.Output()
	if err != nil {
		return true
	}

	target := strings.ToLower(strings.TrimRight(path, `\/`))
	for _, line := range strings.Split(string(out), "\n") {
		line = strings.ToLower(strings.TrimSpace(strings.TrimRight(line, `\/`)))
		if line == target {
			return true
		}
	}
	return false
}

// ─── ShellExecuteEx via direct syscall ───────────────────────────────────────
// We declare the struct + proc ourselves because golang.org/x/sys/windows
// doesn't expose SHELLEXECUTEINFO / ShellExecuteEx in all versions.

const (
	_SEE_MASK_NOCLOSEPROCESS = 0x00000040
	_SW_HIDE                 = 0
	_INFINITE                = 0xFFFFFFFF
	_WAIT_TIMEOUT            = 0x00000102
)

type shellExecuteInfoW struct {
	cbSize         uint32
	fMask          uint32
	hwnd           syscall.Handle
	lpVerb         *uint16
	lpFile         *uint16
	lpParameters   *uint16
	lpDirectory    *uint16
	nShow          int32
	hInstApp       syscall.Handle
	lpIDList       uintptr
	lpClass        *uint16
	hkeyClass      syscall.Handle
	dwHotKey       uint32
	hIconOrMonitor syscall.Handle
	hProcess       syscall.Handle
}

var (
	modShell32              = syscall.NewLazyDLL("shell32.dll")
	modKernel32             = syscall.NewLazyDLL("kernel32.dll")
	procShellExecuteExW     = modShell32.NewProc("ShellExecuteExW")
	procWaitForSingleObject = modKernel32.NewProc("WaitForSingleObject")
	procCloseHandle         = modKernel32.NewProc("CloseHandle")
)

// addExclusionElevated spawns an elevated PowerShell (triggers UAC) to add
// the exclusion, and waits for it to finish.
func addExclusionElevated(path string) error {
	// Escape single quotes for PowerShell string literal
	escaped := strings.ReplaceAll(path, "'", "''")
	psCmd := fmt.Sprintf("Add-MpPreference -ExclusionPath '%s'", escaped)

	verb, err := syscall.UTF16PtrFromString("runas")
	if err != nil {
		return err
	}
	file, err := syscall.UTF16PtrFromString("powershell.exe")
	if err != nil {
		return err
	}
	args, err := syscall.UTF16PtrFromString(
		fmt.Sprintf(`-NoProfile -WindowStyle Hidden -Command "%s"`, psCmd),
	)
	if err != nil {
		return err
	}

	info := shellExecuteInfoW{
		fMask:        _SEE_MASK_NOCLOSEPROCESS,
		lpVerb:       verb,
		lpFile:       file,
		lpParameters: args,
		nShow:        _SW_HIDE,
	}
	info.cbSize = uint32(unsafe.Sizeof(info))

	ret, _, callErr := procShellExecuteExW.Call(uintptr(unsafe.Pointer(&info)))
	if ret == 0 {
		return fmt.Errorf("ShellExecuteEx failed: %v", callErr)
	}
	if info.hProcess == 0 {
		return fmt.Errorf("no process handle returned")
	}
	defer procCloseHandle.Call(uintptr(info.hProcess))

	// Wait up to 60 seconds for the elevated PowerShell to finish.
	const timeoutMs = 60 * 1000
	waitRet, _, _ := procWaitForSingleObject.Call(uintptr(info.hProcess), uintptr(timeoutMs))
	if waitRet == _WAIT_TIMEOUT {
		log.Printf("UAC wait timed out after %dms", timeoutMs)
		return fmt.Errorf("UAC 請求逾時")
	}
	return nil
}
