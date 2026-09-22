# 中文说明：三款设备独立出包；主系统和内核仍来自 ImmortalWrt。
define Build/h6xk-boot
	rm -rf $@.boot
	mkdir -p $@.boot
	$(CP) $(KDIR)/image-$(notdir $(DEVICE_DTS)).dtb $@.boot/rockchip.dtb
	$(CP) $(IMAGE_KERNEL) $@.boot/kernel.img
endef

define Device/h6xk-common
  SOC := rk3568
  DEVICE_VENDOR := HINLINK
  DEVICE_DTS_DIR := ../dts
  UBOOT_DEVICE_NAME := easepi-rk3568
  KERNEL := kernel-bin
  DEVICE_PACKAGES := kmod-r8125 kmod-r8168 kmod-ata-ahci-dwc kmod-hwmon-pwmfan kmod-thermal kmod-iio-rockchip-saradc
  IMAGE/sysupgrade.img.gz = h6xk-boot | boot-script h6xk | pine64-img | gzip | append-metadata
endef

# 中文说明：H66K 只携带本机设备树，不能刷到另外两款设备。
define Device/hinlink_opc-h66k
  $(call Device/h6xk-common)
  DEVICE_MODEL := OPC-H66K
  DEVICE_DTS := rk3568/rk3568-opc-h66k
  SUPPORTED_DEVICES := hinlink,opc-h66k
endef
TARGET_DEVICES += hinlink_opc-h66k

# 中文说明：H68K 只携带本机设备树，不能刷到另外两款设备。
define Device/hinlink_opc-h68k
  $(call Device/h6xk-common)
  DEVICE_MODEL := OPC-H68K
  DEVICE_DTS := rk3568/rk3568-opc-h68k
  SUPPORTED_DEVICES := hinlink,opc-h68k
endef
TARGET_DEVICES += hinlink_opc-h68k

# 中文说明：H69K 只携带本机设备树，不能刷到另外两款设备。
define Device/hinlink_opc-h69k
  $(call Device/h6xk-common)
  DEVICE_MODEL := OPC-H69K
  DEVICE_DTS := rk3568/rk3568-opc-h69k
  SUPPORTED_DEVICES := hinlink,opc-h69k
endef
TARGET_DEVICES += hinlink_opc-h69k
