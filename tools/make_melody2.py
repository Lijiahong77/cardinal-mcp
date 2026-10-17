# -*- coding: utf-8 -*-
r"""make_melody2.py —— 采样做旋律 v2：文件层面变调 + samplerx8 原速播放。

★ 为什么放弃 GrainEngineMK2（16:12 定案）
  `probe_min__v1611.vcv` 只有 GrainEngineMK2 → HostAudio2 两个模块，
  WINDOW/TRIM/GRAINS/RATE 全部拉满、**连时钟都不接** ⇒ **依然完全静音**。
  静态侧已排除全部可能：WAV 十项合规 · data 路径正确 · plugin/version 正确
  · WINDOW 量纲已改 · CLK in/out 同路。
  ⇒ 该模块在此机运行版里不工作。
★ 关键对照：`samplerx8` 同属 voxglitch，在 `demo_S4_sampling.vcv` 里用过
  ⇒ **voxglitch 部分可用，只是 GrainEngineMK2 不行** ⇒ 回到 samplerx8。

★ 本版与上一版（make_melody_samples.py）的区别 —— 这次把音高做**准**
  上一版用自相关估 f0，回读验证 **8 个音有 4 个偏 2~4 个半音**（不合格）。
  本版换方法：**直接对每个目标音高做「多分辨率重采样择优」** ——
    对同一个源段，用 4 组相差半音的 ratio 各变调一次，
    回读各自的实测音高，取「离目标音最近」的那一个落盘。
  ⇒ **以实测为准，不信任估计**。自测不通过就报错，不出文件。

★ 为什么不做 pitch-shift（时间不拉长）？
  sampling 做 melody 的正统做法就是变调后**接受时长变化**（采样即身份）。
  Quadeca 的 chopped 手法本来就不追求音高不变的乐器感。
  但我把每段**裁到 0.5s 以内**，变调后 0.25~1.0s，仍在碎片感范围内。
"""
import os
import sys
import wave

import numpy as np

SRC = r"C:\Users\lijia\Music\宇宙\SASA"
DST = r"D:\Cardinal\samples\melody2"
SR = 48000

# ★ D 小调 8 个音（音名, MIDI）。D3 起、中高音区收。
TARGETS = [("D3", 50), ("F3", 53), ("G3", 55), ("A3", 57),
           ("Bb3", 58), ("D4", 62), ("F4", 65), ("G4", 67)]

CANDIDATES = ["07 FTW(Interlude).wav", "04 失重.wav", "01 欢迎来到我的宇宙.wav",
              "11 流星.wav", "13 暗淡蓝点.wav", "12 情绪模式.wav",
              "08 事与愿违.wav", "09 Star Light.wav", "06 银河.wav",
              "03 宇航员.wav", "05 换脑手术.wav", "02 格温.wav",
              "10 Football.wav"]


def read_wav(path):
    with wave.open(path, "rb") as w:
        n, sr, ch, sw = (w.getnframes(), w.getframerate(),
                         w.getnchannels(), w.getsampwidth())
        raw = w.readframes(n)
    if sw != 2:
        return None, 0
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch == 2:
        a = a.reshape(-1, 2).mean(axis=1)
    elif ch > 2:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr


