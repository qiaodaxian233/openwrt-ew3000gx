#!/bin/bash
# ============================================================
# 乔大仙 OpenWrt 汉化版 —— 品牌定制 + 重编固件
#
# 原理：直接改 include/version.mk 的默认值（这个源码树
#       没有 CONFIG_VERSIONOPT，.config 里的 VERSION 会被 defconfig 清掉）
#
# 用法（Windows）：
#   wsl -d owrtbuild -e bash /mnt/e/jiaoben/pojia/RX_EW3000GX_fw/07_开源定制/build_brand.sh
# ============================================================
set -e

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/usr/lib/wsl/lib"
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
export no_proxy="*"
export FORCE_UNSAFE_CONFIGURE=1

SRC=/opt/openwrt
OUT=/mnt/e/jiaoben/pojia/RX_EW3000GX_fw/07_开源定制/out
BRAND="乔大仙 OpenWrt 汉化版"
VERSION="24.10"
REPO_URL="https://github.com/qiaodaxian/openwrt-ew3000gx"

cd "$SRC" || { echo "!! $SRC 不存在"; exit 1; }

echo "═══════════════════════════════════════════════════════════"
echo " 乔大仙 OpenWrt 汉化版 · 品牌定制"
echo "═══════════════════════════════════════════════════════════"

# ─────────────────────────────────────────────
echo
echo "[1] 备份 version.mk"
# ─────────────────────────────────────────────
VM=include/version.mk
if [ ! -f "${VM}.bak-brand" ]; then
  cp "$VM" "${VM}.bak-brand"
  echo "  已备份 -> ${VM}.bak-brand"
else
  echo "  备份已存在"
  cp "${VM}.bak-brand" "$VM"
  echo "  已从备份还原（保证幂等）"
fi

# ─────────────────────────────────────────────
echo
echo "[2] 改 version.mk 默认值"
# ─────────────────────────────────────────────
python3 - "$VM" "$BRAND" "$VERSION" "$REPO_URL" <<'PY'
import sys, re
path, brand, ver, repo = sys.argv[1:5]
s = open(path, encoding='utf-8').read()

def setdefault(s, var, value):
    """把 $(if $(X),$(X),默认值) 的默认值换掉"""
    pat = re.compile(
        r'(VERSION_%s:=\$\(if \$\(VERSION_%s\),\$\(VERSION_%s\),)([^\n]*?)(\))' % (var, var, var),
        re.M)
    new, n = pat.subn(lambda m: m.group(1) + value + m.group(3), s)
    return new, n

changes = []
for var, val in [
    ('DIST', brand),
    ('NUMBER', ver),
    ('MANUFACTURER', brand),
    ('MANUFACTURER_URL', repo),
    ('HOME_URL', repo),
    ('SUPPORT_URL', repo + '/issues'),
    ('BUG_URL', repo + '/issues'),
    ('REPO', repo),
    ('PRODUCT', 'RG-EW3000GX'),
    ('HWREV', 'v0'),
]:
    s, n = setdefault(s, var, val)
    changes.append('%s -> %s (%d处)' % (var, val, n))

open(path, 'w', encoding='utf-8').write(s)
for c in changes:
    print('  ' + c)
PY

echo
echo "  验证："
grep -E '^VERSION_(DIST|NUMBER|MANUFACTURER):=\$\(if' "$VM" | sed 's/^/    /'

# ─────────────────────────────────────────────
echo
echo "[3] 替换 /etc/banner"
# ─────────────────────────────────────────────
BANNER_FILE=package/base-files/files/etc/banner
cat > "$BANNER_FILE" <<'BANNER'

  ╔═══════════════════════════════════════════════════════════╗
  ║                                                           ║
  ║          乔 大 仙   OpenWrt   汉 化 版                    ║
  ║          QiaoDaXian OpenWrt Chinese Edition               ║
  ║                                                           ║
  ╚═══════════════════════════════════════════════════════════╝

      Ruijie RG-EW3000GX  ·  MediaTek MT7981 (Filogic 820)
      Kernel 6.6.159  ·  aarch64_cortex-a53  ·  256MB RAM

  ─────────────────────────────────────────────────────────────
   GitHub : https://github.com/qiaodaxian/openwrt-ew3000gx
   基于   : OpenWrt 24.10 (r0-34fa4b1)
   许可   : GPL-2.0
  ─────────────────────────────────────────────────────────────

