# -*- coding: utf-8 -*-
"""winprobe.py —— 探测本机显示缩放 + 找指定窗口（Cardinal）

用途：排班前先知道「一屏到底能放多少格」。
  - 系统 DPI 缩放 -> 逻辑分辨率（Cardinal 的可用视野）
  - 枚举顶层窗口，定位 Cardinal 的窗口矩形

用法:
    python winprobe.py [窗口标题关键字]
"""
import ctypes
import ctypes.wintypes as wt
import sys

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()

WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
SW_RESTORE = 9


def dpi_info():
    try:
        dpi = user32.GetDpiForSystem()
    except AttributeError:
        dpi = 96
    sx = user32.GetSystemMetrics(0)
    sy = user32.GetSystemMetrics(1)
    scale = dpi / 96.0
    print("系统 DPI          : %d  (缩放 %d%%)" % (dpi, round(scale * 100)))
    print("物理分辨率        : %d x %d" % (sx, sy))
    print("逻辑分辨率(可用格): %d x %d 格    <- 1 格 = 15px"
          % (int(sx / scale / 15), int(sy / scale / 15)))
    return scale


def find_windows(keyword):
    hits = []

    def cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value
        if keyword.lower() in title.lower():
            r = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            hits.append((hwnd, title, cls.value, r))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return hits


def main():
    keyword = sys.argv[1] if len(sys.argv) > 1 else "Cardinal"
    dpi_info()
    print("-" * 58)
    hits = find_windows(keyword)
    if not hits:
        print("没有找到标题含 %r 的可见窗口 —— 它可能没运行 / 被最小化" % keyword)
        return 1
    for hwnd, title, cls, r in hits:
        w, h = r.right - r.left, r.bottom - r.top
        print("hwnd=%-9s  %-38s  class=%s" % (hwnd, title[:38], cls))
        print("   位置 (%d,%d)  尺寸 %d x %d px  =  %.0f x %.0f 格"
              % (r.left, r.top, w, h, w / 15.0, h / 15.0))
        if "--front" in sys.argv:
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            print("   -> 已置前")
    return 0


if __name__ == "__main__":
    sys.exit(main())
