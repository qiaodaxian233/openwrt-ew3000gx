#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
乔大仙 OpenWrt 汉化版 —— 刷机脚本（u-boot 串口版）

⚠️ 为什么不用 sysupgrade？
   OpenWrt 的 sysupgrade 走 UBI 路径，会在 rootfs 区域（固件内 0x440000 偏移）
   写入 UBI# 头。mtdsplit_fit 会把分区识别成 "ubi" 而不是 "rootfs"，
   内核挂载失败 -> Kernel panic -> 重启循环。

   本机实测过这个坑，只能用 u-boot 的 sf erase + sf write。

⚠️ 为什么必须用 CH340？
   1. 原厂 ReyeeOS 的 Web/SSH 有签名校验，拒绝非官方固件
   2. u-boot bootdelay 只有 2 秒，必须串口抓
   3. 只有 u-boot 能做 sf erase / sf write

用法：
    python flash_uboot.py --port COM4
    python flash_uboot.py --port COM4 --check     # 只检查环境
    python flash_uboot.py --port COM4 --no-erase  # 跳过全量擦除（已有正确固件时）

流程：
    1. 校验固件（大小 / FIT 魔数 / SHA256）
    2. 起 TFTP 服务器（0.0.0.0:69）
    3. 持续发空格抢 u-boot console
    4. 全量擦除 firmware 分区（15 MB，约 110 秒）
    5. 验证擦除结果（全 0xFF）
    6. TFTP 传固件到内存
    7. 验证 FIT 魔数和 load 地址
    8. sf write 写入
    9. cmp.b 逐字节校验
    10. reset 并抓启动日志
