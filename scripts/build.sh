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
#   2. 使用当前 package / feeds 实际 Makefile 判断
#   3. 不存在的软件包自动取消
#   4. 存在的软件包保持原配置
#
# 注意：
#   - 不删除源码
#   - 不修改 feeds
#   - 不修改任何 Makefile
#   - 不伪造软件包
#   - 仅处理 CONFIG_PACKAGE_*
#   - 缺失软件包只 WARNING，不阻止构建
# ============================================================
ignore_missing_packages() {
    local report="$LOGS/missing-packages.log"
    local before="$LOGS/config-before-missing-filter"
    local after="$LOGS/config-after-missing-filter"
    local defconfig_log="$LOGS/defconfig-missing-filter.log"

    echo "============================================================"
    echo "检查 .config 中不存在的软件包"
    echo "============================================================"

    cp .config "$before"

    : > "$report"

    # --------------------------------------------------------
    # scripts/config 必须存在
    # --------------------------------------------------------
    if [ ! -x ./scripts/config ]; then
        echo "错误：找不到 OpenWrt scripts/config。" >&2
        return 1
    fi

    # --------------------------------------------------------
    # 第一次 defconfig。
    #
    # 旧配置中的不存在插件可能产生 WARNING，
    # 这里不能因此停止，后面会自动清理。
    # --------------------------------------------------------
    make defconfig >/dev/null 2>&1 || true

    # --------------------------------------------------------
    # 读取当前 .config 中所有 CONFIG_PACKAGE_xxx=y/m
    # --------------------------------------------------------
    while IFS= read -r line; do
        case "$line" in
            CONFIG_PACKAGE_*=y|CONFIG_PACKAGE_*=m)

                package_config="${line%%=*}"
                package_value="${line#*=}"
                package="${package_config#CONFIG_PACKAGE_}"

                # OpenWrt 配置中的特殊转义名称恢复。
                package="$(printf '%s' "$package" | sed 's/@@/@/g')"

                found=0

                # ------------------------------------------------
                # 官方 / 本地 package
                # ------------------------------------------------
                if find package \
                    -type f \
                    -name Makefile \
                    -path "*/${package}/Makefile" \
                    -print -quit 2>/dev/null | grep -q .; then
                    found=1
                fi

                # ------------------------------------------------
                # feeds package
                # ------------------------------------------------
                if [ "$found" -eq 0 ] && [ -d feeds ]; then
                    if find feeds \
                        -type f \
                        -name Makefile \
                        -path "*/${package}/Makefile" \
                        -print -quit 2>/dev/null | grep -q .; then
                        found=1
                    fi
                fi

                # ------------------------------------------------
                # 通过 PKG_NAME 再检查一次。
                # ------------------------------------------------
                if [ "$found" -eq 0 ]; then
                    if grep -Rqs \
                        --include='Makefile' \
                        -E "^PKG_NAME[[:space:]]*:=[[:space:]]*${package}$|^PKG_NAME[[:space:]]*=[[:space:]]*${package}$" \
                        package feeds 2>/dev/null; then
                        found=1
                    fi
                fi

                # ------------------------------------------------
                # 软件包不存在：
                # 自动取消 CONFIG_PACKAGE_xxx
                # ------------------------------------------------
                if [ "$found" -eq 0 ]; then
                    printf '%s\n' "$package" >> "$report"

                    echo "WARNING: 不存在的软件包，自动忽略：$package"

                    ./scripts/config --disable "$package_config" \
                        2>/dev/null || true
                fi

                ;;
        esac
    done < <(grep '^CONFIG_PACKAGE_.*=\(y\|m\)$' .config || true)


    # ========================================================
    # 清理后重新生成 .config
    #
    # 缺失插件不再作为失败条件。
    # ========================================================
    if ! make defconfig >"$defconfig_log" 2>&1; then

        # ----------------------------------------------------
        # 再检查一次是否还有 CONFIG_PACKAGE_xxx=y/m
        # 指向不存在的软件包。
        # ----------------------------------------------------
        while IFS= read -r line; do
            case "$line" in
                CONFIG_PACKAGE_*=y|CONFIG_PACKAGE_*=m)

                    package_config="${line%%=*}"
                    package="${package_config#CONFIG_PACKAGE_}"
                    package="$(printf '%s' "$package" | sed 's/@@/@/g')"

                    found=0

                    if find package \
                        -type f \
                        -name Makefile \
                        -path "*/${package}/Makefile" \
                        -print -quit 2>/dev/null | grep -q .; then
                        found=1
                    fi

                    if [ "$found" -eq 0 ] && [ -d feeds ]; then
                        if find feeds \
                            -type f \
                            -name Makefile \
                            -path "*/${package}/Makefile" \
                            -print -quit 2>/dev/null | grep -q .; then
                            found=1
                        fi
                    fi

                    if [ "$found" -eq 0 ]; then
                        echo "WARNING: 不存在的软件包，自动忽略：$package"

                        printf '%s\n' "$package" >> "$report"

                        ./scripts/config --disable "$package_config" \
                            2>/dev/null || true
                    fi

                    ;;
            esac
        done < <(grep '^CONFIG_PACKAGE_.*=\(y\|m\)$' .config || true)

        # ----------------------------------------------------
        # 再生成一次配置。
        #
        # 这里仍然允许缺失插件相关问题存在；
        # 如果最终还有真正的 Kconfig 错误，则失败。
        # ----------------------------------------------------
        if ! make defconfig >"$defconfig_log" 2>&1; then

            if grep -Eq \
                'No rule to make target|Makefile:.*Error|Kconfig.*error|syntax error|recipe for target.*failed' \
                "$defconfig_log"; then

                cat "$defconfig_log" >&2
                echo "错误：make defconfig 存在真正的配置 / Makefile 错误。" >&2
                return 1
            fi

            echo "WARNING: make defconfig 返回非零，但未发现真正的 Makefile/Kconfig 错误。"
            echo "WARNING: 继续构建。"

        fi
    fi


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
        make defconfig 2>&1 | tee "$LOGS/defconfig-initial.log" || true


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
        #
        # 缺失插件不作为停止条件。
        # ========================================================
        make defconfig 2>&1 | tee "$LOGS/defconfig-final.log" || {
            echo "WARNING: 最终 defconfig 返回非零，继续构建。"
        }


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
