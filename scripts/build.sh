#!/usr/bin/env bash
# 中文说明：本地 Linux 与 GitHub Actions 使用同一套构建步骤，错误必须返回失败。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TREE="${OPENWRT_DIR:-$ROOT/openwrt}"
BOARD="${BOARD:-h68k}"
JOBS="${JOBS:-2}"
LOGS="$(dirname "$TREE")/build-logs"
mkdir -p "$LOGS"
cd "$TREE"
case "${1:-all}" in
  prepare)
    bash "$ROOT/diy1.sh" 2>&1 | tee "$LOGS/feeds.log"
    bash "$ROOT/diy2.sh" "$BOARD" 2>&1 | tee "$LOGS/adapt.log"
    make defconfig 2>&1 | tee "$LOGS/defconfig.log"
    python3 "$ROOT/scripts/manage.py" audit "$TREE"
    # 记录官方 feeds 的实际版本；不修改 kmod 源到其他内核 ABI。
    {
      printf '# 中文说明：本次实际使用的源码与 feeds 提交。\n'
      git rev-parse HEAD
      for feed in feeds/*; do
        [ -d "$feed/.git" ] || continue
        printf '%s ' "$feed"
        git -C "$feed" rev-parse HEAD
      done
    } >"$LOGS/source-revisions.txt"
    ;;
  download)
    # 下载失败可重试；上游校验和错误由 make 原样报告，不修改校验和。
    for attempt in 1 2 3; do
      if make download -j"$JOBS" V=s 2>&1 | tee "$LOGS/download-$attempt.log"; then exit 0; fi
    done
    exit 1
    ;;
  compile)
    # 先实际应用完整内核补丁队列并确认 BBRv3，失败不能跳过。
    make target/linux/prepare -j1 V=s 2>&1 | tee "$LOGS/kernel-prepare.log"
    python3 "$ROOT/scripts/bbr3.py" verify "$TREE"
    # 并行失败后单线程复查，保存两份日志，便于定位真实错误。
    if make -j"$JOBS" V=s 2>&1 | tee "$LOGS/compile-parallel.log"; then exit 0; fi
    make -j1 V=s 2>&1 | tee "$LOGS/compile-serial.log"
    ;;
  collect)
    python3 "$ROOT/scripts/collect.py" "$TREE" "$BOARD" "$ROOT/firmware"
    ;;
  all)
    for step in prepare download compile collect; do bash "$ROOT/scripts/build.sh" "$step"; done
    ;;
  *) echo '用法：build.sh [prepare|download|compile|collect|all]'; exit 2 ;;
esac
