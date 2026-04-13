package config

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

type Config struct {
	BackendURL string `json:"backend_url"`
}

func Load() (*Config, error) {
	// Try next to the executable first
	exePath, err := os.Executable()
	if err == nil {
		p := filepath.Join(filepath.Dir(exePath), "config.json")
		if c, err := loadFrom(p); err == nil {
			return c, nil
		}
	}

	// Fallback to CWD
	if c, err := loadFrom("config.json"); err == nil {
		return c, nil
	}

	return nil, fmt.Errorf("config.json not found next to exe or in CWD")
}

func loadFrom(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var c Config
	if err := json.Unmarshal(data, &c); err != nil {
		return nil, err
	}
	return &c, nil
}
