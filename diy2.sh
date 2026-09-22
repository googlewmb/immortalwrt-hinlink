#!/usr/bin/env bash
# 中文说明：添加设备支持、默认无线及连接数；不下载第三方插件。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOARD="${1:-h68k}"
python3 "$ROOT/scripts/manage.py" adapt "$PWD"
python3 "$ROOT/scripts/manage.py" config "$PWD" "$BOARD"
install -Dm644 "$ROOT/runtime/99-h6xk.conf" files/etc/sysctl.d/99-h6xk.conf
install -Dm755 "$ROOT/runtime/99-h6xk-wireless" files/etc/uci-defaults/99-h6xk-wireless
