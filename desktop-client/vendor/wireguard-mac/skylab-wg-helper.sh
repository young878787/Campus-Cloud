#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-only
# SkyLab Connect privileged WireGuard helper for macOS (darwin)

set -eu

export LC_ALL=C
export PATH="/usr/sbin:/sbin:/usr/bin:/bin"

INSTALL_DIR="/Library/Application Support/SkyLabConnect/wireguard"
HELPER_BIN="$INSTALL_DIR/skylab-wg-helper"
WG_GO_BIN="$INSTALL_DIR/wireguard-go"
WG_BIN="$INSTALL_DIR/wg"
VERSION_FILE="$INSTALL_DIR/version"
SUDOERS_FILE="/etc/sudoers.d/skylab-connect"
RUN_DIR="/var/run/wireguard"
TUNNEL_NAME="SkyLab"
NAME_FILE="$RUN_DIR/$TUNNEL_NAME.name"

die() {
  echo "skylab-wg-helper: $*" >&2
  exit 1
}

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    die "This command must be run as root."
  fi
}

valid_ipv4_cidr() {
  echo "$1" | grep -Eq '^[0-9]{1,3}(\.[0-9]{1,3}){3}/[0-9]{1,2}$'
}

get_real_interface() {
  if [ ! -f "$NAME_FILE" ]; then
    return 1
  fi
  iface="$(cat "$NAME_FILE" 2>/dev/null || true)"
  case "$iface" in
    utun[0-9]*) ;;
    *) return 1 ;;
  esac
  if [ -x "$WG_BIN" ]; then
    "$WG_BIN" show interfaces >/dev/null 2>&1 || true
  fi
  if [ ! -S "$RUN_DIR/$iface.sock" ]; then
    return 1
  fi
  if ! /sbin/ifconfig "$iface" >/dev/null 2>&1; then
    return 1
  fi
  echo "$iface"
  return 0
}

delete_interface_routes() {
  iface="$1"
  if [ -z "$iface" ]; then
    return 0
  fi
  /usr/sbin/netstat -nr -f inet 2>/dev/null | awk -v target="$iface" '$4 == target || $6 == target { print $1 }' | while read -r dest; do
    if [ -n "$dest" ] && [ "$dest" != "Destination" ] && [ "$dest" != "default" ]; then
      /sbin/route -q -n delete -inet "$dest" -interface "$iface" >/dev/null 2>&1 || \
      /sbin/route -q -n delete -inet "$dest" >/dev/null 2>&1 || true
    fi
  done
}

cmd_down() {
  require_root
  if iface="$(get_real_interface)"; then
    delete_interface_routes "$iface"
    rm -f "$RUN_DIR/$iface.sock"
  elif [ -f "$NAME_FILE" ]; then
    stale_iface="$(cat "$NAME_FILE" 2>/dev/null || true)"
    case "$stale_iface" in
      utun[0-9]*)
        delete_interface_routes "$stale_iface"
        rm -f "$RUN_DIR/$stale_iface.sock"
        ;;
    esac
  fi
  rm -f "$NAME_FILE" "$RUN_DIR/$TUNNEL_NAME.wgconf"
}

cmd_up() {
  require_root
  config_file="${1:-}"
  if [ -z "$config_file" ] || [ ! -f "$config_file" ]; then
    die "Configuration file is missing."
  fi

  address_cidr="$(awk -F '=' '
    /^\[Interface\]/ { in_if=1; next }
    /^\[/ { in_if=0 }
    in_if && /^[[:space:]]*Address[[:space:]]*=/ {
      val=$2
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", val)
      print val
      exit
    }
  ' "$config_file")"

  if [ -z "$address_cidr" ] || ! valid_ipv4_cidr "$address_cidr"; then
    die "Invalid or missing Interface Address."
  fi
  address_ip="${address_cidr%%/*}"

  cmd_down

  mkdir -p "$RUN_DIR"
  chmod 0755 "$RUN_DIR"

  stripped_conf="$RUN_DIR/$TUNNEL_NAME.wgconf"
  rm -f "$stripped_conf"
  umask 077
  awk '
    /^\[Interface\]/ { print; next }
    /^\[Peer\]/ { print; next }
    /^[[:space:]]*(PrivateKey|PublicKey|Endpoint|AllowedIPs|PersistentKeepalive)[[:space:]]*=/ { print; next }
  ' "$config_file" > "$stripped_conf"

  trap 'rm -f "$stripped_conf"; cmd_down; exit 1' INT TERM EXIT

  WG_TUN_NAME_FILE="$NAME_FILE" "$WG_GO_BIN" utun
  chmod 0644 "$NAME_FILE"

  iface="$(get_real_interface)" || die "Failed to initialize WireGuard utun interface."

  "$WG_BIN" setconf "$iface" "$stripped_conf"
  rm -f "$stripped_conf"

  /sbin/ifconfig "$iface" inet "$address_cidr" "$address_ip" alias
  /sbin/ifconfig "$iface" mtu 1420
  /sbin/ifconfig "$iface" up

  "$WG_BIN" show "$iface" allowed-ips | awk '{
    for (i = 2; i <= NF; i++) {
      print $i
    }
  }' | while read -r cidr; do
    if [ -n "$cidr" ] && [ "$cidr" != "(none)" ] && [ "$cidr" != "0.0.0.0/0" ] && valid_ipv4_cidr "$cidr"; then
      /sbin/route -q -n add -inet "$cidr" -interface "$iface" >/dev/null 2>&1 || \
      /sbin/route -q -n change -inet "$cidr" -interface "$iface" >/dev/null 2>&1 || true
    fi
  done

  trap - INT TERM EXIT
  echo "$iface"
}

