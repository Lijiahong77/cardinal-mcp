"""D 盘空间哨兵 —— 编译期间持续盯盘，跌破阈值立刻报警（可选自动终止编译）。

用法:
    python disk_watch.py [阈值MB] [监控时长秒] [--kill]

例:
    python disk_watch.py 2048 3600          # 低于 2 GB 就报警，盯 1 小时
    python disk_watch.py 2048 3600 --kill   # 低于 2 GB 并自动杀掉 make

关键指标有两个：
  1. D 盘剩余空间（这是你真正在意的）
  2. ext4.vhdx 文件大小（这个才是"吃盘"的真身 —— vhdx 不涨，D 盘就不会少）
"""
import io
import os
import subprocess
import shutil
import sys
import time

VHDX = r'D:\WSL\Ubuntu-26.04\ext4.vhdx'
LOG = r'D:\Cardinal\tmp\disk_watch.log'
INTERVAL = 15


def snap():
    """返回 (D 盘剩余字节, vhdx 字节)"""
    free = shutil.disk_usage('D:/').free
    v = os.path.getsize(VHDX) if os.path.exists(VHDX) else -1
    return free, v


def log(text):
    io.open(LOG, 'a', encoding='utf-8').write(text + '\n')


def main():
    thr_mb = int(sys.argv[1]) if len(sys.argv) > 1 else 2048
    dur_s = int(sys.argv[2]) if len(sys.argv) > 2 else 3600
    do_kill = '--kill' in sys.argv

    log('')
    log('=== 哨兵启动 %s  阈值=%d MB  时长=%ds  kill=%s ==='
        % (time.strftime('%Y-%m-%d %H:%M:%S'), thr_mb, dur_s, do_kill))

    f0, v0 = snap()
    log('起始: D_free=%.0f MB  vhdx=%.1f GB' % (f0 / 2**20, v0 / 2**30))

    t_end = time.time() + dur_s
    n = 0
    tripped = False
    while time.time() < t_end:
        f, v = snap()
        n += 1
        log('%s  D_free=%7.0f MB   vhdx=%7.1f GB   vhdx变化=%+7.0f MB'
            % (time.strftime('%H:%M:%S'), f / 2**20, v / 2**30, (v - v0) / 2**20))

        if f / 2**20 < thr_mb:
            tripped = True
            log('!! 触发阈值：D 盘剩余 %.0f MB < %d MB' % (f / 2**20, thr_mb))
            if do_kill:
                subprocess.run(['wsl.exe', '-u', 'root', 'pkill', '-f', 'make'],
                               capture_output=True)
                log('!! 已向 WSL 内的 make 发送终止信号')
            break
        time.sleep(INTERVAL)

    f1, v1 = snap()
    log('=== 哨兵结束%s：D_free %+.0f MB   vhdx %+.0f MB ==='
        % ('（已触发）' if tripped else '', (f1 - f0) / 2**20, (v1 - v0) / 2**20))
    print('D_free %.0f MB -> %.0f MB (%+.0f MB); vhdx %.1f GB -> %.1f GB (%+.0f MB)'
          % (f0 / 2**20, f1 / 2**20, (f1 - f0) / 2**20,
             v0 / 2**30, v1 / 2**30, (v1 - v0) / 2**20))


main()
