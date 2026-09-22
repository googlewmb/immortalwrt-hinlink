#!/usr/bin/env bash
# 中文说明：只管理插件来源；官方 feeds 排在前面，第三方不覆盖官方包。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
test -f include/toplevel.mk || { echo '请在 ImmortalWrt 源码根目录运行'; exit 1; }
python3 "$ROOT/scripts/manage.py" feeds "$PWD"
# feeds install 不使用 -f，官方仓库已有的 Passwall/OpenClash 直接使用官方版本。
./scripts/feeds update -a
./scripts/feeds install -a
