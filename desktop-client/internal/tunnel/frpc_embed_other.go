//go:build !windows

package tunnel

// installFrpc on non-Windows falls back to the runtime download path
// (downloadFrpcWithProgress). The desktop client is distributed as a
// Windows binary in practice, so this is mostly a compile-time stub.
func (m *Manager) installFrpc(destPath string) error {
	return m.downloadFrpcWithProgress(destPath)
}
