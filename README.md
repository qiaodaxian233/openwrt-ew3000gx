# 乔大仙 OpenWrt 汉化版 · Ruijie RG-EW3000GX

> 锐捷 EW3000GX（RG-EW3000GX）OpenWrt 24.10 移植固件 —— 完整中文界面

[![Release](https://img.shields.io/github/v/release/qiaodaxian233/openwrt-ew3000gx?color=brightgreen&label=release)](https://github.com/qiaodaxian233/openwrt-ew3000gx/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/qiaodaxian233/openwrt-ew3000gx/total?color=blue)](https://github.com/qiaodaxian233/openwrt-ew3000gx/releases)
[![Stars](https://img.shields.io/github/stars/qiaodaxian233/openwrt-ew3000gx?style=flat&color=yellow)](https://github.com/qiaodaxian233/openwrt-ew3000gx/stargazers)
[![License](https://img.shields.io/badge/license-GPL--2.0-red)](https://github.com/qiaodaxian233/openwrt-ew3000gx/blob/main/LICENSE)

![Platform](https://img.shields.io/badge/platform-MediaTek%20MT7981-blue)
![OpenWrt](https://img.shields.io/badge/OpenWrt-24.10-brightgreen)
![Kernel](https://img.shields.io/badge/kernel-6.6.159-orange)

---

## 这是什么

锐捷 Reyee EW3000GX 是一款 MT7981（Filogic 820）方案的 WiFi6 路由器。
本固件把它从原厂 ReyeeOS 换成 OpenWrt 24.10，带完整 LuCI 中文界面。

**核心特性：**

- OpenWrt 24.10-SNAPSHOT（r0-34fa4b1）
- 内核 6.6.159
- LuCI 完整中文汉化
- MT7981 WiFi6（2.4G + 5G，160MHz）
- 默认 LAN `192.168.2.1`（避开光猫 `192.168.1.1` 冲突）
- 已集成 xray 代理控制 / 动态 DNS / HTTPS DNS Proxy / irqbalance

---

## 硬件规格

| 项目 | 规格 |
|---|---|
| 型号 | Ruijie Reyee RG-EW3000GX |
| SoC | MediaTek MT7981 (Filogic 820) |
| CPU | 双核 ARM Cortex-A53 @ 1.3 GHz |
| RAM | 256 MB DDR3 |
| Flash | 128 Mbit (16 MB) SPI-NOR — `en25qx128a` |
| WiFi | MT7981 内置 2.4G + 5G（WiFi6，AX3000） |
| 网口 | 1× WAN + 3× LAN（千兆） |
| 按钮 | Reset |
| LED | 系统状态灯 |

**分区表（SPI-NOR）：**

```
mtd0  BL2            256 KB    0x000000    ⚠️ 绝不碰
mtd1  u-boot-env      64 KB    0x040000
mtd2  Factory         64 KB    0x050000    ⚠️ WiFi 校准，丢了没信号
mtd3  FIP            512 KB    0x060000    ⚠️ u-boot 本体，绝不碰
mtd4  product_info    64 KB    0x0E0000
mtd5  kdump           64 KB    0x0F0000
mtd6  firmware        15 MB    0x100000    ✅ 刷这个
mtd7  kernel         2.7 MB    0xA00000
mtd8  rootfs        12.3 MB    0xC70000
mtd9  rootfs_data    1.7 MB    0x1F00000
```

---

## 📥 下载

**最新固件：** [**Releases → v1.0**](https://github.com/qiaodaxian233/openwrt-ew3000gx/releases/latest)

| 文件 | 大小 | 用途 |
|---|---|---|
| [qiaodaxian-ew3000gx-sysupgrade.bin](https://github.com/qiaodaxian233/openwrt-ew3000gx/releases/latest/download/qiaodaxian-ew3000gx-sysupgrade.bin) | 8.75 MB | **刷这个** |
| [qiaodaxian-ew3000gx-initramfs.bin](https://github.com/qiaodaxian233/openwrt-ew3000gx/releases/latest/download/qiaodaxian-ew3000gx-initramfs.bin) | 8.38 MB | 内存试跑（不写 flash） |
| [qiaodaxian-ew3000gx.manifest](https://github.com/qiaodaxian233/openwrt-ew3000gx/releases/latest/download/qiaodaxian-ew3000gx.manifest) | 4.7 KB | 软件包清单 |

**SHA256：**

```
5ee079349d3f1315e2836cef04a29805ffb6467c1b97edcd353fc843fcbb6728  qiaodaxian-ew3000gx-sysupgrade.bin
d46e0a17ce3abcfc0972b00133ea0a00528cb5203c842fe1b3826cbdeb76ca4e  qiaodaxian-ew3000gx-initramfs.bin
```

---

## 快速开始

> ### ⚠️ 必须用 CH340 串口，不能用 sysupgrade
>
> **OpenWrt 的 `sysupgrade` 会破坏这台设备的 NOR flash：**
>
> 它走 UBI 路径，在 rootfs 区域（固件内 `0x440000` 偏移）写入 `UBI#` 头。
> `mtdsplit_fit` 会把分区识别成 `ubi` 而不是 `rootfs`，
> 内核挂载失败 → Kernel panic → 重启循环。
>
> **唯一正确的刷法：u-boot 的 `sf erase` + `sf write`。**

### 需要准备

| 东西 | 说明 |
|---|---|
| **CH340G USB-TTL** | 约 10 元，**电平必须 3.3V**（5V 可能烧 SoC） |
| 杜邦线 3 根 | GND / TX / RX |
| 网线 | 接路由器 LAN 口 |
| 螺丝刀 + 电烙铁 | 拆机接 UART 焊盘 |

**接线（TX/RX 交叉）：**

```
路由器 UART 焊盘        USB-TTL
   GND      ──────────  GND
   TX       ──────────  RX
   RX       ──────────  TX
```

**串口参数：115200 8N1，无流控**

### 一键刷机

```bash
# 1. 装依赖
pip install pyserial

# 2. 设置 PC IP（管理员 PowerShell）
New-NetIPAddress -InterfaceAlias "以太网" -IPAddress 192.168.1.100 -PrefixLength 24

# 3. 检查环境
python flash_uboot.py --port COM4 --check

# 4. 刷机（脚本会提示上电时机）
python flash_uboot.py --port COM4
```

**脚本流程：**

1. 校验固件（大小 / FIT 魔数 / SHA256 / 品牌串）
2. 起 TFTP 服务器（0.0.0.0:69）
3. 持续发空格抢 u-boot console（自动选 `0. U-Boot console`）
4. **全量擦除 firmware 分区**（15 MB，约 110 秒）— 清掉 UBI 头
5. 验证擦除结果（全 `0xFF`）
6. TFTP 传固件到内存 `0x46000000`
7. 验证 FIT 魔数 + Load Address `0x48000000`
8. `sf write` 写入
9. `cmp.b` 逐字节校验
10. `reset` 并抓启动日志（自动检查 9 项指标）

**参数：**

| 参数 | 说明 |
|---|---|
| `--port COM4` | 串口号（设备管理器里看） |
| `--check` | 只检查环境，不刷 |
| `--no-erase` | 跳过全量擦除（已有正确固件时省 2 分钟） |
| `--yes` | 跳过确认 |

### 手动刷（脚本失败时）

**抢 u-boot：** 上电时每 20ms 发空格，看到 `Boot Menu` 后选 `0. U-Boot console`

```bash
# u-boot 里执行
sf probe 0
sf erase 0x100000 0xF00000
sf read 0x48000000 0x100000 0x10 && md.b 0x48000000 0x10    # 应全 ff

setenv ipaddr 192.168.1.1
setenv serverip 192.168.1.100
setenv netmask 255.255.255.0
ping 192.168.1.100

tftpboot 0x46000000 qiaodaxian-ew3000gx-sysupgrade.bin
iminfo 0x46000000                                            # Load Address 应为 0x48000000

sf write 0x46000000 0x100000 0x8C0006                        # 大小见上一步 filesize
sf read 0x48000000 0x100000 0x8C0006
cmp.b 0x46000000 0x48000000 0x8C0006                         # 必须 "were the same"

reset
```

### 方式二：手动 SSH

```bash
# 1. 上传固件
scp qiaodaxian-ew3000gx-sysupgrade.bin root@192.168.2.1:/tmp/

# 2. 校验
ssh root@192.168.2.1 "sha256sum /tmp/qiaodaxian-ew3000gx-sysupgrade.bin"

# 3. 备份配置（可选）
ssh root@192.168.2.1 "sysupgrade -b /tmp/backup.tar.gz"

# 4. 刷机（保留配置）
ssh root@192.168.2.1 "sysupgrade /tmp/qiaodaxian-ew3000gx-sysupgrade.bin"

# 5. 或全新安装
ssh root@192.168.2.1 "sysupgrade -n /tmp/qiaodaxian-ew3000gx-sysupgrade.bin"
```

### 方式三：LuCI 网页

1. 浏览器打开 `http://192.168.2.1/`
2. 系统 → 备份与更新 → 刷写固件
3. 选择 `qiaodaxian-ew3000gx-sysupgrade.bin`
4. 点「刷写固件」

---

## 首次开机

```
WiFi SSID : OpenWrt-2.4G / OpenWrt-5G
WiFi 密码 : 无（开放网络，首次登录后请立刻设置）
Web 界面  : http://192.168.2.1/
SSH       : root@192.168.2.1（无密码）
```

**⚠️ 首次登录后立刻做的事：**

1. **设置 WiFi 密码** — 网络 → 无线 → 编辑 → 无线安全
2. **设置 root 密码** — 系统 → 管理权
3. **改国家代码** — 网络 → 无线 → 编辑 → 高级设置 → 国家代码选 `CN`（否则 5G 可能受限）

---

## 从原厂 ReyeeOS 刷过来

**前置条件：** 已经刷入 OpenWrt（本固件是 OpenWrt → OpenWrt 升级）

如果你还在原厂 ReyeeOS，需要先：

1. 拆机接 UART（CH340G，3.3V 电平）
2. 进 u-boot，`tftpboot` 加载 initramfs 试跑
3. 确认可用后 `sysupgrade` 写入

详细步骤见 [`docs/从原厂刷机.md`](docs/从原厂刷机.md)

---

## 回滚到原厂

**前提：刷机前备份过 `mtd6_firmware.bin`**

```bash
# 在 OpenWrt 里
mtd write mtd6_firmware.bin firmware
mtd verify mtd6_firmware.bin firmware
reboot
```

**或者 u-boot 里：**

```bash
tftpboot 0x46000000 mtd6_firmware.bin
sf probe 0
sf erase 0x100000 0xF00000
sf write 0x46000000 0x100000 $filesize
reset
```

---

## 编译

### 环境

```bash
# Ubuntu 22.04 / Debian 12
sudo apt install -y build-essential ccache ecj fastjar file g++ gawk \
  gettext git java-propose-classpath libelf-dev libncurses5-dev \
  libncursesw5-dev libssl-dev python3 python3-distutils python3-setuptools \
  python3-dev rsync subversion swig time xsltproc zlib1g-dev
```

### 拉源码

```bash
git clone https://github.com/RuijieNetworksCommunity/MT798X-6.6-24.10.git openwrt
cd openwrt
git checkout openwrt-24.10-6.6
```

### 应用设备定义

```bash
# DTS
cp dts/mt7981b-ruijie-rg-ew3000gx.dts target/linux/mediatek/dts/

# 设备定义
cat device/ew3000gx.mk >> target/linux/mediatek/image/filogic.mk
```

### 品牌定制

```bash
# 改品牌（会自动改 version.mk / banner / hostname）
bash scripts/build_brand.sh
```

### 配置与编译

```bash
make defconfig
cat >> .config <<EOF
CONFIG_TARGET_mediatek=y
CONFIG_TARGET_mediatek_filogic=y
CONFIG_TARGET_mediatek_filogic_DEVICE_ruijie_ew3000gx=y
CONFIG_PACKAGE_luci=y
CONFIG_PACKAGE_luci-theme-bootstrap=y
CONFIG_PACKAGE_uhttpd=y
CONFIG_PACKAGE_uhttpd-mod-ubus=y
EOF
make defconfig
make -j$(nproc)
```

**产物：** `bin/targets/mediatek/filogic/`

---

## 关键技术点

### DTB 与内核地址必须分开

```
DEVICE_DTS_LOADADDR := 0x47000000    # DTB
KERNEL_LOADADDR     := 0x48000000    # 内核（默认，不要手写）
```

**如果两个都设成 `0x48080000`，DTB 会覆盖内核，u-boot 报：**

```
ERROR: image is not a fdt - must RESET the board to recover.
```

### 6.6 内核是 relocatable

原厂 5.4 内核 `text_offset = 0x80000`，但 6.6 是 `text_offset = 0`，必须用 `0x48000000`。

### LAN 网段避开光猫

默认 `192.168.1.1` 会和光猫冲突，改为 `192.168.2.1`：

```bash
# target/linux/mediatek/filogic/base-files/etc/board.d/02_network
ruijie,rg-ew3000gx|\
ruijie,ew3000gx)
    ucidef_set_interfaces_lan_wan "lan1 lan2 lan3" wan
    ucidef_set_interface_addr "lan" "192.168.2.1" "255.255.255.0"
    ;;
```

---

## 目录结构

```
.
├── README.md                      本文件
├── LICENSE                        GPL-2.0
├── flash_uboot.py                 u-boot 刷机脚本（CH340 串口）
├── build_brand.sh                 品牌定制 + 重编脚本
├── device/
│   ├── ew3000gx.mk                设备编译定义
│   └── mt7981b-ruijie-rg-ew3000gx.dts
├── out/
│   ├── qiaodaxian-ew3000gx-sysupgrade.bin     ← 刷这个
│   ├── qiaodaxian-ew3000gx-initramfs.bin      ← 内存试跑用
│   └── qiaodaxian-ew3000gx.manifest
└── docs/
    ├── 从原厂刷机.md
    ├── 回滚指南.md
    └── 硬件实测.md
```

---

## 已知问题

| 问题 | 状态 | 说明 |
|---|---|---|
| WiFi 国家代码默认 `00` | 需手动改 | 改 `CN` 才能用完整 5G 信道 |
| 首次开机无 WiFi 密码 | 设计如此 | 立刻设置 |
| 16 MB flash 空间紧 | 已知 | 装不了太多插件 |

---

## 致谢

- [OpenWrt](https://openwrt.org/) — 基础系统
- [RuijieNetworksCommunity/MT798X-6.6-24.10](https://github.com/RuijieNetworksCommunity/MT798X-6.6-24.10) — MT798x 移植基础
- [LuCI](https://github.com/openwrt/luci) — Web 界面
- 中文汉化 — LuCI 官方 zh-cn 翻译

---

## 许可证

本项目基于 OpenWrt，遵循 **GPL-2.0** 许可证。

```
Copyright (C) 2026 乔大仙

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.
```

---

## 免责声明

刷机有风险，操作需谨慎。请务必：

1. **刷机前备份全部分区**（尤其 `BL2` / `FIP` / `Factory`）
2. **不要在刷写过程中断电**
3. **确认自己有能力通过 UART 救砖**

因操作不当导致的设备损坏，作者不承担责任。
