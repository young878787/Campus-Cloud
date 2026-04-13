package auth

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// DeviceCodeResponse is the backend's response to POST /auth/device-code.
type DeviceCodeResponse struct {
	DeviceCode string `json:"device_code"`
	LoginURL   string `json:"login_url"`
	ExpiresIn  int    `json:"expires_in"`
}

// PollResponse is the backend's response to GET /auth/poll.
type PollResponse struct {
	Status      string `json:"status"`       // "pending" or "approved"
	AccessToken string `json:"access_token"` // set when status == "approved"
}

// LoginWithDeviceCode performs the device authorization flow:
//  1. Request a device code from the backend
//  2. Open the login page in the browser with the device code
//  3. Poll the backend until the user approves or timeout
//
// Returns the access token on success.
func LoginWithDeviceCode(backendURL string) (string, error) {
	// Step 1: Request device code
	resp, err := http.Post(backendURL+"/api/v1/desktop-client/auth/device-code", "application/json", nil)
	if err != nil {
		return "", fmt.Errorf("request device code: %w", err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != 200 {
		return "", fmt.Errorf("device code request failed (%d): %s", resp.StatusCode, string(body))
	}

	var dcResp DeviceCodeResponse
	if err := json.Unmarshal(body, &dcResp); err != nil {
		return "", fmt.Errorf("parse device code: %w", err)
	}

	// Step 2: Open browser to frontend login page (URL provided by backend)
	openBrowser(dcResp.LoginURL)

	// Step 3: Poll for approval
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(dcResp.ExpiresIn)*time.Second)
	defer cancel()

	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return "", fmt.Errorf("login timed out")
		case <-ticker.C:
			token, done, err := pollDeviceCode(backendURL, dcResp.DeviceCode)
			if err != nil {
				return "", err
			}
			if done {
				return token, nil
			}
		}
	}
}

func pollDeviceCode(backendURL, code string) (token string, done bool, err error) {
	resp, err := http.Get(backendURL + "/api/v1/desktop-client/auth/poll?code=" + code)
	if err != nil {
		return "", false, fmt.Errorf("poll: %w", err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode == 404 {
		return "", false, fmt.Errorf("device code expired or not found")
	}
	if resp.StatusCode != 200 {
		return "", false, fmt.Errorf("poll failed (%d): %s", resp.StatusCode, string(body))
	}

	var pollResp PollResponse
	if err := json.Unmarshal(body, &pollResp); err != nil {
		return "", false, fmt.Errorf("parse poll response: %w", err)
	}

	if pollResp.Status == "approved" && pollResp.AccessToken != "" {
		return pollResp.AccessToken, true, nil
	}

	return "", false, nil
}