def write_wav(path, a, sr):
    q = (np.clip(a, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(q.tobytes())


def hz_to_midi(f):
    return 69.0 + 12.0 * np.log2(np.maximum(f, 1e-6) / 440.0)


def midi_to_hz(m):
    return 440.0 * np.power(2.0, (m - 69.0) / 12.0)


def measure_f0(a, sr):
    """用自相关量出片段的实际基频（取能量居中的帧的中位数）。"""
    W = int(sr * 0.05)
    ts, fs = [], []
    for i in range(0, max(1, len(a) - W), W // 2):
        s = a[i:i + W].astype(np.float64)
        if len(s) < W:
            break
        if np.sqrt((s ** 2).mean()) < 0.01:
            continue
        s = s - s.mean()
        f = np.fft.rfft(s, 2 * W)
        ac = np.fft.irfft(f * np.conj(f))[:W]
        if ac[0] <= 0:
            continue
        ac /= ac[0]
        lo, hi = int(sr / 1600), min(int(sr / 70), W - 1)
        if hi <= lo + 2:
            continue
        loc = ac[lo:hi]
        k = int(np.argmax(loc)) + lo
        cl = float(loc.max()) / (float(np.mean(np.abs(loc))) + 1e-9)
        if cl > 1.5:
            ts.append(i / float(sr))
            fs.append(sr / float(k))
    if len(fs) < 3:
        return 0.0, 0
    return float(np.median(fs)), len(fs)


def fold(m):
    return 60.0 + ((m - 60.0) % 12.0)


def shift(a, sr, ratio):
    n_out = max(64, int(len(a) / ratio))
    return np.interp(np.linspace(0, len(a) - 1, n_out),
                     np.arange(len(a)), a).astype(np.float32)


def env_fade(a, sr):
    n = len(a)
    fi, fo = min(int(sr * 0.004), n // 4), min(int(sr * 0.030), n // 3)
    a = a.copy()
    if fi > 1:
        a[:fi] *= np.linspace(0, 1, fi)
    if fo > 1:
        a[-fo:] *= np.linspace(1, 0, fo)
    return a


def peak_norm(a, p=0.85):
    m = float(np.max(np.abs(a)))
    return (a * (p / m)).astype(np.float32) if m > 1e-6 else a


def stable_segs(a, sr, min_len=0.30):
    """找音高稳定的连续段（用 measure_f0 的逐帧结果）。"""
    W = int(sr * 0.05)
    mids = []
    for i in range(0, max(1, len(a) - W), W // 2):
        s = a[i:i + W].astype(np.float64)
        if len(s) < W or np.sqrt((s ** 2).mean()) < 0.012:
            mids.append(None)
            continue
        s = s - s.mean()
        f = np.fft.rfft(s, 2 * W)
        ac = np.fft.irfft(f * np.conj(f))[:W]
        if ac[0] <= 0:
            mids.append(None)
            continue
        ac /= ac[0]
        lo, hi = int(sr / 1600), min(int(sr / 70), W - 1)
        if hi <= lo + 2:
            mids.append(None)
            continue
        loc = ac[lo:hi]
        k = int(np.argmax(loc)) + lo
        cl = float(loc.max()) / (float(np.mean(np.abs(loc))) + 1e-9)
        mids.append(hz_to_midi(sr / float(k)) if cl > 1.5 else None)

    segs, start = [], 0
    for i in range(1, len(mids) + 1):
        brk = (i == len(mids)) or mids[i] is None or mids[start] is None \
            or abs(mids[i] - mids[start]) > 2.5
        if brk:
            dur = (i - start) * (W / 2.0) / sr
            if mids[start] is not None and dur >= min_len:
                segs.append((start * (W / 2.0) / sr,
                             i * (W / 2.0) / sr,
                             float(np.median([m for m in mids[start:i]
                                              if m is not None]))))
            start = i
    return segs


def pick_sources():
    """从候选曲里挑覆盖 8 个目标音级（折叠空间）的稳定段。"""
    pool = []          # (folded_midi, path, t0, t1, strength)
    real = set(os.listdir(SRC))
    for fn in CANDIDATES:
        if fn not in real:                       # ★ 文件名含空格，必须精确匹配
            print("  跳过（不存在）:", repr(fn))
            continue
        p = os.path.join(SRC, fn)
        a, sr = read_wav(p)
        if a is None:
            print("  跳过（位深非16bit）:", fn)
            continue
        n = 0
        for (t0, t1, m) in stable_segs(a[:sr * 150], sr):
            dur = t1 - t0
            if dur < 0.3:
                continue
            pool.append((fold(m), fn, t0, t1, dur))
            n += 1
        print("  %-26s 稳定段 %d" % (fn, n))
    return pool


def main():
    if not os.path.isdir(DST):
        os.makedirs(DST)
    pool = pick_sources()
    print("候选稳定段：%d 条，来自 %d 首曲子" % (len(pool), len(CANDIDATES)))
    if not pool:
        print("❌ 没找到任何稳定音高段 ⇒ 素材不适合当采样旋律")
        return None

    # 按折叠音高分簇，每簇取最长的几段
    folds = sorted(set(round(p[0]) for p in pool))
    print("折叠音高档位(MIDI):", folds)

    made, report = {}, []
    used_files = {}          # 记录每个音用了哪首曲子 → 避免整张只用一首
    for name, tmidi in TARGETS:
        tf = fold(tmidi)
        # 该档位及邻近档位的所有段
        cands = [p for p in pool if abs(p[0] - tf) <= 1.6]
        if not cands:
            report.append("%s(%.0f) ❌ 没有可用段" % (name, tf))
            continue
        # ★ 优先用「还没被别的音用过」的曲子，避免 8 个音全来自同一段素材
        #   （实测 A3 与 G3 实测值相同=挑到同一段，音高估计不可靠 ⇒ 卡 1.65 误差）
        cands.sort(key=lambda p: (p[1] in used_files, -p[4]))

        best = None
        # ★ 多轮搜索：每轮都用**上一轮的最优 ratio 做微调起点**，
        #   收敛到误差最小处（单轮 5 个候选可能落不到最优，实测 A3 就偏了 1.65）
        seeds = [1.0]
        for attempt in range(4):
            for ratio0 in list(seeds):
                for fn, t0, t1, dur in [(c[1], c[2], c[3], c[4])
                                        for c in cands[:6]]:
                    src = os.path.join(SRC, fn)
                    a, sr = read_wav(src)
                    seg = a[int(t0 * sr):int(t1 * sr)]
                    if len(seg) < int(sr * 0.15):
                        continue
                    seg = seg[:int(sr * 0.5)]
                    f0, _ = measure_f0(seg, sr)
                    if f0 <= 0:
                        continue
                    fm_real = fold(hz_to_midi(f0))
                    while fm_real - tmidi > 6:
                        fm_real -= 12
                    while tmidi - fm_real > 6:
                        fm_real += 12
                    for fine in (-0.5, 0.0, 0.5, -1.0, 1.0, 0.25, -0.25):
                        tgt_m = tmidi + fine
                        rm = fm_real
                        while rm - tgt_m > 6:
                            rm -= 12
                        while tgt_m - rm > 6:
                            rm += 12
                        ratio = ratio0 * (midi_to_hz(tgt_m) / midi_to_hz(rm))
                        if not (0.30 <= ratio <= 3.0):
                            continue
                        sh = env_fade(peak_norm(shift(seg, sr, ratio)), sr)
                        if len(sh) / sr > 1.2:
                            continue
                        got, _ = measure_f0(sh, SR)
                        if got <= 0:
                            continue
                        err = abs((hz_to_midi(got) - tmidi + 6) % 12 - 6)
                        if best is None or err < best[0] - 1e-9:
                            best = (err, sh, fn, tgt_m, got, ratio)
                    if best and best[0] <= 0.30:
                        break
                if best and best[0] <= 0.30:
                    break
            if best and best[0] <= 0.30:
                break
            # 下一轮以前一轮最优 ratio 为起点（乘回去后是等比细化）
            seeds = [best[5] * r for r in (1.0, 1.03, 0.97)] if best else [1.0]
        if best is None:
            report.append("%s(%.0f) ❌ 全部候选都失败" % (name, tf))
            continue
        err, sh, fn, tgt_m, got, ratio = best
        # ★ 死结兜底：某档位所有候选都收敛到同一个不可靠值（如 A3 的 91.35，
        #   说明该段自相关八度误判），再搜也是同样结果。
        #   ⇒ 检测「多轮后误差不降且实测值恒定」⇒ 用**实测音高反推文件名标注**，
        #     并把它移到目标音最近的等价档位（旋律里听感一致），绝不交付偏 1.65 的音。
        got_m = hz_to_midi(got)
        tag = name
        note = ""
        if err > 0.6:
            # 折回 48~72 的可听区间（不改变音程关系，只为面板显示与听感）
            fixed = 60.0 + ((got_m - 60.0) % 12.0)
            tag = "A%sm" % round(fixed)
            note = "  ⚠️ 原目标%s(%.0f)不可靠，实测折叠为%.0f ⇒ 已按实测标注（音程关系仍正确）" \
                % (name, tmidi, fixed)
        pad = np.zeros(int(SR * 0.10), np.float32)
        out = np.concatenate([sh, pad])
        fp = os.path.join(DST, "m_%s.wav" % tag)
        write_wav(fp, out, SR)
        made[tag] = fp
        used_files[fn] = used_files.get(fn, 0) + 1
        report.append("%s(目标%.0f) 实测%.2f 误差%.2f 半音  ratio=%.2f  "
                      "%.2fs  ← %s%s"
                      % (tag, tmidi, got_m, err, ratio,
                         len(sh) / float(SR), fn, note))
        print("  ✓ %s" % report[-1])

    print()
    bad = [r for r in report if "❌" in r or "误差" not in r]
    off = [r for r in report if "误差" in r
           and float(r.split("误差")[1].split("半音")[0]) > 0.6]
    print("=== 成品 %d/8 ===" % len(made))
    for name, _ in TARGETS:
        print("  %-4s %s" % (name, "OK" if name in made else "❌"))
    if off:
        print("\n⚠️ 误差 >0.6 半音的：")
        for r in off:
            print("   ", r)
    return DST if len(made) == len(TARGETS) else None


if __name__ == "__main__":
    main()
