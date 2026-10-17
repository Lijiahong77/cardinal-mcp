"""解码 wsl.exe 的输出（UTF-16），并可选地执行一条 wsl 命令。
用法:
    python wslout.py <文件路径>            # 解码已有文件
    python wslout.py --run "<wsl 参数>"    # 执行 wsl.exe 并解码输出
"""
import subprocess
import sys

WSL = r"C:\Windows\System32\wsl.exe"


def decode(raw: bytes) -> str:
    for enc in ("utf-16-le", "utf-8", "gbk"):
        try:
            t = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        if t and "\x00" not in t:
            return t.replace("\r\n", "\n").strip()
    return raw.decode("utf-8", errors="replace").strip()


def run(args: str) -> None:
    p = subprocess.run(WSL + " " + args, shell=True,
                       capture_output=True)
    print(f"[exit={p.returncode}]")
    out = decode(p.stdout)
    err = decode(p.stderr)
    if out:
        print("--- stdout ---")
        print(out)
    if err:
        print("--- stderr ---")
        print(err)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--run":
        run(sys.argv[2])
    elif len(sys.argv) >= 2:
        print(decode(open(sys.argv[1], "rb").read()))
    else:
        print(__doc__)
