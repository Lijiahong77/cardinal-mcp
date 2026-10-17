"""WSL 环境探测 —— 一次性摸清 Ubuntu 内部状况。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wslrun import run, WSL, DISTRO  # noqa: E402


def sh(cmd):
    return run([WSL, "-d", DISTRO, "--", "bash", "-lc", cmd])


def root_sh(cmd):
    return run([WSL, "-d", DISTRO, "-u", "root", "--", "bash", "-lc", cmd])


PROBES = [
    ("用户 / 家目录", "whoami; id -u; echo HOME=$HOME; echo PWD=$(pwd)"),
    ("发行版", "grep -E 'PRETTY_NAME|VERSION_ID' /etc/os-release"),
    ("内核", "uname -r"),
    ("CPU 核数", "nproc"),
    ("内存", "free -h"),
    ("磁盘", "df -h / /mnt/d"),
    ("写入测试", "echo ok-from-wsl > /tmp/_probe.txt && cat /tmp/_probe.txt"),
    ("sudo 是否免密", "sudo -n true 2>/dev/null && echo SUDO_NOPASSWD || echo SUDO_NEEDS_PASSWORD"),
    ("apt 源", "grep -rhE '^(URIs|deb )' /etc/apt/sources.list /etc/apt/sources.list.d/ 2>/dev/null | head -6"),
    ("联网 (清华源)", "timeout 10 curl -s -o /dev/null -w '%{http_code}' https://mirrors.tuna.tsinghua.edu.cn/ || echo NO_NET"),
    ("联网 (ubuntu官方)", "timeout 10 curl -s -o /dev/null -w '%{http_code}' http://archive.ubuntu.com/ || echo NO_NET"),
    ("git 是否已装", "git --version 2>&1 || echo NOT_INSTALLED"),
    ("gcc 是否已装", "gcc --version 2>&1 | head -1 || echo NOT_INSTALLED"),
    ("make 是否已装", "make --version 2>&1 | head -1 || echo NOT_INSTALLED"),
]

print("################ 默认用户身份 ################")
for name, cmd in PROBES:
    rc, out, err = sh(cmd)
    print(f"===== {name} (exit={rc}) =====")
    if out:
        print(out)
    if err:
        print("[stderr]", err)
    print()

print("################ root 身份（关键：能否免密执行）################")
for name, cmd in [
    ("root whoami", "whoami; id -u"),
    ("root 写 /usr 测试", "touch /usr/_roottest && rm -f /usr/_roottest && echo ROOT_WRITE_OK"),
]:
    rc, out, err = root_sh(cmd)
    print(f"===== {name} (exit={rc}) =====")
    if out:
        print(out)
    if err:
        print("[stderr]", err)
    print()