BANNER
echo "  已写入 ($(wc -c < "$BANNER_FILE") 字节)"

# ─────────────────────────────────────────────
echo
echo "[4] 默认主机名（uci-defaults）"
# ─────────────────────────────────────────────
UCI_DEF=package/base-files/files/etc/uci-defaults/99-brand-hostname
cat > "$UCI_DEF" <<EOF
#!/bin/sh
uci -q set system.@system[0].hostname='$BRAND'
uci -q commit system
exit 0
EOF
chmod +x "$UCI_DEF"
echo "  已写入 $UCI_DEF"

# ─────────────────────────────────────────────
echo
echo "[5] 清理 base-files 与旧产物"
# ─────────────────────────────────────────────
rm -rf build_dir/target-aarch64_cortex-a53_musl/base-files* 2>/dev/null || true
rm -rf build_dir/target-aarch64_cortex-a53_musl/root-mediatek 2>/dev/null || true
rm -f bin/targets/mediatek/filogic/*ruijie_ew3000gx* 2>/dev/null || true
echo "  已清理"

# ─────────────────────────────────────────────
echo
echo "[6] 编译（约 3-10 分钟）"
echo "───────────────────────────────────────────────────────────"
START=$(date +%s)
if ! make -j"$(nproc)" V=s > /tmp/build_brand.log 2>&1; then
  echo "  !! 编译失败，最后 25 行："
  tail -25 /tmp/build_brand.log
  exit 1
fi
END=$(date +%s)
echo "  完成，耗时 $((END-START)) 秒"

# ─────────────────────────────────────────────
echo
echo "[7] 检查产物"
# ─────────────────────────────────────────────
ls -l bin/targets/mediatek/filogic/*ruijie_ew3000gx* 2>/dev/null || { echo "  !! 无产物"; exit 1; }

# ─────────────────────────────────────────────
echo
echo "[8] 验证品牌写进了 rootfs"
# ─────────────────────────────────────────────
ROOTFS=$(ls -d build_dir/target-aarch64_cortex-a53_musl/root-mediatek 2>/dev/null | head -1)
if [ -n "$ROOTFS" ] && [ -f "$ROOTFS/etc/openwrt_release" ]; then
  echo "  --- $ROOTFS/etc/openwrt_release ---"
  sed 's/^/    /' "$ROOTFS/etc/openwrt_release"
else
  echo "  (rootfs 已打包，跳过预检)"
fi

# ─────────────────────────────────────────────
echo
echo "[9] 拷贝到输出"
# ─────────────────────────────────────────────
mkdir -p "$OUT"
SYSUP=bin/targets/mediatek/filogic/openwrt-mediatek-filogic-ruijie_ew3000gx-squashfs-sysupgrade.bin
INITR=bin/targets/mediatek/filogic/openwrt-mediatek-filogic-ruijie_ew3000gx-initramfs-kernel.bin
MANIFEST=bin/targets/mediatek/filogic/openwrt-mediatek-filogic-ruijie_ew3000gx.manifest

[ -f "$SYSUP" ] && cp "$SYSUP" "$OUT/qiaodaxian-ew3000gx-sysupgrade.bin" && echo "  sysupgrade -> qiaodaxian-ew3000gx-sysupgrade.bin"
[ -f "$INITR" ] && cp "$INITR" "$OUT/qiaodaxian-ew3000gx-initramfs.bin" && echo "  initramfs  -> qiaodaxian-ew3000gx-initramfs.bin"
[ -f "$MANIFEST" ] && cp "$MANIFEST" "$OUT/qiaodaxian-ew3000gx.manifest"

echo
echo "═══════════════════════════════════════════════════════════"
echo " 完成"
echo "═══════════════════════════════════════════════════════════"
ls -l "$OUT"
echo
echo "SHA256:"
sha256sum "$OUT"/*.bin 2>/dev/null | sed 's/^/  /'
