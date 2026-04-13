package api

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

type Client struct {
	BaseURL    string
	HTTPClient *http.Client
	token      string
}

func NewClient(baseURL string) *Client {
	return &Client{
		BaseURL:    baseURL,
		HTTPClient: &http.Client{},
	}
}

func (c *Client) SetToken(token string) { c.token = token }
func (c *Client) HasToken() bool        { return c.token != "" }

type Resource struct {
	VMID            int    `json:"vmid"`
	Name            string `json:"name"`
	Status          string `json:"status"`
	Node            string `json:"node"`
	Type            string `json:"type"`
	IPAddress       string `json:"ip_address"`
	EnvironmentType string `json:"environment_type"`
}

type TunnelConfig struct {
	FrpcConfig string       `json:"frpc_config"`
	Tunnels    []TunnelInfo `json:"tunnels"`
}

type TunnelInfo struct {
	ProxyName   string `json:"proxy_name"`
	Service     string `json:"service"`
	VMID        int    `json:"vmid"`
	VisitorPort int    `json:"visitor_port"`
	VMName      string `json:"vm_name"`
}

func (c *Client) LoginGoogle(ctx context.Context, idToken string) error {
	body, _ := json.Marshal(map[string]string{"id_token": idToken})
	req, _ := http.NewRequestWithContext(ctx, "POST", c.BaseURL+"/api/v1/login/google", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != 200 {
		return fmt.Errorf("login failed (%d): %s", resp.StatusCode, string(data))
	}
	var result struct {
		AccessToken string `json:"access_token"`
	}
	if err := json.Unmarshal(data, &result); err != nil {
		return err
	}
	c.token = result.AccessToken
	return nil
}

func (c *Client) MyResources(ctx context.Context) ([]Resource, error) {
	req, _ := http.NewRequestWithContext(ctx, "GET", c.BaseURL+"/api/v1/resources/my", nil)
	req.Header.Set("Authorization", "Bearer "+c.token)
	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("resources failed (%d): %s", resp.StatusCode, string(data))
	}
	var resources []Resource
	if err := json.Unmarshal(data, &resources); err != nil {
		return nil, err
	}
	return resources, nil
}

func (c *Client) GetTunnelConfig(ctx context.Context) (*TunnelConfig, error) {
	req, _ := http.NewRequestWithContext(ctx, "GET", c.BaseURL+"/api/v1/tunnel/my-config", nil)
	req.Header.Set("Authorization", "Bearer "+c.token)
	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("tunnel config failed (%d): %s", resp.StatusCode, string(data))
	}
	var config TunnelConfig
	if err := json.Unmarshal(data, &config); err != nil {
		return nil, err
	}
	return &config, nil
}
