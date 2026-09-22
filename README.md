# H66K / H68K / H69K 独立固件工程

这是以 **ImmortalWrt master** 为主源码的构建工程。H66K、H68K、H69K 分别编译、分别下载、分别刷写，不生成三合一镜像。设备树和通用引导配置来自 iStoreOS `istoreos-25.12`，不是把整个 iStoreOS 系统换名。

**当前状态：待 CI 完整编译和实机验证的移植版本，不是已经验证可刷的固件。** 本机为 Windows，未安装 WSL/Linux 构建环境；已做的检查见 `验证记录.md`。这里没有承诺未来变化的 master 永远编译成功。上游结构变化或配置缺失时会停止并保留诊断，不会把错误隐藏后发布。

## 小白使用步骤

1. 将本目录全部内容上传到你自己的 GitHub 仓库根目录。务必包含隐藏的 `.github` 文件夹；不要只把 ZIP 文件上传到仓库。
2. 打开仓库的 **Actions → ImmortalWrt_H66K_H68K_H69K → Run workflow**。
3. `device` 选择 `h66k`、`h68k`、`h69k`，或 `all`。`all` 会启动三个独立构建任务。
4. `source_ref` 默认 `master`，每次获取最新主源码。需要回查问题时，输入某次成功产物里的主源码 SHA。官方 feeds 的实际 SHA 也会记录，但仅固定主仓库 SHA 并不能完整复现 feeds；需同时把 feeds.conf 的 URL 固定为记录的提交。
5. 第一次保持 `allow_config_drift=false`。如果配置审计失败，下载 `logs-机型-…` 中的 `config-drift.txt`，查看原配置中哪些选项已经不存在、被改名或依赖不满足。修复后再编译。只有明确接受报告中的非核心缺失项，才开启该选项；核心设备、无线和分区要求仍不能绕过。
6. 编译通过后，下载对应机型的 `firmware-机型-…` artifact，或到 Releases 下载对应机型的 `.tar.gz` 包。镜像文件名中包含 `hinlink_opc-h66k` / `h68k` / `h69k`。
7. 核对 `sha256sums`，使用对应机型的镜像进行测试。首次建议通过可恢复的 SD 卡启动，核对网口、存储、无线、H69K 风扇，再决定写入 eMMC；当前没有实机验证记录。

每天北京时间 **00:16** 自动运行，等于模板的 UTC `16:16`。默认三个独立任务；只有所选任务全部通过才生成测试版 Release。保留日志 14 天，不自动删除历史工作流，也不自动向仓库提交 `.config`；最终配置随固件保存，避免构建触发循环和多机型互相覆盖。

## 你要求的设置

| 项目 | 实现 |
|---|---|
| 主源码 | ImmortalWrt master；可手动指定提交 |
| 三款机型拆分 | 独立设备 ID、独立 DTS、独立镜像、独立构建任务 |
| 插件源码 | `diy1.sh`，优先安装官方 feeds，第三方追加在后，不使用强制覆盖 |
| 默认无线 | `diy2.sh` 安装首次启动脚本，开启已有无线电和 AP |
| 无线密码 | 首次启动随机生成；通过有线 SSH 执行 `cat /root/wifi-password.txt` 查看 |
| 连接数 | `net.netfilter.nf_conntrack_max=655550` |
| 分区 | 内核 64 MiB、rootfs 512 MiB、squashfs；体积超过限制会失败，不擅自扩容 |
| 语言 | 保留原配置的简体中文选项 |
| 原配置 | 完整保存在 `configs/requested.config` |
| 中文注释 | 自建脚本、工作流、配置和移植文件均添加中文说明，保留上游版权 |

无线驱动不等于硬件保证支持 AP 模式；仍取决于实际网卡、固件、频段及地区设置。脚本不猜测无线国家码。没有检测到无线电时，首次启动脚本不会删除，安装好网卡后重启会重试。只安装为 `m` 的包会生成安装包，不会直接放入固件，这是原配置的语义。

网口沿用 iStoreOS 的分配：H66K 为 LAN `eth1` / WAN `eth0`；H68K 为 LAN `eth1 eth2 eth3` / WAN `eth0`；H69K 为 LAN `eth1 eth2` / WAN `eth0`。实际物理端口顺序需上机核对。

## 已明确修正的配置

