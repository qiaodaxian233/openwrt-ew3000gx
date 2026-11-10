# 固件下载

固件不放在仓库里（避免仓库臃肿），请到 **Releases** 页面下载：

👉 https://github.com/qiaodaxian233/openwrt-ew3000gx/releases/latest

## 文件说明

| 文件 | 用途 |
|---|---|
| `qiaodaxian-ew3000gx-sysupgrade.bin` | **刷这个**。sysupgrade 升级用 |
| `qiaodaxian-ew3000gx-initramfs.bin` | 内存试跑用（不写 flash，重启即失效） |
| `qiaodaxian-ew3000gx.manifest` | 包含的软件包清单 |

## 校验

下载后请核对 SHA256：

```bash
# Linux / macOS
sha256sum qiaodaxian-ew3000gx-sysupgrade.bin

# Windows PowerShell
Get-FileHash qiaodaxian-ew3000gx-sysupgrade.bin -Algorithm SHA256
```

SHA256 值见 Release 说明。