cmd_status() {
  require_root
  if iface="$(get_real_interface)"; then
    echo "running $iface"
  else
    echo "missing"
  fi
}

cmd_handshake() {
  require_root
  if iface="$(get_real_interface)"; then
    "$WG_BIN" show "$iface" latest-handshakes
  fi
}

cmd_install() {
  require_root
  src_dir="${1:-}"
  version_hash="${2:-}"
  if [ -z "$src_dir" ] || [ ! -d "$src_dir" ]; then
    die "Source directory not found."
  fi
  wg_go_src="$src_dir/wireguard-go"
  if [ ! -f "$wg_go_src" ]; then
    if [ "$(uname -m)" = "arm64" ] && [ -f "$src_dir/wireguard-go-arm64" ]; then
      wg_go_src="$src_dir/wireguard-go-arm64"
    elif [ -f "$src_dir/wireguard-go-amd64" ]; then
      wg_go_src="$src_dir/wireguard-go-amd64"
    fi
  fi
  if [ ! -f "$wg_go_src" ] || [ ! -f "$src_dir/wg" ] || [ ! -f "$src_dir/skylab-wg-helper.sh" ]; then
    die "Required WireGuard binaries are missing from source directory."
  fi
  case "$version_hash" in
    [a-f0-9]*) ;;
    *) die "Invalid version hash." ;;
  esac

  mkdir -p "$INSTALL_DIR"
  chown root:wheel "/Library/Application Support/SkyLabConnect" "$INSTALL_DIR"
  chmod 0755 "/Library/Application Support/SkyLabConnect" "$INSTALL_DIR"

  cp -f "$wg_go_src" "$WG_GO_BIN.tmp"
  cp -f "$src_dir/wg" "$WG_BIN.tmp"
  cp -f "$src_dir/skylab-wg-helper.sh" "$HELPER_BIN.tmp"
  printf '%s\n' "$version_hash" > "$VERSION_FILE.tmp"

  /usr/bin/xattr -c "$WG_GO_BIN.tmp" "$WG_BIN.tmp" "$HELPER_BIN.tmp" 2>/dev/null || true
  chown root:wheel "$WG_GO_BIN.tmp" "$WG_BIN.tmp" "$HELPER_BIN.tmp" "$VERSION_FILE.tmp"
  chmod 0755 "$WG_GO_BIN.tmp" "$WG_BIN.tmp" "$HELPER_BIN.tmp"
  chmod 0644 "$VERSION_FILE.tmp"

  mv -f "$WG_GO_BIN.tmp" "$WG_GO_BIN"
  mv -f "$WG_BIN.tmp" "$WG_BIN"
  mv -f "$HELPER_BIN.tmp" "$HELPER_BIN"
  mv -f "$VERSION_FILE.tmp" "$VERSION_FILE"

  mkdir -p /etc/sudoers.d
  sudoers_tmp="$SUDOERS_FILE.tmp"
  cat > "$sudoers_tmp" <<'EOF'
Defaults!/Library/Application\ Support/SkyLabConnect/wireguard/skylab-wg-helper !requiretty, env_reset
%staff ALL=(root) NOPASSWD: /Library/Application\ Support/SkyLabConnect/wireguard/skylab-wg-helper
EOF
  chown root:wheel "$sudoers_tmp"
  chmod 0440 "$sudoers_tmp"
  if ! /usr/sbin/visudo -cf "$sudoers_tmp" >/dev/null 2>&1; then
    rm -f "$sudoers_tmp"
    die "Generated sudoers rule failed visudo validation."
  fi
  mv -f "$sudoers_tmp" "$SUDOERS_FILE"
}

subcommand="${1:-}"
shift || true

case "$subcommand" in
  check)
    require_root
    echo "ok"
    ;;
  up)
    cmd_up "$@"
    ;;
  down)
    cmd_down
    ;;
  status)
    cmd_status
    ;;
  handshake)
    cmd_handshake
    ;;
  install)
    cmd_install "$@"
    ;;
  *)
    die "Unknown subcommand: $subcommand"
    ;;
esac
