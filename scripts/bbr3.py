#!/usr/bin/env python3
"""中文说明：安装固定的 BBRv3 补丁并检查实际准备后的内核，禁止静默退回 BBRv1。"""
import hashlib
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
SHA256='4894ae7d5e0800a7540209d5bef7313ced9aaf83e64cbc389336f52b4dcdb05f'

def install(tree):
    text=(tree/'target/linux/rockchip/Makefile').read_text()
    version=re.search(r'^KERNEL_PATCHVER\s*:?=\s*(\S+)',text,re.M)
    if not version or version[1]!='6.18':
        raise SystemExit('BBRv3 补丁仅验证 6.18；内核系列已变化，请更新补丁后再编译')
    source=ROOT/'patch/999-bbr3-6.18.patch'
    data=source.read_bytes()
    if hashlib.sha256(data).hexdigest()!=SHA256:
        raise SystemExit('BBRv3 补丁校验失败')
    dest=tree/'target/linux/rockchip/patches-6.18/999-bbr3-6.18.patch'
    if dest.exists() and dest.read_bytes()!=data:
        raise SystemExit('已有不同的 BBRv3 补丁，拒绝覆盖')
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(data)
    print('已安装固定 BBRv3 补丁；仍需检查实际内核补丁队列及编译')

def verify(tree):
    candidates=list((tree/'build_dir').glob('target-*/linux-rockchip_armv8/linux-6.18*/net/ipv4/tcp_bbr.c'))
    if len(candidates)!=1:
        raise SystemExit(f'需唯一准备后的 Linux 6.18 源码，实际找到 {len(candidates)} 份')
    source=candidates[0].read_text()
    if not re.search(r'#define\s+BBR_VERSION\s+3\b',source) or 'MODULE_VERSION(__stringify(BBR_VERSION))' not in source:
        raise SystemExit('实际内核不是预期 BBRv3；拒绝继续')
    if not re.search(r'\.name\s*=\s*"bbr"',source):
        raise SystemExit('BBR 注册名称变化，需要更新运行时配置')
    log=tree.parent/'build-logs/bbr3-verification.txt'
    log.parent.mkdir(exist_ok=True)
    log.write_text('中文说明：实际准备后的内核含 BBR_VERSION=3，算法名 bbr。\n补丁 SHA256='+SHA256+'\n',encoding='utf-8')
    print('已确认实际内核源码为 BBRv3')

if __name__=='__main__':
    if len(sys.argv)!=3 or sys.argv[1] not in ('install','verify'):
        raise SystemExit('用法：bbr3.py install|verify 源码目录')
    globals()[sys.argv[1]](Path(sys.argv[2]))