"""
import sys
import os
import io
import re
import time
import socket
import struct
import hashlib
import argparse
import threading

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
FW_DEFAULT = os.path.join(HERE, "out", "qiaodaxian-ew3000gx-sysupgrade.bin")

# 硬件参数（实测）
PROMPT = b"MT7981>"
LOAD_ADDR = 0x46000000       # TFTP 加载地址
CMP_ADDR = 0x48000000        # 校验回读地址
FW_OFFSET = 0x100000         # firmware 分区起始
FW_SIZE = 0xF00000           # firmware 分区大小 15 MB
UB_IP = "192.168.1.1"        # u-boot 侧 IP
PC_IP = "192.168.1.100"      # PC 侧 IP
BAUD = 115200


def hr(t=""):
    print("\n" + "=" * 68)
    if t:
        print(t)
        print("=" * 68)


def ok(s):
    print("  [OK]   " + s)


def bad(s):
    print("  [FAIL] " + s)


def info(s):
    print("  " + s)


# ══════════════════════════════════════════════════
# TFTP 服务器
# ══════════════════════════════════════════════════
class Tftp(threading.Thread):
    def __init__(self, root, port=69):
        super().__init__(daemon=True)
        self.root = root
        self.stop_flag = False
        self.log = []
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("0.0.0.0", port))
        self.srv.settimeout(1.0)

    def run(self):
        while not self.stop_flag:
            try:
                data, addr = self.srv.recvfrom(2048)
            except socket.timeout:
                continue
            except Exception:
                break
            if len(data) < 4 or struct.unpack(">H", data[:2])[0] != 1:
                continue
            parts = data[2:].split(b"\x00")
            fname = parts[0].decode("latin1")
            path = os.path.join(self.root, os.path.basename(fname))
            self.log.append("RRQ %s from %s:%d" % (fname, addr[0], addr[1]))
            if not os.path.isfile(path):
                self.srv.sendto(struct.pack(">HH", 5, 1) + b"File not found\x00", addr)
                continue
            self._send(path, addr)

    def _send(self, path, addr):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("0.0.0.0", 0))
        s.settimeout(3)
        total = os.path.getsize(path)
        sent = 0
        blk = 1
        try:
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(512)
                    pkt = struct.pack(">HH", 3, blk) + chunk
                    good = False
                    for _ in range(10):
                        s.sendto(pkt, addr)
                        try:
                            ack, _ = s.recvfrom(1024)
                            if len(ack) >= 4:
                                a, n = struct.unpack(">HH", ack[:4])
                                if a == 4 and n == blk:
                                    good = True
                                    break
                        except socket.timeout:
                            continue
                    if not good:
                        self.log.append("  block %d FAILED" % blk)
                        break
                    sent += len(chunk)
                    if len(chunk) < 512:
                        break
                    blk = (blk + 1) & 0xFFFF
            self.log.append("  DONE %d / %d bytes" % (sent, total))
        finally:
            s.close()


# ══════════════════════════════════════════════════
# 串口命令
# ══════════════════════════════════════════════════
def cmd(s, line, maxwait=300, expect=None, label=""):
    s.reset_input_buffer()
    s.write(line.encode() + b"\r")
    buf = bytearray()
    t0 = time.time()
    got = False
    while time.time() - t0 < maxwait:
        c = s.read(8192)
        if c:
            buf += c
            if PROMPT in bytes(buf[-40:]):
                got = True
                ex = time.time()
                while time.time() - ex < 0.3:
                    c2 = s.read(8192)
                    if c2:
                        buf += c2
                        ex = time.time()
                break
    txt = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", bytes(buf).decode("utf-8", "replace"))
    good = (expect in txt) if expect else True
    if label:
        print("\n" + "-" * 68)
        print("%s   >>> %s" % (label, line))
        print("-" * 68)
        print(txt.strip()[:1500])
        print("[%.1fs] 提示符=%s 关键=%s" % (time.time() - t0, got, good))
    return txt, got, good


# ══════════════════════════════════════════════════
# 固件校验
# ══════════════════════════════════════════════════
def check_firmware(path):
    hr("[1] 固件校验")
    if not os.path.exists(path):
        bad("不存在: %s" % path)
        return None

    size = os.path.getsize(path)
    info("路径   : %s" % path)
    info("大小   : %d 字节 (%.2f MB)" % (size, size / 1048576.0))

    if size > FW_SIZE:
        bad("固件超出 firmware 分区（%d > %d）" % (size, FW_SIZE))
        return None
    if size < 4 * 1048576:
        bad("固件太小")
        return None

    with open(path, "rb") as f:
        head = f.read(4)
    if head != b"\xd0\x0d\xfe\xed":
        bad("不是 FIT 镜像（头部 %s）" % head.hex())
        return None
    ok("FIT 魔数正确 (d0 0d fe ed)")

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    digest = h.hexdigest()
    info("SHA256 : %s" % digest)

    with open(path, "rb") as f:
        txt = f.read().decode("utf-8", "ignore")
    if "乔大仙" in txt:
        ok("品牌字符串已写入")

    return {"path": path, "size": size, "sha256": digest}


# ══════════════════════════════════════════════════
# 环境检查
# ══════════════════════════════════════════════════
def check_env(port):
    hr("[2] 环境检查")

    try:
        import serial
        ok("pyserial 已安装")
    except ImportError:
        bad("缺 pyserial，请运行: pip install pyserial")
        return False

    try:
        s = serial.Serial(port, BAUD, timeout=0.2)
        s.close()
        ok("串口 %s 可用" % port)
    except Exception as e:
        bad("串口 %s 打不开: %s" % (port, str(e)[:80]))
        info("检查：")
        info("  1. CH340 驱动装了吗")
        info("  2. 设备管理器里是 COM 几")
        info("  3. 有没有别的程序占用（PuTTY/串口助手）")
        return False

    # 检查 PC IP
    import subprocess
    try:
        out = subprocess.run(["ipconfig"], capture_output=True, text=True,
                             encoding="gbk", errors="ignore", timeout=10).stdout
        if PC_IP in out:
            ok("PC 已有 IP %s" % PC_IP)
        else:
            bad("PC 没有 %s" % PC_IP)
            info("设置命令（管理员 PowerShell）：")
            info('  New-NetIPAddress -InterfaceAlias "以太网" -IPAddress %s -PrefixLength 24' % PC_IP)
            return False
    except Exception:
        info("无法检查 PC IP，跳过")

    # 检查 69 端口
    try:
        t = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        t.bind(("0.0.0.0", 69))
        t.close()
        ok("TFTP 端口 69 可用")
    except Exception as e:
        bad("端口 69 被占用: %s" % str(e)[:60])
        return False

    return True


# ══════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(description="乔大仙 OpenWrt 汉化版 u-boot 刷机")
    ap.add_argument("--port", default="COM4", help="串口（默认 COM4）")
    ap.add_argument("--firmware", default=FW_DEFAULT, help="固件路径")
    ap.add_argument("--check", action="store_true", help="只检查环境")
    ap.add_argument("--no-erase", action="store_true", help="跳过全量擦除")
    ap.add_argument("--yes", action="store_true", help="跳过确认")
    args = ap.parse_args()

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   乔大仙 OpenWrt 汉化版  ·  u-boot 刷机                      ║")
    print("║   Ruijie RG-EW3000GX  ·  MediaTek MT7981                     ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    fw = check_firmware(args.firmware)
    if not fw:
        return 1

    if args.check:
        check_env(args.port)
        hr("仅检查模式")
        return 0

    if not check_env(args.port):
        return 1

    if not args.yes:
        hr("⚠️  确认")
        info("固件     : %s" % os.path.basename(fw["path"]))
        info("大小     : %.2f MB" % (fw["size"] / 1048576.0))
        info("串口     : %s @ %d" % (args.port, BAUD))
        info("写入位置 : 0x%X (%d MB)" % (FW_OFFSET, FW_SIZE // 1048576))
        info("全量擦除 : %s" % ("否" if args.no_erase else "是（约 110 秒）"))
        print()
        info("⚠️  刷写过程中绝对不能断电")
        info("⚠️  需要手动给路由器上电（脚本会提示）")
        print()
        try:
            a = input("  确认刷机？输入 yes: ").strip().lower()
        except EOFError:
            a = ""
        if a not in ("yes", "y"):
            info("已取消")
            return 0

    import serial

    # ── TFTP 服务器
    hr("[3] 启动 TFTP 服务器")
    root = os.path.dirname(fw["path"])
    srv = Tftp(root)
    srv.start()
    ok("TFTP 监听 0.0.0.0:69，根目录 %s" % root)

    # ── 打开串口
    hr("[4] 打开串口 %s @ %d" % (args.port, BAUD))
    s = serial.Serial(args.port, BAUD, timeout=0.05,
                      dsrdtr=False, rtscts=False, xonxoff=False)
    s.dtr = False
    s.rts = False
    time.sleep(0.2)
    s.reset_input_buffer()
    ok("串口已打开")

    stop = threading.Event()
    buf = bytearray()
    lock = threading.Lock()

    def spam():
        while not stop.is_set():
            try:
                s.write(b" ")
            except Exception:
                break
            time.sleep(0.02)

    def reader():
        while not stop.is_set():
            try:
                c = s.read(4096)
                if c:
                    with lock:
                        buf.extend(c)
            except Exception:
                time.sleep(0.05)

    # ── 抢 u-boot
    hr("[5] 抢 u-boot console")
    print(">>> 请现在给路由器上电（拔插电源）<<<")
    print(">>> 脚本会持续发空格，看到 Boot Menu 自动选 0 <<<")

    t_spam = threading.Thread(target=spam, daemon=True)
    t_read = threading.Thread(target=reader, daemon=True)
    t_spam.start()
    t_read.start()

    t0 = time.time()
    menu_seen = False
    zero_sent = False
    got = False
    last = 0

    while time.time() - t0 < 200:
        with lock:
            raw = bytes(buf)
        now = time.time()

        if not menu_seen and b"U-Boot Boot Menu" in raw:
            menu_seen = True
            print("  >>> [%.1fs] Boot Menu 出现" % (now - t0))

        if menu_seen and not zero_sent and b"0. U-Boot console" in raw:
            zero_sent = True
            print("  >>> [%.1fs] 选择 0. U-Boot console" % (now - t0))
            s.write(b"0")
            time.sleep(0.1)
            s.write(b"\r")

        if PROMPT in raw:
            got = True
            print("\n*** 进入 u-boot console (%.1fs) ***" % (now - t0))
            break

        if now - last >= 4:
            last = now
            tail = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "",
                          bytes(buf[-200:]).decode("utf-8", "replace"))
            print("  %5.1fs menu=%s %d字节 %s"
                  % (now - t0, menu_seen, len(raw), " ".join(tail.split())[-50:]))

    stop.set()
    time.sleep(0.3)
    s.reset_input_buffer()
    s.write(b"\r")
    time.sleep(0.6)
    s.reset_input_buffer()

    if not got:
        bad("未进入 u-boot console")
        info("检查：")
        info("  1. 上电时机对不对（脚本提示后再上电）")
        info("  2. 串口接线对不对（TX/RX 要交叉）")
        info("  3. 波特率是不是 115200")
        s.close()
        srv.stop_flag = True
        return 1

    try:
        # ── probe
        hr("[6] 探测 flash")
        t, g, good = cmd(s, "sf probe 0", 30, "en25qx128a", "sf probe")
        if "en25qx128a" not in t:
            bad("flash 探测失败")
            return 1
        ok("flash: en25qx128a (16 MB)")

        # ── 检查现有 UBI 头
        hr("[7] 检查 rootfs 区是否有 UBI 头残留")
        cmd(s, "sf read 0x48000000 0x540000 0x10", 30, "Read: OK", "读 0x540000")
        t, g, _ = cmd(s, "md.b 0x48000000 0x10", 30, None, "看内容")
        if "75 62 69 23" in t or "ubi#" in t.lower():
            info("⚠️  检测到 UBI 头（上次 sysupgrade 留下的），必须全量擦除")
        else:
            ok("无 UBI 头")

        # ── 擦除
        if args.no_erase:
            info("跳过擦除（--no-erase）")
        else:
            hr("[8] 全量擦除 firmware 分区（15 MB，约 110 秒）")
            info("⚠️  不要断电！")
            t, g, good = cmd(s, "sf erase 0x%X 0x%X" % (FW_OFFSET, FW_SIZE),
                             400, "Erased: OK", "sf erase")
            if "Erased: OK" not in t:
                bad("擦除失败")
                return 1
            ok("擦除完成")

            hr("[9] 验证擦除结果（应全 0xFF）")
            cmd(s, "sf read 0x48000000 0x100000 0x10", 30, "Read: OK", "读固件头")
            t1, _, _ = cmd(s, "md.b 0x48000000 0x10", 30, None, "应为全 ff")
            cmd(s, "sf read 0x48000000 0x540000 0x10", 30, "Read: OK", "读 0x540000")
            t2, _, _ = cmd(s, "md.b 0x48000000 0x10", 30, None, "应为全 ff")
            if "ff ff ff ff" in t1 and "ff ff ff ff" in t2:
                ok("擦除验证通过")
            else:
                bad("擦除不彻底，建议重跑")
                return 1

        # ── 网络
        hr("[10] 配置 u-boot 网络")
        cmd(s, "setenv ipaddr %s" % UB_IP, 10, None, "ipaddr")
        cmd(s, "setenv serverip %s" % PC_IP, 10, None, "serverip")
        cmd(s, "setenv netmask 255.255.255.0", 10, None, "netmask")

        t, g, good = cmd(s, "ping %s" % PC_IP, 25, "alive", "ping")
        if "alive" not in t:
            bad("ping 不通")
            info("检查 PC 是否有 %s，网线是否插 LAN 口" % PC_IP)
            return 1
        ok("网络连通")

        # ── TFTP
        hr("[11] TFTP 传输固件（%.2f MB）" % (fw["size"] / 1048576.0))
        img_name = os.path.basename(fw["path"])
        t, g, good = cmd(s, "tftpboot 0x%X %s" % (LOAD_ADDR, img_name),
                         600, "Bytes transferred", "tftpboot")
        for l in srv.log:
            info("  " + l)
        if "Bytes transferred" not in t:
            bad("TFTP 传输失败")
            return 1
        ok("传输完成")

        # ── 验证
        hr("[12] 验证内存里的固件")
        t, g, _ = cmd(s, "md.b 0x%X 0x10" % LOAD_ADDR, 30, "d0 0d fe ed", "FIT 魔数")
        if "d0 0d fe ed" not in t:
            bad("FIT 魔数不对")
            return 1
        ok("FIT 魔数正确")

        t, g, _ = cmd(s, "iminfo 0x%X" % LOAD_ADDR, 60, None, "iminfo")
        if "0x48000000" not in t:
            info("⚠️  Load Address 不是 0x48000000，请确认固件")
        else:
            ok("Load Address 正确 (0x48000000)")

        # ── 写入
        hr("[13] 写入 flash（0x%X 字节）" % fw["size"])
        info("⚠️  不要断电！")
        t, g, good = cmd(s, "sf write 0x%X 0x%X 0x%X" % (LOAD_ADDR, FW_OFFSET, fw["size"]),
                         600, "Written: OK", "sf write")
        if "Written: OK" not in t:
            bad("写入失败")
            return 1
        ok("写入成功")

        # ── 校验
        hr("[14] 逐字节校验")
        t, g, good = cmd(s, "sf read 0x%X 0x%X 0x%X" % (CMP_ADDR, FW_OFFSET, fw["size"]),
                         300, "Read: OK", "sf read 回读")
        if "Read: OK" not in t:
            bad("回读失败")
            return 1
        t, g, good = cmd(s, "cmp.b 0x%X 0x%X 0x%X" % (LOAD_ADDR, CMP_ADDR, fw["size"]),
                         500, None, "cmp.b")
        if "were the same" not in t:
            bad("校验失败，数据不一致")
            return 1
        ok("✓✓✓ 校验通过")

        # ── 确认 rootfs 是 squashfs
        hr("[15] 确认 rootfs 区是 squashfs")
        cmd(s, "sf read 0x48000000 0x540000 0x10", 30, "Read: OK", "读 0x540000")
        t, g, _ = cmd(s, "md.b 0x48000000 0x10", 30, None, "应为 hs qs")
        if "68 73 71 73" in t:
            ok("rootfs 是 squashfs（正确）")
        else:
            info("⚠️  未看到 hsqs 标记，请核对")

        # ── reset
        hr("[16] 重启并抓启动日志")
        s.reset_input_buffer()
        s.write(b"reset\r")
        out = bytearray()
        t0 = last = time.time()
        while time.time() - t0 < 240:
            c = s.read(16384)
            if c:
                out += c
                last = time.time()
                print(c.decode("utf-8", "replace"), end="", flush=True)
            elif time.time() - last > 30 and len(out) > 0:
                break

        logfile = os.path.join(HERE, "boot.log")
        open(logfile, "wb").write(bytes(out))
        txt = bytes(out).decode("utf-8", "replace")

        hr("刷机结果")
        checks = {
            "rootfs 分区名正确": '"rootfs"' in txt,
            "非 ubi 分区名": '"ubi"' not in txt,
            "Linux 6.6 启动": "Linux version 6.6" in txt,
            "WiFi 初始化": "HW/SW Version" in txt,
            "无 Kernel panic": "Kernel panic" not in txt,
            "lan1 链路": "lan1: Link is Up" in txt,
            "uhttpd 启动": "uhttpd" in txt,
            "console 就绪": "activate this console" in txt,
            "品牌显示": "乔大仙" in txt,
        }
        for k, v in checks.items():
            print("  %-22s %s" % (k, "✓" if v else "✗"))
        print()
        info("日志: %s" % logfile)
        info("访问: http://192.168.2.1/")

        return 0 if checks["无 Kernel panic"] else 1

    finally:
        stop.set()
        s.close()
        srv.stop_flag = True


if __name__ == "__main__":
    sys.exit(main())
