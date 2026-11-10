#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
乔大仙 OpenWrt 汉化版 —— 一键刷机脚本

用法：
    python flash.py                     # 交互式，自动探测设备
    python flash.py --ip 192.168.2.1    # 指定 IP
    python flash.py --check             # 只检查，不刷

流程：
    1. 探测设备（LuCI 是否在线、SSH 是否可达）
    2. 校验固件（大小、SHA256、FIT 结构）
    3. 备份当前配置
    4. 上传固件
    5. 执行 sysupgrade（-n 不保留配置 / 默认保留）
    6. 等待重启并验证
"""
import sys
import io
import os
import json
import time
import hashlib
import argparse
import warnings
import subprocess

warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
FW = os.path.join(HERE, "out", "qiaodaxian-ew3000gx-sysupgrade.bin")

# 已知口令（依次尝试）
PASSWORDS = [
    "52249136d4296c2c",
    "qiaodaxian233",
    "root",
    "password",
    "",
]

DEFAULT_IPS = ["192.168.2.1", "192.168.1.1", "192.168.110.1"]


def hr(t=""):
    print("\n" + "=" * 64)
    if t:
        print(t)
        print("=" * 64)


def ok(s):
    print("  [OK]   " + s)


def bad(s):
    print("  [FAIL] " + s)


def info(s):
    print("  " + s)


# ══════════════════════════════════════════════════
# 1. 固件校验
# ══════════════════════════════════════════════════
def check_firmware():
    hr("[1] 固件校验")
    if not os.path.exists(FW):
        bad("固件不存在: %s" % FW)
        return None

    size = os.path.getsize(FW)
    info("路径   : %s" % FW)
    info("大小   : %d 字节 (%.2f MB)" % (size, size / 1048576.0))

    if size < 4 * 1048576:
        bad("文件太小，不是完整固件")
        return None
    if size > 20 * 1048576:
        bad("文件太大，超出 flash 分区")
        return None

    # SHA256
    h = hashlib.sha256()
    with open(FW, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest()
    info("SHA256 : %s" % digest)

    # FIT 魔数检查（D0 0D FE ED）
    with open(FW, "rb") as f:
        head = f.read(4)
    if head == b"\xd0\x0d\xfe\xed":
        ok("FIT 镜像结构正确")
    else:
        bad("不是 FIT 镜像（头部 %s）" % head.hex())
        return None

    # 品牌检查
    with open(FW, "rb") as f:
        data = f.read()
    try:
        txt = data.decode("utf-8", "ignore")
    except Exception:
        txt = ""
    if "乔大仙" in txt:
        ok("品牌字符串已写入")
    else:
        info("品牌字符串被压缩（正常，squashfs 用 xz）")

    ok("固件校验通过")
    return digest


# ══════════════════════════════════════════════════
# 2. 探测设备
# ══════════════════════════════════════════════════
def probe_http(ip, timeout=5):
    """HTTP 探测 LuCI"""
    import urllib.request
    import urllib.error
    url = "http://%s/cgi-bin/luci/" % ip
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status in (200, 302, 403)
    except urllib.error.HTTPError as e:
        return e.code in (200, 302, 403)
    except Exception:
        return False


def probe_ssh(ip, timeout=6):
    """SSH 探测 + 尝试口令，返回 (ok, password)"""
    try:
        import paramiko
    except ImportError:
        return False, None

    for pwd in PASSWORDS:
        try:
            t = paramiko.Transport((ip, 22))
            t.get_security_options().key_types = (
                "ssh-rsa", "rsa-sha2-256", "rsa-sha2-512",
                "ecdsa-sha2-nistp256", "ssh-ed25519",
            )
            t.start_client(timeout=timeout)
            t.auth_password("root", pwd)
            t.close()
            return True, pwd
        except paramiko.AuthenticationException:
            continue
        except Exception:
            break
    return False, None


def detect_device(ip_hint=None):
    hr("[2] 探测设备")

    cands = [ip_hint] if ip_hint else DEFAULT_IPS
    found = None

    for ip in cands:
        info("探测 %s ..." % ip)
        http_ok = probe_http(ip)
        if http_ok:
            ok("%s LuCI 在线" % ip)
            found = ip
            break
        else:
            info("  LuCI 无响应")

    if not found:
        bad("没找到在线设备")
        info("请确认：")
        info("  1. 电脑已连到路由器（LAN 口或 WiFi）")
        info("  2. 路由器 IP 是 %s 之一" % " / ".join(DEFAULT_IPS))
        info("  3. 或者用 --ip 指定")
        return None, None

    # SSH 探测
    info("尝试 SSH 登录 ...")
    ssh_ok, pwd = probe_ssh(found)
    if ssh_ok:
        ok("SSH 可达，口令: %s" % (pwd if pwd else "(空)"))
    else:
        info("SSH 不可用（将走 LuCI 上传方式）")

    return found, pwd if ssh_ok else None


# ══════════════════════════════════════════════════
# 3. SSH 方式刷机
# ══════════════════════════════════════════════════
def flash_via_ssh(ip, pwd, keep_config=True):
    hr("[3] 通过 SSH 刷机")
    import paramiko

    t = paramiko.Transport((ip, 22))
    t.get_security_options().key_types = (
        "ssh-rsa", "rsa-sha2-256", "rsa-sha2-512",
        "ecdsa-sha2-nistp256", "ssh-ed25519",
    )
    t.start_client(timeout=15)
    t.auth_password("root", pwd)

    def run(cmd, wait=3):
        ch = t.open_session()
        ch.exec_command(cmd)
        out = b""
        end = time.time() + 120
        while time.time() < end:
            time.sleep(0.3)
            while ch.recv_ready():
                out += ch.recv(65535)
            if ch.exit_status_ready() and not ch.recv_ready():
                break
        while ch.recv_ready():
            out += ch.recv(65535)
        return out.decode("utf-8", "replace")

    # 3.1 设备信息
    info("读取设备信息 ...")
    rel = run("cat /etc/openwrt_release 2>/dev/null")
    info("当前固件:")
    for line in rel.strip().split("\n")[:8]:
        if line.strip():
            info("  " + line.strip())

    board = run("ubus call system board 2>/dev/null")
    try:
        bj = json.loads(board)
        info("型号: %s" % bj.get("model", "?"))
        info("内核: %s" % bj.get("kernel", "?"))
    except Exception:
        pass

    # 3.2 检查空间
    info("检查 /tmp 空间 ...")
    df = run("df -k /tmp | tail -1")
    info("  " + df.strip())
    try:
        avail_kb = int(df.split()[3])
        need_kb = os.path.getsize(FW) // 1024 + 2048
        if avail_kb < need_kb:
            bad("/tmp 空间不足（需要 %d KB，只有 %d KB）" % (need_kb, avail_kb))
            t.close()
            return False
        ok("空间充足（%d KB 可用）" % avail_kb)
    except Exception:
        info("  无法解析，跳过")

    # 3.3 备份配置
    info("备份当前配置到 /tmp/backup.tar.gz ...")
    bk = run("sysupgrade -b /tmp/backup-$(date +%s).tar.gz 2>&1 && ls -l /tmp/backup-*.tar.gz")
    info("  " + bk.strip().replace("\n", "\n  "))

    # 3.4 上传固件
    info("上传固件（%.2f MB）..." % (os.path.getsize(FW) / 1048576.0))
    sftp = t.open_sftp_client()
    remote = "/tmp/firmware.bin"
    t0 = time.time()

    def cb(done, total):
        pct = done * 100 // total
        bar = "#" * (pct // 4) + "." * (25 - pct // 4)
        sys.stdout.write("\r  [%s] %3d%%  %.1f/%.1f MB" % (
            bar, pct, done / 1048576.0, total / 1048576.0))
        sys.stdout.flush()

    sftp.put(FW, remote, callback=cb)
    sftp.close()
    print()
    ok("上传完成，耗时 %.1f 秒" % (time.time() - t0))

    # 3.5 校验远端文件
    info("校验远端 SHA256 ...")
    local_h = hashlib.sha256()
    with open(FW, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            local_h.update(c)
    remote_h = run("sha256sum %s | cut -d' ' -f1" % remote).strip()
    if local_h.hexdigest() == remote_h:
        ok("SHA256 一致")
    else:
        bad("SHA256 不一致！")
        info("  本地: %s" % local_h.hexdigest())
        info("  远端: %s" % remote_h)
        t.close()
        return False

    # 3.6 执行 sysupgrade
    hr("[4] 执行 sysupgrade")
    flag = "" if keep_config else "-n"
    info("命令: sysupgrade %s /tmp/firmware.bin" % flag)
    info("（设备将重启，SSH 会断开，这是正常的）")
    print()

    cmd = "sysupgrade %s /tmp/firmware.bin > /tmp/sysupgrade.log 2>&1 &" % flag
    try:
        run(cmd, wait=2)
    except Exception:
        pass

    t.close()
    ok("已下发刷机命令")

    # 3.7 等待重启
    hr("[5] 等待设备重启")
    info("预计 90-150 秒 ...")
    for i in range(180, 0, -5):
        time.sleep(5)
        if probe_http(ip, timeout=3):
            ok("设备已上线！（等待 %d 秒）" % (180 - i + 5))
            return True
        sys.stdout.write("\r  等待中... 剩余 %d 秒" % i)
        sys.stdout.flush()
    print()
    bad("超时未上线")
    info("请检查：")
    info("  1. 串口看启动日志")
    info("  2. 手动访问 http://%s/" % ip)
    return False


# ══════════════════════════════════════════════════
# 4. LuCI 上传方式（SSH 不可用时）
# ══════════════════════════════════════════════════
def flash_via_luci(ip):
    hr("[3] LuCI 上传方式")
    info("SSH 不可用，请手动操作：")
    info("")
    info("  1. 浏览器打开  http://%s/cgi-bin/luci/" % ip)
    info("  2. 登录后进入：系统 → 备份与更新 → 刷写固件")
    info("  3. 选择文件：%s" % FW)
    info("  4. 取消勾选「保留配置」（如果要全新安装）")
    info("  5. 点击「刷写固件」")
    info("")
    info("注意：刷写过程中不要断电，约 2-3 分钟")
    return False


# ══════════════════════════════════════════════════
# 5. 刷后验证
# ══════════════════════════════════════════════════
def verify_after(ip, pwd):
    hr("[6] 刷机后验证")
    time.sleep(5)

    ok_ssh, p = probe_ssh(ip)
    if not ok_ssh:
        info("SSH 暂不可用，用 HTTP 验证")
        if probe_http(ip):
            ok("LuCI 在线")
        return

    import paramiko
    t = paramiko.Transport((ip, 22))
    t.get_security_options().key_types = ("ssh-rsa", "rsa-sha2-256", "rsa-sha2-512")
    t.start_client(timeout=15)
    t.auth_password("root", p)

    def run(cmd):
        ch = t.open_session()
        ch.exec_command(cmd)
        out = b""
        end = time.time() + 30
        while time.time() < end:
            time.sleep(0.3)
            while ch.recv_ready():
                out += ch.recv(65535)
            if ch.exit_status_ready() and not ch.recv_ready():
                break
        return out.decode("utf-8", "replace")

    rel = run("cat /etc/openwrt_release")
    info("新固件信息:")
    for line in rel.strip().split("\n"):
        if line.strip():
            info("  " + line.strip())

    hn = run("uci get system.@system[0].hostname").strip()
    info("主机名: %s" % hn)

    if "乔大仙" in rel or "乔大仙" in hn:
        ok("品牌验证通过")
    else:
        info("品牌未生效（可能需要清缓存）")

    t.close()


# ══════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(description="乔大仙 OpenWrt 汉化版 一键刷机")
    ap.add_argument("--ip", help="路由器 IP（默认自动探测）")
    ap.add_argument("--check", action="store_true", help="只检查不刷机")
    ap.add_argument("--no-keep", action="store_true", help="不保留配置（全新安装）")
    ap.add_argument("--force", action="store_true", help="跳过确认")
    args = ap.parse_args()

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║     乔大仙 OpenWrt 汉化版  ·  一键刷机                   ║")
    print("║     Ruijie RG-EW3000GX  ·  MediaTek MT7981               ║")
    print("╚══════════════════════════════════════════════════════════╝")

    digest = check_firmware()
    if not digest:
        return 1

    if args.check:
        hr("仅检查模式，退出")
        return 0

    ip, pwd = detect_device(args.ip)
    if not ip:
        return 1

    if not args.force:
        hr("确认")
        info("设备     : %s" % ip)
        info("固件     : %s" % os.path.basename(FW))
        info("大小     : %.2f MB" % (os.path.getsize(FW) / 1048576.0))
        info("保留配置 : %s" % ("否（全新安装）" if args.no_keep else "是"))
        info("刷机方式 : %s" % ("SSH" if pwd is not None else "LuCI 手动"))
        print()
        try:
            ans = input("  确认刷机？输入 yes 继续: ").strip().lower()
        except EOFError:
            ans = ""
        if ans not in ("yes", "y"):
            info("已取消")
            return 0

    if pwd is not None:
        success = flash_via_ssh(ip, pwd, keep_config=not args.no_keep)
        if success:
            verify_after(ip, pwd)
    else:
        flash_via_luci(ip)

    hr("结束")
    info("访问 http://%s/ 查看" % ip)
    return 0


if __name__ == "__main__":
    sys.exit(main())
