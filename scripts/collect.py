#!/usr/bin/env python3
"""中文说明：只收集当前机型镜像，校验压缩完整性，生成校验和与真实配置。"""
from pathlib import Path
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

tree, board, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
if board not in ('h66k','h68k','h69k'):
    raise SystemExit('未知机型')
target=tree/'bin/targets/rockchip/armv8'
images=list(target.glob(f'*hinlink_opc-{board}*squashfs*sysupgrade.img.gz'))
if len(images)!=1:
    raise SystemExit(f'应找到一个 {board} squashfs 镜像，实际为 {len(images)}')
out.mkdir(parents=True,exist_ok=True)
for p in images:
    # sysupgrade.gz 尾部有 fwtool 元数据；先校验并提取，再检查纯 gzip。
    # -T 输出到临时文件，不改动交付镜像；fwtool 同时验证元数据 CRC。
    with tempfile.TemporaryDirectory(prefix='h6xk-image-') as scratch:
        scratch=Path(scratch)
        raw=scratch/'image.gz'
        meta=scratch/'metadata.json'
        with raw.open('wb') as f:
            subprocess.run([str(tree/'staging_dir/host/bin/fwtool'),'-i',str(meta),'-T',str(p)],stdout=f,check=True)
        metadata=json.loads(meta.read_text())
        if metadata.get('supported_devices') != [f'hinlink,opc-{board}']:
            raise SystemExit('镜像升级元数据与当前机型不一致')
        with gzip.open(raw,'rb') as f:
            while f.read(1024*1024):
                pass
    shutil.copy2(p,out/p.name)
for name in ('profiles.json','config.buildinfo','feeds.buildinfo','version.buildinfo'):
    if (target/name).exists(): shutil.copy2(target/name,out/name)
for p in target.glob(f'*hinlink_opc-{board}*.manifest'):
    shutil.copy2(p,out/p.name)
shutil.copy2(tree/'.config',out/f'{board}.config')
logs=tree.parent/'build-logs'
for name in ('source-revisions.txt','config-drift.txt','generated-adaptation.patch','bbr3-verification.txt'):
    if (logs/name).exists(): shutil.copy2(logs/name,out/name)
lines=[]
for p in sorted(out.iterdir()):
    if p.is_file() and p.name!='sha256sums':
        with p.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
        lines.append(digest+'  '+p.name)
(out/'sha256sums').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(f'已校验并整理 {board} 镜像；编译成功不代表已经实机验证。')
