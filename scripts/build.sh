#!/usr/bin/env bash
# 中文说明：
# 本地 Linux 与 GitHub Actions 使用同一套构建步骤。
# 不存在的软件包自动从 .config 中忽略，不参与编译；
# 真正的源码、内核、编译、下载错误仍然返回失败。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TREE="${OPENWRT_DIR:-$ROOT/openwrt}"
BOARD="${BOARD:-h68k}"
JOBS="${JOBS:-2}"
LOGS="$(dirname "$TREE")/build-logs"

mkdir -p "$LOGS"
cd "$TREE"


# ============================================================
# 自动清理 .config 中不存在的软件包
#
# 逻辑：
#   1. 读取当前 .config 中所有 CONFIG_PACKAGE_xxx=y/m
#   2. 使用 OpenWrt 的实际 menuconfig/package 数据判断
#   3. 不存在的软件包自动取消
#   4. 存在的软件包保持原配置
#
# 注意：
#   - 不删除源码
#   - 不修改 feeds
#   - 不修改任何 Makefile
#   - 不伪造软件包
#   - 仅处理 CONFIG_PACKAGE_*
# ============================================================
ignore_missing_packages() {
    local report="$LOGS/missing-packages.log"
    local before="$LOGS/config-before-missing-filter"
    local after="$LOGS/config-after-missing-filter"

    echo "============================================================"
    echo "检查 .config 中不存在的软件包"
    echo "============================================================"

    cp .config "$before"

    : > "$report"

    # --------------------------------------------------------
    # 先让 OpenWrt 根据当前 feeds / package Makefile
    # 生成完整的 package 配置数据库。
    # --------------------------------------------------------
    make defconfig >/dev/null 2>&1 || true

    # --------------------------------------------------------
    # 通过 scripts/config 检查 CONFIG_PACKAGE_*。
    #
    # OpenWrt 自带 scripts/config：
    #   - --get-val 可以读取配置
    #   - --disable 可以安全取消配置
    #
    # 这里只处理当前 .config 中已经存在的 CONFIG_PACKAGE_*。
    # --------------------------------------------------------
    if [ ! -x ./scripts/config ]; then
        echo "错误：找不到 OpenWrt scripts/config。" >&2
        return 1
    fi

    while IFS= read -r line; do
        case "$line" in
            CONFIG_PACKAGE_*=y|CONFIG_PACKAGE_*=m)
                package_config="${line%%=*}"
                package_value="${line#*=}"

                package="${package_config#CONFIG_PACKAGE_}"

                # OpenWrt 配置中的特殊转义名称恢复。
                package="$(printf '%s' "$package" | sed 's/@@/@/g')"

                # ------------------------------------------------
                # 使用 OpenWrt 自身生成的 .config / tmp 信息
                # 判断 package 是否存在。
                #
                # package Makefile 存在时：
                #   package/feeds/*/<pkg>/Makefile
                #   package/*/<pkg>/Makefile
                #
                # 同时检查 package 名称，避免简单 grep
                # 把依赖关系误判成软件包存在。
                # ------------------------------------------------
                found=0

                # 官方 / 本地 package
                if find package \
                    -type f \
                    -name Makefile \
                    -path "*/${package}/Makefile" \
                    -print -quit 2>/dev/null | grep -q .; then
                    found=1
                fi

                # feeds package
                if [ "$found" -eq 0 ] && find feeds \
                    -type f \
                    -name Makefile \
                    -path "*/${package}/Makefile" \
                    -print -quit 2>/dev/null | grep -q .; then
                    found=1
                fi

                # ------------------------------------------------
                # 进一步使用 package metadata 判断。
                # 这一步用于处理某些 package 目录名称和
                # CONFIG_PACKAGE 名称不完全一致的情况。
                # ------------------------------------------------
                if [ "$found" -eq 0 ]; then
                    if grep -Rqs \
                        --include='Makefile' \
                        -E "^PKG_NAME[[:space:]]*:=[[:space:]]*${package}$|^PKG_NAME[[:space:]]*=[[:space:]]*${package}$" \
                        package feeds 2>/dev/null; then
                        found=1
                    fi
                fi

                if [ "$found" -eq 0 ]; then
                    printf '%s\n' "$package" >> "$report"

                    echo "忽略不存在的软件包：$package"

                    # 自动取消配置。
                    ./scripts/config --disable "$package_config" 2>/dev/null || true
                fi
                ;;
        esac
    done < <(grep '^CONFIG_PACKAGE_.*=\(y\|m\)$' .config || true)

    # --------------------------------------------------------
    # 重新生成 .config。
    #
    # 被取消的软件包会变成：
    # CONFIG_PACKAGE_xxx is not set
    #
    # 其他存在的软件包保持原状态。
    # --------------------------------------------------------
    make defconfig

    cp .config "$after"

    echo
    echo "============================================================"
    echo "不存在的软件包处理完成"
    echo "============================================================"

    if [ -s "$report" ]; then
        echo "以下软件包不存在，已自动忽略："
        cat "$report"
    else
        echo "没有发现需要忽略的软件包。"
    fi

    echo
}


