#!/usr/bin/env python3
"""中文说明：按语义定位添加设备定义，不使用固定行号或模糊强制打补丁。"""
import argparse
import difflib
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BOARDS = ('h66k', 'h68k', 'h69k')

def read(p):
    return p.read_text(encoding='utf-8')

def write(p, s):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding='utf-8', newline='\n')

def require(condition, message):
    if not condition:
        raise SystemExit(message)

def feeds(tree):
    path=tree/'feeds.conf'
    original=read(path if path.exists() else tree/'feeds.conf.default')
    start='# BEGIN H6XK THIRD PARTY'
    end='# END H6XK THIRD PARTY'
    original=re.sub(r'\n?'+re.escape(start)+r'.*?'+re.escape(end)+r'\n?', '\n', original, flags=re.S)
    extra=read(ROOT/'configs/third-party.feeds')
    existing={line.split()[1] for line in original.splitlines() if line.startswith('src-')}
    new={line.split()[1] for line in extra.splitlines() if line.startswith('src-')}
    require(not existing & new, f'第三方 feed 名称重复：{existing & new}')
    write(path, original.rstrip()+'\n'+start+'\n'+extra+end+'\n')

def install_feeds(tree):
    # feeds install -a 按源码目录去重；不同目录可导出同名二进制包。
    # 先只安装官方 feeds，再按当前机型实际请求补齐第三方包及其依赖。
    path=tree/'feeds.conf'
    combined=read(path)
    official=re.sub(r'# BEGIN H6XK THIRD PARTY.*?# END H6XK THIRD PARTY\n?', '', combined, flags=re.S)
    require(official != combined, '未找到第三方 feeds 边界')
    try:
        write(path,official)
        subprocess.run(['./scripts/feeds','install','-a'],cwd=tree,check=True)
    finally:
        write(path,combined)
    configure(tree,os.getenv('BOARD','h68k'))
    wanted=[k.removeprefix('CONFIG_PACKAGE_') for k,v in parse_config(read(tree/'.config.requested')).items()
            if k.startswith('CONFIG_PACKAGE_') and v in ('y','m')]
    # 官方安装生成的元数据含核心和已安装 feed 的实际二进制包名。
    subprocess.run(['make','-s','prepare-tmpinfo'],cwd=tree,check=True)
    available=set(re.findall(r'^Package: (\S+)',read(tree/'tmp/.packageinfo'),re.M))
    missing=sorted(set(wanted)-available)
    write(tree.parent/'build-logs/third-party-requested.txt','\n'.join(missing)+'\n')
    if missing:
        subprocess.run(['./scripts/feeds','install',*missing],cwd=tree,check=True)

