package main

import (
	"context"
	"embed"
	"encoding/json"
	"fmt"
	"io/fs"
	"log"
	"net"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"runtime"
	"syscall"

	"campus-cloud-connect/internal/api"
	"campus-cloud-connect/internal/auth"
	"campus-cloud-connect/internal/config"
	"campus-cloud-connect/internal/tunnel"
)

//go:embed web
var webFS embed.FS

var (
	cfg       *config.Config
	apiClient *api.Client
	tunnelMgr *tunnel.Manager
)

func main() {
	var err error
	cfg, err = config.Load()
	if err != nil {
		log.Fatalf("載入 config.json 失敗: %v", err)
	}

	apiClient = api.NewClient(cfg.BackendURL)
	tunnelMgr = tunnel.NewManager()

	mux := http.NewServeMux()

	// Serve embedded web UI
	webContent, _ := fs.Sub(webFS, "web")
	mux.Handle("/", http.FileServer(http.FS(webContent)))

	// API endpoints for the browser UI
	mux.HandleFunc("/api/state", handleState)
	mux.HandleFunc("/api/login", handleLogin)
	mux.HandleFunc("/api/logout", handleLogout)
	mux.HandleFunc("/api/resources", handleResources)
	mux.HandleFunc("/api/tunnel/start", handleTunnelStart)
	mux.HandleFunc("/api/tunnel/stop", handleTunnelStop)
	mux.HandleFunc("/api/tunnel/status", handleTunnelStatus)
	mux.HandleFunc("/api/shutdown", handleShutdown)

	// Find a free port
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		log.Fatalf("無法啟動伺服器: %v", err)
	}

	addr := listener.Addr().String()
	url := "http://" + addr
	fmt.Printf("Campus Cloud Connect 啟動於 %s\n", url)

	// Open browser
	openBrowser(url)

	// Handle graceful shutdown
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	srv := &http.Server{Handler: mux}
	go func() {
		<-sigCh
		tunnelMgr.Stop()
		_ = srv.Shutdown(context.Background())
	}()

	if err := srv.Serve(listener); err != http.ErrServerClosed {
		log.Fatalf("伺服器錯誤: %v", err)
	}
}

func openBrowser(url string) {
	switch runtime.GOOS {
	case "windows":
		_ = exec.Command("rundll32", "url.dll,FileProtocolHandler", url).Start()
	case "darwin":
		_ = exec.Command("open", url).Start()
	default:
		_ = exec.Command("xdg-open", url).Start()
	}
}

func jsonResponse(w http.ResponseWriter, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(v)
}

func jsonError(w http.ResponseWriter, msg string, code int) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(map[string]string{"error": msg})
}

func handleState(w http.ResponseWriter, r *http.Request) {
	tunnelStatus := tunnelMgr.GetStatus()
	jsonResponse(w, map[string]interface{}{
		"logged_in": apiClient.HasToken(),
		"tunnel":    tunnelStatus,
	})
}

func handleLogin(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
		jsonError(w, "method not allowed", 405)
		return
	}

	// Start device auth flow in background (opens browser to backend login page)
	go func() {
		token, err := auth.LoginWithDeviceCode(cfg.BackendURL)
		if err != nil {
			log.Printf("登入失敗: %v", err)
			return
		}
		apiClient.SetToken(token)
		log.Println("登入成功")
	}()

	jsonResponse(w, map[string]string{"status": "login_started"})
}

func handleLogout(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
		jsonError(w, "method not allowed", 405)
		return
	}
	tunnelMgr.Stop()
	apiClient.SetToken("")
	jsonResponse(w, map[string]string{"status": "logged_out"})
}

func handleResources(w http.ResponseWriter, r *http.Request) {
	if !apiClient.HasToken() {
		jsonError(w, "not logged in", 401)
		return
	}
	resources, err := apiClient.MyResources(r.Context())
	if err != nil {
		jsonError(w, "取得資源失敗: "+err.Error(), 500)
		return
	}
	jsonResponse(w, resources)
}

func handleTunnelStart(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
		jsonError(w, "method not allowed", 405)
		return
	}
	if !apiClient.HasToken() {
		jsonError(w, "not logged in", 401)
		return
	}

	// Get tunnel config from backend
	tunnelConfig, err := apiClient.GetTunnelConfig(r.Context())
	if err != nil {
		jsonError(w, "取得隧道設定失敗: "+err.Error(), 500)
		return
	}

	if len(tunnelConfig.Tunnels) == 0 {
		jsonError(w, "沒有可用的隧道", 404)
		return
	}

	if err := tunnelMgr.Start(tunnelConfig); err != nil {
		jsonError(w, "啟動隧道失敗: "+err.Error(), 500)
		return
	}

	jsonResponse(w, tunnelMgr.GetStatus())
}

func handleTunnelStop(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
		jsonError(w, "method not allowed", 405)
		return
	}
	tunnelMgr.Stop()
	jsonResponse(w, map[string]string{"status": "stopped"})
}

func handleTunnelStatus(w http.ResponseWriter, r *http.Request) {
	jsonResponse(w, tunnelMgr.GetStatus())
}

func handleShutdown(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
		jsonError(w, "method not allowed", 405)
		return
	}
	tunnelMgr.Stop()
	jsonResponse(w, map[string]string{"status": "shutting_down"})
	go func() {
		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh)
		p, _ := os.FindProcess(os.Getpid())
		_ = p.Signal(syscall.SIGTERM)
	}()
}
