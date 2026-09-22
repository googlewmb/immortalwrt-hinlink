"""中文说明：检查设备拆分、重复执行、冲突保护和配置审计的失败行为。"""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('manage',ROOT/'scripts/manage.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class GuardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tree=Path(self.temp.name)/'openwrt'
        m.write(self.tree/'include/toplevel.mk','# 测试用源码标记\n')
        m.write(self.tree/'target/linux/rockchip/image/Makefile','define Build/pine64-img\nendef\ndefine Build/boot-script\nendef\n$(eval $(call BuildImage))\n')
        m.write(self.tree/'package/boot/uboot-rockchip/Makefile','define U-Boot/rk3568/Default\nendef\nUBOOT_TARGETS := test\n$(eval $(call BuildPackage/U-Boot))\n')
        m.write(self.tree/'feeds.conf.default','src-git packages https://example.test/packages\n')
        m.write(self.tree/'tmp/.packageinfo','Source-Makefile: package/test/Makefile\nPackage: test\n')

    def test_split(self):
        for b in m.BOARDS:
            m.configure(self.tree,b)
            c=m.parse_config(m.read(self.tree/'.config'))
            selected=[k for k,v in c.items() if k.startswith('CONFIG_TARGET_DEVICE_') and v=='y']
            self.assertEqual(selected,[f'CONFIG_TARGET_DEVICE_rockchip_armv8_DEVICE_hinlink_opc-{b}'])
            self.assertEqual(c['CONFIG_PACKAGE_kmod-mt7915e'],'y')
            self.assertEqual(c['CONFIG_PACKAGE_kmod-mt7915-firmware'],'n')

    def test_idempotent(self):
        m.adapt(self.tree)
        before={str(p.relative_to(self.tree)):p.read_bytes() for p in self.tree.rglob('*') if p.is_file()}
        m.adapt(self.tree)
        after={str(p.relative_to(self.tree)):p.read_bytes() for p in self.tree.rglob('*') if p.is_file()}
        self.assertEqual(before,after)
        m.feeds(self.tree)
        before=m.read(self.tree/'feeds.conf')
        m.feeds(self.tree)
        self.assertEqual(before,m.read(self.tree/'feeds.conf'))

    def test_hardware_and_performance(self):
        for b in m.BOARDS:
            m.configure(self.tree,b)
            c=m.parse_config(m.read(self.tree/'.config'))
            for name in ('modemmanager','kmod-hwmon-pwmfan','kmod-usb-net-qmi-wwan'):
                self.assertEqual(c['CONFIG_PACKAGE_'+name],'y' if b=='h69k' else 'n')
            for name in ('kmod-nft-fullcone','kmod-nft-offload','kmod-tcp-bbr','kmod-sched'):
                self.assertEqual(c['CONFIG_PACKAGE_'+name],'y')
            self.assertEqual(c['CONFIG_PACKAGE_kmod-r8126'],'n')

    def test_fullcone_cannot_be_ignored(self):
        m.configure(self.tree,'h69k')
        m.write(self.tree/'.config',m.read(self.tree/'.config').replace('CONFIG_PACKAGE_kmod-nft-fullcone=y',''))
        with patch.dict(os.environ,{'ALLOW_CONFIG_DRIFT':'true'}):
            with self.assertRaises(SystemExit): m.audit(self.tree)

    def test_refuse_conflict_before_writing(self):
        path=self.tree/'target/linux/rockchip/dts/rk3568/rk3568-opc-h66k.dts'
        m.write(path,'用户已有的不同文件')
        image=self.tree/'target/linux/rockchip/image/Makefile'
        before=read_before=image.read_bytes()
        with self.assertRaises(SystemExit): m.adapt(self.tree)
        self.assertEqual(image.read_bytes(),before)
        self.assertEqual(m.read(path),'用户已有的不同文件')

    def test_missing_core_cannot_be_ignored(self):
        m.configure(self.tree,'h69k')
        s=m.read(self.tree/'.config').replace('CONFIG_PACKAGE_kmod-mt7922-firmware=y','')
        m.write(self.tree/'.config',s)
        with patch.dict(os.environ,{'ALLOW_CONFIG_DRIFT':'true'}):
            with self.assertRaises(SystemExit): m.audit(self.tree)

    def test_changed_optional_requires_explicit_opt_in(self):
        m.configure(self.tree,'h68k')
        s=m.read(self.tree/'.config').replace('CONFIG_PACKAGE_htop=y','')
        m.write(self.tree/'.config',s)
        with patch.dict(os.environ,{'ALLOW_CONFIG_DRIFT':'false'}):
            with self.assertRaises(SystemExit): m.audit(self.tree)
        with patch.dict(os.environ,{'ALLOW_CONFIG_DRIFT':'true'}): m.audit(self.tree)

    def test_package_collision_stops(self):
        m.configure(self.tree,'h66k')
        m.write(self.tree/'tmp/.packageinfo','Source-Makefile: package/official/Makefile\nPackage: test\nSource-Makefile: package/third/Makefile\nPackage: test\n')
        with self.assertRaises(SystemExit): m.audit(self.tree)

if __name__=='__main__': unittest.main()
