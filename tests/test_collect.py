"""镜像整理必须接受已验证的升级元数据，并拒绝损坏数据和串机型。"""
import gzip
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/collect.py'

class CollectTests(unittest.TestCase):
    def check_image(self, payload, device='h66k'):
        with tempfile.TemporaryDirectory() as tmp:
            tree=Path(tmp)/'openwrt'
            target=tree/'bin/targets/rockchip/armv8'
            target.mkdir(parents=True)
            image=target/'immortalwrt-hinlink_opc-h66k-squashfs-sysupgrade.img.gz'
            original=payload+b'fixture-metadata-trailer'
            image.write_bytes(original)
            (tree/'.config').write_text('fixture')
            out=Path(tmp)/'firmware'
            def fwtool(args, stdout, check):
                self.assertEqual(args[1],'-i')
                self.assertEqual(args[3],'-T')
                Path(args[2]).write_text(json.dumps({'supported_devices':['hinlink,opc-'+device]}))
                stdout.write(payload)
            with patch('sys.argv',['collect.py',str(tree),'h66k',str(out)]), patch('subprocess.run',side_effect=fwtool):
                runpy.run_path(str(SCRIPT),run_name='__main__')
            self.assertEqual((out/image.name).read_bytes(),original)
            self.assertTrue((out/'sha256sums').exists())

    def test_valid_gzip_with_metadata(self):
        self.check_image(gzip.compress(b'firmware' * 1000))

    def test_wrong_device_rejected(self):
        with self.assertRaises(SystemExit):
            self.check_image(gzip.compress(b'firmware'),'h69k')

    def test_truncated_gzip_rejected(self):
        with self.assertRaises(EOFError):
            self.check_image(gzip.compress(b'firmware')[:-4])

    def test_bad_crc_rejected(self):
        payload=bytearray(gzip.compress(b'firmware'))
        payload[-8] ^= 1
        with self.assertRaises(gzip.BadGzipFile):
            self.check_image(payload)
