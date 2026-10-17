"""WSL 驱动工具 —— 绕过 Git-Bash 的路径转换，直连 wsl.exe。

为什么要有这个：从 Git-Bash 里调 wsl.exe 时，以 / 开头的参数会被 MSYS
擅自改写成 Windows 路径（例：/etc/os-release -> C:/Users/.../etc/os-release），
导致命令失败。用 Python 的 subprocess 直接拉起 wsl.exe 就没有这个转换。

用法:
    python wslrun.py --raw   "--list --verbose"      # 直接调 wsl.exe
    python wslrun.py --sh    "cat /etc/os-release"   # 在 Ubuntu 里跑（默认用户）
    python wslrun.py --root  "apt-get update"        # 在 Ubuntu 里跑（root）
"""
import subprocess
import sys

WSL = r"C:\Windows\System32\wsl.exe"
DISTRO = "Ubuntu-26.04"


def decode(raw: bytes) -> str:
    """wsl.exe 的输出是 UTF-16；WSL 里 Linux 命令的输出是 UTF-8。两种都要认。"""
    if not raw:
        return ""
    if b"\x00" in raw:  # 出现 NUL 字节 → 判定为 UTF-16
        for enc in ("utf-16-le", "utf-16-be"):
            try:
                t = raw.decode(enc)
                if "\x00" not in t:
                    return t.replace("\r\n", "\n").strip()
            except UnicodeDecodeError:
                pass
    for enc in ("utf-8", "gbk"):
        try:
            t = raw.decode(enc)
            if "\x00" not in t:
                return t.replace("\r\n", "\n").strip()
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace").strip()


def run(argv, timeout=None):
    p = subprocess.run(argv, capture_output=True, timeout=timeout)
    return p.returncode, decode(p.stdout), decode(p.stderr)


def main():
    a = sys.argv[1:]
    if len(a) < 2:
        print(__doc__)
        return
    mode, payload = a[0], a[1]
    if mode == "--raw":
        argv = [WSL] + payload.split()
    elif mode == "--sh":
        argv = [WSL, "-d", DISTRO, "--", "bash", "-lc", payload]
    elif mode == "--root":
        argv = [WSL, "-d", DISTRO, "-u", "root", "--", "bash", "-lc", payload]
    else:
        print(__doc__)
        return
    rc, out, err = run(argv)
    print(f"[exit={rc}]")
    if out:
        print(out)
    if err:
        print("--- stderr ---")
        print(err)


if __name__ == "__main__":
    main()
