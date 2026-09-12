# -*- coding: utf-8 -*-
"""shot.py —— 纯标准库屏幕截图（Windows GDI + 手写 PNG）

用途：让 AI 能「看见」李屏幕上 Cardinal 的实际渲染，
而不是靠猜坐标。零依赖，只用 ctypes / zlib / struct。

用法:
    python shot.py [输出路径] [最大宽度]

默认输出到 D:\\Cardinal\\refs\\_screen_now.png，最长边缩到 1400。
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
import zlib

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

SRCCOPY = 0x00CC0020
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long), ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


def grab():
    """抓全屏（含多显示器虚拟桌面），返回 (宽, 高, BGRA bytes，自上而下)。"""
    user32.SetProcessDPIAware()
    x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

    hdc = user32.GetDC(0)
    memdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(memdc, bmp)
    ok = gdi32.BitBlt(memdc, 0, 0, w, h, hdc, x, y, SRCCOPY)
    if not ok:
        raise RuntimeError("BitBlt 失败")

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth = w
    bi.biHeight = -h          # 负值 = 自上而下
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0

    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(memdc, bmp, 0, h, buf, ctypes.byref(bi), 0)

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(memdc)
    user32.ReleaseDC(0, hdc)
    return w, h, buf.raw


def write_png(path, w, h, rows):
    """rows: 每行 RGB bytes（长 3*w）。"""
    raw = b"".join(b"\x00" + r for r in rows)

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    blob = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(blob)
    return len(blob)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else r"D:\Cardinal\refs\_screen_now.png"
    maxw = int(sys.argv[2]) if len(sys.argv) > 2 else 1400

    W, H, bgra = grab()
    step = max(1, -(-W // maxw))          # 向上取整的降采样步长
    ow, oh = W // step, H // step
    rows = []
    for oy in range(oh):
        sy = oy * step
        base = sy * W * 4
        row = bytearray(ow * 3)
        for ox in range(ow):
            i = base + ox * step * 4
            row[ox * 3 + 0] = bgra[i + 2]   # B -> R
            row[ox * 3 + 1] = bgra[i + 1]   # G
            row[ox * 3 + 2] = bgra[i + 0]   # R -> B
        rows.append(bytes(row))
    n = write_png(out, ow, oh, rows)
    print("屏幕 %dx%d -> %dx%d (step %d) -> %s  %d bytes"
          % (W, H, ow, oh, step, out, n))


if __name__ == "__main__":
    main()