- MT7916 使用 `kmod-mt7915e` 共用驱动，因此启用该驱动，同时保持 MT7915 固件关闭；启用 MT76 公共依赖。驱动名称包含 7915 不代表集成了 MT7915 固件。
- 将 `hostapd-openssl`、`wpa-supplicant-openssl` 和 `wpad-basic-mbedtls=m` 整理为 `wpad-openssl`，避免认证组件的文件和提供者冲突；保留 `wpa-cli`。
- LuCI HTTPS 改为 `luci-ssl-openssl`，与 OpenSSL 无线组件一致。
- 原配置选择 USB 音频，却禁止 sound-core；允许依赖的 sound-core。
- 每个矩阵任务只选择当前设备，替换原配置仅选择 H68K 的目标项；其他包按原配置请求，经 `defconfig` 审计后才继续。
- 移除 iStoreOS 设备树对厂商 VPU/NPU/GPU 扩展文件的引用，保留三款板级供电、PCIe、网口、USB、存储、风扇描述。主线已有的节点保留，不声称移植了 iStoreOS 的厂商加速驱动。

原配置包含大量旧版本或私有扩展包/选项，不能仅凭同名目录断言它们全部可用。工程提供官方优先的第三方来源及严格审计，但最终每一个包是否实际满足，需要真实运行 `defconfig` 和构建才能确认。不会自动删除缺失插件来制造“成功”。`ALLOW_CONFIG_DRIFT=true` 是明确接受部分配置缺失的选择，产物仍包含缺失报告。

## 目录说明

- `.github/workflows/build.yml`：手动/定时、三机型矩阵、缓存、日志、上传与测试版发布。
- `diy1.sh`：插件来源和 feeds 更新、安装。官方已经有 Passwall、OpenClash，使用官方版本。
- `diy2.sh`：设备移植、当前机型配置、无线和连接数默认值。
- `configs/third-party.feeds`：固定 SHA 的第三方来源；最后的 iStoreOS 兼容 feeds 只用于补充缺失包，不能替换 ImmortalWrt 的内核或官方同名包。
- `overlay/`：来自 iStoreOS 并适配的 DTS/DTSI、通用 U-Boot 配置、独立机型镜像定义和 LAN/WAN 设置。
- `patch/`：设备树参考差异和自适应机制说明；不要再对 overlay 重复打这些参考补丁。
- `scripts/manage.py`：检查构建接口、语义插入、拒绝文件冲突、配置审计。
- `scripts/build.sh`：统一构建入口。并行失败后单线程重试以定位错误，不吞掉错误。
- `scripts/collect.py`：检查镜像机型和 gzip 完整性，整理配置与校验值。
- `sources.lock.env`：本次核对的两仓库提交。设备移植文件已随包提供，无需每次抓取移动分支。

## Linux 本地编译

在 Ubuntu 24.04 上按工作流中的“安装编译依赖”安装软件，然后在本工程根目录运行：

```bash
git clone --depth 1 --branch master https://github.com/immortalwrt/immortalwrt.git openwrt
BOARD=h68k JOBS=2 bash scripts/build.sh all
```

请为每个机型使用独立源码工作目录或彻底清理旧目标产物；不要直接复用已经生成旧机型 Kconfig 的脏目录。最简单的方法是用 Actions 矩阵。不同设备的包和内核可以共享下载缓存，但不能混用最终镜像。

在路由器上检查默认设置：

```sh
sysctl net.netfilter.nf_conntrack_max
uci show wireless
cat /root/wifi-password.txt
ubus call system board
```

期望连接数输出为 `655550`。密码文件只允许 root 读取。升级时保留旧配置可能保留旧的无线设置，首次默认值不会强制覆盖用户已有密码。

## 上游依据和许可

- [ImmortalWrt master](https://github.com/immortalwrt/immortalwrt/tree/master)：主系统、内核、默认 feeds 和镜像框架。
- [iStoreOS 设备树](https://github.com/istoreos/istoreos/tree/istoreos-25.12/target/linux/rockchip/dts/rk3568)：三款板级文件和公共 hinlink DTSI。
- [iStoreOS 镜像配置](https://github.com/istoreos/istoreos/tree/istoreos-25.12/target/linux/rockchip/image)：原版为三款合并 `hinlink_opc-h6xk`，本工程拆分。
- [iStoreOS legacy 引导](https://github.com/istoreos/istoreos/tree/istoreos-25.12/target/linux/rockchip/image/legacy)：参考其原始内核和 DTB 加载流程，拆分后不再用 ADC/GPIO 自动识别机型。

移植文件保留各自 SPDX/版权声明；原无单独许可头的文件沿用上游仓库许可，不重新声明第三方代码版权。
