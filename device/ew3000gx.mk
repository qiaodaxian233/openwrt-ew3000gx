# Ruijie EW3000GX (RG-EW3000GX / EW3000GX-PRO)
#
# 硬件：MediaTek MT7981 (Filogic 820) / 256MB RAM / SPI-NOR 32MB
# 实测：
#   model      = MediaTek MT7981 RFB
#   compatible = mediatek,mt7981-spim-nor-rfb
#   arch       = aarch64_cortex-a53
#   kernel     = 5.4.194 (原厂)
#   rootfs     = squashfs-xz
#   分区       : BL2/u-boot-env/Factory/FIP/product_info/kdump/firmware(15MB)
#
# 用法：把这段追加到 target/linux/mediatek/image/filogic.mk 末尾

define Device/ruijie_ew3000gx
  DEVICE_VENDOR := Ruijie
  DEVICE_MODEL := EW3000GX
  DEVICE_DTS := mt7981b-ruijie-ew3000gx
  DEVICE_DTS_DIR := ../dts
  DEVICE_PACKAGES := \
	kmod-mt7981-firmware mt7981-wo-firmware \
	kmod-usb3 kmod-phy-mediatek-tphy \
	kmod-mt7915e kmod-mt7981-firmware
  SUPPORTED_DEVICES := ruijie,ew3000gx ruijie,rg-ew3000gx
  KERNEL_LOADADDR := 0x44000000
  KERNEL_SIZE := 6144k
  IMAGE_SIZE := 15360k
  IMAGES := sysupgrade.bin
  IMAGE/sysupgrade.bin := append-kernel | pad-to $$$$(KERNEL_SIZE) | \
	append-rootfs | pad-rootfs | append-metadata | check-size
endef
TARGET_DEVICES += ruijie_ew3000gx

# ---------------------------------------------------------------------------
# 说明
# ---------------------------------------------------------------------------
# 1) 本机 32MB NOR，无 UBI，使用 firmware 分区（15MB）直接放 FIT 镜像。
#
# 2) IMAGE_SIZE = 15MB 对应分区 firmware (0x100000..0x1000000)
#
# 3) KERNEL_SIZE 6MB 为内核预留空间，可根据实际内核大小调整。
#
# 4) SUPPORTED_DEVICES 让 sysupgrade 接受从原厂固件升级（需配合 -F 强制）。
#
# 5) 若要替换原厂 u-boot（FIP），需另外编译 U-Boot 2023.07 for
#    mt7981-spim-nor，并单独写入 FIP 分区。本文件仅生成内核+rootfs。