def adapt(tree):
    image=tree/'target/linux/rockchip/image/Makefile'
    uboot=tree/'package/boot/uboot-rockchip/Makefile'
    a, u = read(image),read(uboot)
    # 只有确认构建接口存在才继续，上游结构变化时不凭猜测重写。
    for token in ('define Build/pine64-img','define Build/boot-script','$(eval $(call BuildImage))'):
        require(a.count(token)==1,'镜像构建接口发生变化：'+token)
    for token in ('define U-Boot/rk3568/Default','$(eval $(call BuildPackage/U-Boot))'):
        require(u.count(token)==1,'U-Boot 构建接口发生变化：'+token)
    require('UBOOT_TARGETS :=' in u,'没有找到 U-Boot 目标列表')
    include='include ./h6xk.mk'
    if include not in a:
        # 若未来官方添加同名设备，应人工核对，避免覆盖其设备定义。
        allmk='\n'.join(read(p) for p in image.parent.glob('*.mk'))
        require(not any('define Device/hinlink_opc-'+b in allmk for b in BOARDS),'官方已有同名设备，请核对后更新移植')
        a=a.replace('$(eval $(call BuildImage))', '# 中文说明：加载三个独立设备配置。\n'+include+'\n\n$(eval $(call BuildImage))')
    block='''# BEGIN H6XK UBOOT
# 中文说明：使用当前 ImmortalWrt 的 ATF/TPL 和 U-Boot 构建框架。
define U-Boot/easepi-rk3568
  $(U-Boot/rk3568/Default)
  NAME:=HINLINK H66K H68K H69K bootloader
  BUILD_DEVICES:=hinlink_opc-h66k hinlink_opc-h68k hinlink_opc-h69k
endef
UBOOT_TARGETS += easepi-rk3568
# END H6XK UBOOT

'''
    if '# BEGIN H6XK UBOOT' not in u:
        require('define U-Boot/easepi-rk3568\n' not in u,'官方已有 easepi-rk3568，需要核对')
        u=u.replace('$(eval $(call BuildPackage/U-Boot))',block+'$(eval $(call BuildPackage/U-Boot))')
    # 在任何写入前检查 overlay 冲突，重复执行时相同文件可以安全保留。
    assets=[p for p in (ROOT/'overlay').rglob('*') if p.is_file()]
    for src in assets:
        dest=tree/src.relative_to(ROOT/'overlay')
        require(not dest.exists() or dest.read_bytes()==src.read_bytes(),f'拒绝覆盖已有不同文件：{dest}')
    changes=[]
    for p,new in ((image,a),(uboot,u)):
        rel=p.relative_to(tree).as_posix()
        changes.extend(difflib.unified_diff(read(p).splitlines(True),new.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
        write(p,new)
    for src in assets:
        dest=tree/src.relative_to(ROOT/'overlay')
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(src,dest)
        if 'board.d' in dest.parts:
            dest.chmod(0o755)
    log=tree.parent/'build-logs'
    log.mkdir(exist_ok=True)
    if changes:
        write(log/'generated-adaptation.patch',''.join(changes))
    print('已添加 H66K/H68K/H69K 独立定义；仍需完成 Linux 构建和实机验证。')

def parse_config(text):
    values={}
    for line in text.splitlines():
        m=re.fullmatch(r'(CONFIG_[^= ]+)=(.*)',line)
        n=re.fullmatch(r'# (CONFIG_\S+) is not set',line)
        if m: values[m[1]]=m[2]
        elif n: values[n[1]]='n'
    return values

def configure(tree,board):
    require(board in BOARDS,'未知机型')
    values=parse_config(read(ROOT/'configs/requested.config'))
    values.update(parse_config(read(ROOT/'configs/compat.config')))
    # 原配置只选了 H68K；矩阵每次只选择当前机型，绝不混合三款设备树。
    values={k:v for k,v in values.items() if not k.startswith('CONFIG_TARGET_DEVICE_')}
    fixes={
        'CONFIG_TARGET_rockchip':'y','CONFIG_TARGET_rockchip_armv8':'y',
        'CONFIG_TARGET_MULTI_PROFILE':'y','CONFIG_TARGET_ALL_PROFILES':'n',
        f'CONFIG_TARGET_DEVICE_rockchip_armv8_DEVICE_hinlink_opc-{board}':'y',
        'CONFIG_TARGET_ROOTFS_SQUASHFS':'y',
        'CONFIG_PACKAGE_kmod-mt7915e':'y',
        'CONFIG_PACKAGE_kmod-mt76-connac':'y','CONFIG_PACKAGE_kmod-mt76-core':'y','CONFIG_PACKAGE_kmod-mt76-usb':'y',
        # MT7916 复用 mt7915e 驱动，但不引入 MT7915 固件。
        'CONFIG_PACKAGE_kmod-mt7915-firmware':'n',
        # 合并为同一个 OpenSSL wpad，避免 hostapd/wpa-supplicant 变体冲突。
        'CONFIG_PACKAGE_wpad-openssl':'y','CONFIG_PACKAGE_wpad-basic-mbedtls':'n',
        'CONFIG_PACKAGE_wpad-basic-openssl':'n','CONFIG_PACKAGE_wpad-basic-wolfssl':'n',
        'CONFIG_PACKAGE_hostapd-openssl':'n','CONFIG_PACKAGE_wpa-supplicant-openssl':'n',
        'CONFIG_PACKAGE_luci-ssl':'n','CONFIG_PACKAGE_luci-ssl-openssl':'y',
        'CONFIG_PACKAGE_kmod-sound-core':'y', # 用户同时选择了 USB 音频。
        'CONFIG_CCACHE':'y',
        # 旧 ntfsprogs 已由官方 ntfs-3g-utils 提供。
        'CONFIG_PACKAGE_ntfsprogs':'n','CONFIG_PACKAGE_ntfs-3g-utils':'y',
        # 固件含 fwupd 的 ModemManager 插件，basic collection 被其依赖禁止。
        'CONFIG_LIBQMI_COLLECTION_BASIC':'n',
        'CONFIG_LIBQMI_COLLECTION_FULL':'y' if board=='h69k' else 'n',
    }
    values.update(fixes)
    # 中文说明：专属硬件片段最后生效，不再只替换目标名称。
    values.update(parse_config(read(ROOT/'configs/devices'/f'{board}.config')))
    values.update({
        'CONFIG_PACKAGE_firewall4':'y', 'CONFIG_PACKAGE_kmod-nft-fullcone':'y',
        'CONFIG_PACKAGE_kmod-nft-offload':'y', 'CONFIG_PACKAGE_kmod-tcp-bbr':'y',
        'CONFIG_PACKAGE_kmod-sched':'y', 'CONFIG_PACKAGE_kmod-r8126':'n',
        'CONFIG_PACKAGE_kmod-r8168':'n', 'CONFIG_PACKAGE_kmod-drm-panfrost':'n',
        'CONFIG_PACKAGE_kmod-rkgpu-bifrost':'n',
    })
    for b in BOARDS:
        values[f'CONFIG_TARGET_DEVICE_rockchip_armv8_DEVICE_hinlink_opc-{b}']='y' if b==board else 'n'
    result='# 中文说明：原配置加上已说明的依赖修正；defconfig 变更会另存报告。\n'
    result+='\n'.join(f'# {k} is not set' if v=='n' else f'{k}={v}' for k,v in values.items())+'\n'
    write(tree/'.config',result)
    write(tree/'.config.requested',result)

def audit(tree):
    # 检查真正被安装的包元数据；发现不同 recipe 提供同名包时禁止继续。
    packageinfo=tree/'tmp/.packageinfo'
    require(packageinfo.exists(),'未生成软件包元数据，不能证明插件没有重名冲突')
    providers={}
    source=None
    conflicts=[]
    for line in read(packageinfo).splitlines():
        if line.startswith('Source-Makefile: '):
            source=line.split(': ',1)[1]
        if line.startswith('Package: ') and source:
            name=line.split(': ',1)[1]
            if name in providers and providers[name]!=source:
                conflicts.append(f'{name}: {providers[name]} / {source}')
            providers[name]=source
    write(tree.parent/'build-logs/package-conflicts.txt','# 中文说明：实际安装的不同 recipe 同名包冲突。\n'+'\n'.join(conflicts)+'\n')
    if conflicts:
        print('\n'.join(conflicts),flush=True)
    require(providers,'软件包元数据格式发生变化，需要更新审计器')
    require(not conflicts,'发现插件重名冲突，停止构建，查看 package-conflicts.txt')
    before=parse_config(read(tree/'.config.requested'))
    after=parse_config(read(tree/'.config'))
    # m 被依赖提升为 y 仍然满足构建请求，不应当作缺失而拦截。
    changes=[f'{k}: {v} -> {after.get(k,"<不存在>")}' for k,v in before.items()
             if v!='n' and after.get(k)!=v and not (v=='m' and after.get(k)=='y')]
    log=tree.parent/'build-logs'
    write(log/'config-drift.txt','# 中文说明：defconfig 移除或改变的用户选项。\n'+'\n'.join(changes)+'\n')
    if changes:
        print('\n'.join(changes),flush=True)
    # 硬性要求始终检查，不能用允许配置漂移选项绕过。
    required=['CONFIG_TARGET_rockchip','CONFIG_TARGET_rockchip_armv8','CONFIG_TARGET_ROOTFS_SQUASHFS',
        'CONFIG_PACKAGE_kmod-r8125','CONFIG_PACKAGE_kmod-mt7915e',
        'CONFIG_PACKAGE_kmod-mt7916-firmware','CONFIG_PACKAGE_kmod-mt7921e','CONFIG_PACKAGE_kmod-mt7921u',
        'CONFIG_PACKAGE_kmod-mt7922-firmware','CONFIG_PACKAGE_wpad-openssl',
        'CONFIG_PACKAGE_firewall4','CONFIG_PACKAGE_kmod-nft-fullcone',
        'CONFIG_PACKAGE_kmod-nft-offload','CONFIG_PACKAGE_kmod-tcp-bbr','CONFIG_PACKAGE_kmod-sched']
    required += [k for k,v in before.items() if k.startswith('CONFIG_TARGET_DEVICE_') and v=='y']
    selected={k for k,v in after.items() if k.startswith('CONFIG_TARGET_DEVICE_') and v=='y'}
    expected={k for k,v in before.items() if k.startswith('CONFIG_TARGET_DEVICE_') and v=='y'}
    require(len(expected)==1 and selected==expected,'目标机型数量或型号变化，禁止生成混合固件')
    forbidden=['kmod-r8126','kmod-r8168','kmod-drm-panfrost','kmod-rkgpu-bifrost',
               'hostapd-openssl','wpa-supplicant-openssl','wpad-basic-mbedtls',
               'wpad-basic-openssl','wpad-basic-wolfssl']
    require(not any(after.get('CONFIG_PACKAGE_'+name) in ('y','m') for name in forbidden),
            '禁用的硬件驱动或冲突无线认证组件被重新启用')
    require(all(after.get(k)=='y' for k in required),'设备或无线必要配置丢失，停止构建，查看 config-drift.txt')
    require(after.get('CONFIG_TARGET_KERNEL_PARTSIZE')=='64' and after.get('CONFIG_TARGET_ROOTFS_PARTSIZE')=='512','分区大小发生变化')
    if changes:
        require(os.getenv('ALLOW_CONFIG_DRIFT','false')=='true','配置有未满足项，停止构建；不要把缺失插件当成已集成。')
    write(log/'effective.config',read(tree/'.config'))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['feeds','install_feeds','adapt','config','audit'])
    parser.add_argument('tree',type=Path)
    parser.add_argument('board',nargs='?',default='h68k')
    args=parser.parse_args()
    require((args.tree/'include/toplevel.mk').exists(),'指定目录不是 OpenWrt/ImmortalWrt 源码根目录')
    if args.action=='config': configure(args.tree,args.board)
    else: globals()[args.action](args.tree)