case "${1:-all}" in

    prepare)

        # ========================================================
        # 先注册设备，避免 feeds 刷新配置时丢失自定义目标。
        # ========================================================
        python3 "$ROOT/scripts/manage.py" adapt "$TREE"

        bash "$ROOT/diy1.sh" 2>&1 | tee "$LOGS/feeds.log"

        bash "$ROOT/diy2.sh" "$BOARD" 2>&1 | tee "$LOGS/adapt.log"


        # ========================================================
        # 第一次 defconfig
        # ========================================================
        make defconfig 2>&1 | tee "$LOGS/defconfig-initial.log"


        # ========================================================
        # 关键修正：
        #
        # 对 .config 中已经不存在的第三方 / iStoreOS 插件
        # 自动取消 CONFIG_PACKAGE_*。
        #
        # 不存在：
        #   CONFIG_PACKAGE_xxx=y
        #
        # 自动变成：
        #   # CONFIG_PACKAGE_xxx is not set
        #
        # 不再因为这些插件不存在而停止构建。
        # ========================================================
        ignore_missing_packages 2>&1 | tee "$LOGS/missing-packages.log"


        # ========================================================
        # 再做一次最终 defconfig
        #
        # 确保取消不存在软件包以后：
        #   - 依赖重新计算
        #   - .config 一致
        #   - OpenWrt 最终配置有效
        # ========================================================
        make defconfig 2>&1 | tee "$LOGS/defconfig-final.log"


        # ========================================================
        # 审计
        # ========================================================
        python3 "$ROOT/scripts/manage.py" audit "$TREE"


        # ========================================================
        # 记录官方 feeds 的实际版本；
        # 不修改 kmod 源到其他内核 ABI。
        # ========================================================
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

        # ========================================================
        # 下载失败可重试；
        # 上游校验和错误由 make 原样报告，不修改校验和。
        # ========================================================
        for attempt in 1 2 3; do

            if make download -j"$JOBS" V=s \
                2>&1 | tee "$LOGS/download-$attempt.log"; then
                exit 0
            fi

        done

        exit 1

        ;;


    compile)

        # ========================================================
        # 先实际应用完整内核补丁队列并确认 BBRv3，
        # 失败不能跳过。
        # ========================================================
        make target/linux/prepare -j1 V=s \
            2>&1 | tee "$LOGS/kernel-prepare.log"

        python3 "$ROOT/scripts/bbr3.py" verify "$TREE"


        # ========================================================
        # 并行编译。
        #
        # 如果并行编译失败，则继续进行单线程复查。
        # ========================================================
        if make -j"$JOBS" V=s \
            2>&1 | tee "$LOGS/compile-parallel.log"; then

            exit 0

        fi


        # ========================================================
        # 单线程复查。
        #
        # 真正的编译错误仍然返回失败。
        # ========================================================
        make -j1 V=s \
            2>&1 | tee "$LOGS/compile-serial.log"

        ;;


    collect)

        python3 "$ROOT/scripts/collect.py" \
            "$TREE" \
            "$BOARD" \
            "$ROOT/firmware"

        ;;


    all)

        for step in prepare download compile collect; do
            bash "$ROOT/scripts/build.sh" "$step"
        done

        ;;


    *)

        echo '用法：build.sh [prepare|download|compile|collect|all]'
        exit 2

        ;;

esac
