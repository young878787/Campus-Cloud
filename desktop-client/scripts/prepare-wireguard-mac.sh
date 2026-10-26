#!/usr/bin/env bash
# Build or assemble universal (x86_64 + arm64) WireGuard binaries for macOS.

set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "prepare-wireguard-mac.sh must be run on macOS (Darwin)." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
VENDOR_DIR="$PROJECT_ROOT/vendor/wireguard-mac"

WG_TOOLS_TAG="v1.0.20260223"
WG_GO_TAG="0.0.20250522"

WG_BIN="$VENDOR_DIR/wg"
WG_GO_ARM64="$VENDOR_DIR/wireguard-go-arm64"
WG_GO_AMD64="$VENDOR_DIR/wireguard-go-amd64"
WG_GO_UNIVERSAL="$VENDOR_DIR/wireguard-go"
HELPER_SCRIPT="$VENDOR_DIR/skylab-wg-helper.sh"

mkdir -p "$VENDOR_DIR"
chmod 0755 "$HELPER_SCRIPT"

has_arch() {
  local file="$1"
  local arch="$2"
  [[ -f "$file" ]] && lipo -archs "$file" 2>/dev/null | grep -qw "$arch"
}

need_build=0
if [[ "${1:-}" == "--rebuild" ]]; then
  need_build=1
fi
if ! has_arch "$WG_BIN" "x86_64" || ! has_arch "$WG_BIN" "arm64"; then
  need_build=1
fi
if ! has_arch "$WG_GO_ARM64" "arm64" || ! has_arch "$WG_GO_AMD64" "x86_64"; then
  need_build=1
fi

if [[ "$need_build" -eq 1 ]]; then
  echo "Building macOS WireGuard binaries (universal x86_64 + arm64)..."
  BUILD_TMP="$(mktemp -d "${TMPDIR:-/tmp}/skylab-wg-mac-build.XXXXXX")"
  trap 'rm -rf "$BUILD_TMP"' EXIT

  git clone --depth 1 --branch "$WG_TOOLS_TAG" https://github.com/WireGuard/wireguard-tools.git "$BUILD_TMP/wireguard-tools"
  CFLAGS="-O2 -arch x86_64 -arch arm64" LDFLAGS="-arch x86_64 -arch arm64" \
    make -C "$BUILD_TMP/wireguard-tools/src" clean wg
  cp -f "$BUILD_TMP/wireguard-tools/src/wg" "$WG_BIN"
  chmod 0755 "$WG_BIN"

  git clone --depth 1 --branch "$WG_GO_TAG" https://github.com/WireGuard/wireguard-go.git "$BUILD_TMP/wireguard-go"
  (
    cd "$BUILD_TMP/wireguard-go"
    CGO_ENABLED=0 GOOS=darwin GOARCH=arm64 go build -trimpath -ldflags="-s -w" -o "$WG_GO_ARM64"
    CGO_ENABLED=0 GOOS=darwin GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o "$WG_GO_AMD64"
  )
  chmod 0755 "$WG_GO_ARM64" "$WG_GO_AMD64"
fi

lipo -create -output "$WG_GO_UNIVERSAL" "$WG_GO_AMD64" "$WG_GO_ARM64"
chmod 0755 "$WG_GO_UNIVERSAL" "$WG_BIN"

if command -v codesign >/dev/null 2>&1; then
  codesign --force --sign - "$WG_BIN" >/dev/null 2>&1 || true
  codesign --force --sign - "$WG_GO_UNIVERSAL" >/dev/null 2>&1 || true
fi

echo "Verified macOS WireGuard universal binaries:"
echo "  wg           : $(lipo -archs "$WG_BIN")"
echo "  wireguard-go : $(lipo -archs "$WG_GO_UNIVERSAL")"
