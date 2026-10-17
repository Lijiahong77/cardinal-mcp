# -*- coding: utf-8 -*-
r"""make_melody_samples.py —— 从李自己的曲子（SASA）里切出**有音高的单音**，
变调成 D 小调音阶，供采样器原速播放当旋律用。

★ 为什么必须在文件层面变调
  `samplerx8` 原速播放，**采样器不改音高**（它只有 TRIGGER 和 POSITION 输入，
  源码枚举里没有 pitch/ VOctave CV）。所以想让采样"唱歌"，
  唯一的办法是：**文件里就存着正确的音高**。

★ 音高怎么找才靠谱（不猜绝对值，只算音程）
  自相关估f0 在这种带混响的曲子上极易跳八度（我第一版就全撞在1200Hz 上限）。
  所以：
    ① 只取**连续 0.35s 以上音高稳定**的段（波动 < 0.6 半音）
    ② **八度归一**：把每个候选折叠进 [60, 72)（一个八度窗口）
    ③ **音程聚类**：按 MIDI 距离聚成簇，取出现次数最多的 8 个 —— 这就是这首歌的调内音级
    ④ 每个簇的 f0 取中位数 → 该簇的代表音高
  ⇒ 得到的 8 个音是**相对关系**（音程）可靠，绝对值可能差八度，
     但我们本来就要重映射到 D 小调，绝对值不重要。

★ 变调方式 = 重采样（改变播放速率）
  读 wav → 按 r = 目标f0/原f0 重采样 → 播放时长同步缩短/拉长。
  这是采样音乐里最常见的 pitch-shift，也是 Quadeca「废弃曲子重新编排」的做法。
"""
import os
import sys
import wave

import numpy as np

SRC = r"C:\Users\lijia\Music\宇宙\SASA"
DST = r"D:\Cardinal\samples\melody"
SR_OUT = 48000

# ★ D 小调（D natural minor）：D E F G A Bb C
#   8 个位覆盖：D3E3 F3 G3 A3 Bb3 C4 D4 —— 低八度打底+ 高音区封顶
TARGET_MIDI = [50, 52, 53, 55, 57, 58, 62, 65]
TARGET_NAME = ["D3", "E3", "F3", "G3", "A3", "Bb3", "D4", "F4"]

# ★ 候选曲：优先有稳定音高的（_sana_pitch 扫出来的）
CANDIDATES = ["07 FTW(Interlude).wav", "04 失重.wav", "01 欢迎来到我的宇宙.wav"]


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
    q = np.clip(a, -1.0, 1.0)
    q = (q * 32767.0).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(q.tobytes())


def hz_to_midi(f):
    return 69.0 + 12.0 * np.log2(np.maximum(f, 1e-6) / 440.0)


def midi_to_hz(m):
    return 440.0 * np.power(2.0, (m - 69.0) / 12.0)


def f0_track(a, sr, hop=0.01, win=0.05):
    """逐帧估 f0，返回 (times, f0, rms, clarity)。"""
    W, H = int(sr * win), int(sr * hop)
    ts, f0s, rmss, cls = [], [], [], []
    for i in range(0, max(0, len(a) - W), H):
        s = a[i:i + W].astype(np.float64)
        if len(s) < W:
            break
        rms = float(np.sqrt((s ** 2).mean()))
        if rms < 0.012:
            continue                       # 静音段不参与
        s = s - s.mean()
        f = np.fft.rfft(s, 2 * W)
        ac = np.fft.irfft(f * np.conj(f))[:W]
        if ac[0] <= 0:
            continue
        ac /= ac[0]
        lo, hi = int(sr / 1500.0), min(int(sr / 70.0), W - 1)
        if hi <= lo + 2:
            continue
        loc = ac[lo:hi]
        k = int(np.argmax(loc)) + lo
        clarity = float(loc.max()) / (float(np.mean(np.abs(loc))) + 1e-9)
        ts.append(i / float(sr))
        f0s.append(sr / float(k))
        rmss.append(rms)
        cls.append(clarity)
    return (np.array(ts), np.array(f0s), np.array(rmss), np.array(cls))


def stable_segments(ts, f0s, rmss, cls, min_len=0.35, tol=0.6):
    """找连续音高稳定的段：|ΔMIDI| 累计不超过 tol。"""
    if len(ts) == 0:
        return []
    mid = hz_to_midi(f0s)
    segs, start, bad = [], 0, 0.0
    for i in range(1, len(mid)):
        d = abs(mid[i] - mid[i - 1])
        if d > 3.0:                        # 大跳= 分句
            bad += tol + 1
        elif d > tol:
            bad += d
        else:
            bad = max(0.0, bad - tol * 0.5)
        if bad > tol * 2:
            if ts[i] - ts[start] >= min_len:
                segs.append((ts[start], ts[i], float(np.median(mid[start:i]))))
            start, bad = i, 0.0
    if len(mid) and ts[-1] - ts[start] >= min_len:
        segs.append((ts[start], ts[-1], float(np.median(mid[start:]))))
    return segs


def fold_octave(m):
    """折叠到 [60,72)。"""
    return 60.0 + ((m - 60.0) % 12.0)


def pick_one_per_cluster(segs, n_clusters=8, min_sep=0.8):
    """把折叠后的音高聚类，每簇选**能量最大、时长够**的一段。"""
    if not segs:
        return []
    folded = np.array([fold_octave(s[2]) for s in segs])
    order = np.argsort(folded)
    clusters, cur = [], [order[0]]
    for idx in order[1:]:
        if folded[idx] - folded[cur[-1]] <= 1.0:      # 1 半音内算同簇
            cur.append(idx)
        else:
            clusters.append(cur)
            cur = [idx]
    clusters.append(cur)
    # 簇评分：段数 × 平均时长（既常见又够长）
    scored = []
    for c in clusters:
        if len(c) < 1:
            continue
        durs = [segs[i][1] - segs[i][0] for i in c]
        scored.append((len(c) * float(np.mean(durs)) * (1.0 + min(len(c), 6) * 0.12), c))
    scored.sort(reverse=True, key=lambda t: t[0])

    chosen = []
    for _, c in scored:
        # 与已选簇音高至少差 min_sep 半音，避免全挤在一个音上
        rep = float(np.median(folded[c]))
        if all(abs(rep - p) >= min_sep for p in chosen):
            best = max(c, key=lambda i: (segs[i][1] - segs[i][0]))
            chosen.append(fold_octave(segs[best][2]))
            if len(chosen) >= n_clusters:
                break
    return chosen


def shift(a, sr, ratio):
    """重采样变调：ratio>1 = 音高升高（时长变短）。"""
    n_out = max(64, int(len(a) / ratio))
    x_old = np.arange(len(a), dtype=np.float64)
    x_new = np.linspace(0, len(a) - 1, n_out)
    return np.interp(x_new, x_old, a).astype(np.float32)


def fade(a, sr, fin=0.006, fout=0.05):
    ni, no = int(sr * fin), int(sr * fout)
    a = a.copy()
    if ni > 1:
        a[:ni] *= np.linspace(0, 1, ni)
    if no > 1 and no < len(a):
        a[-no:] *= np.linspace(1, 0, no)
    return a


def normalize(a, peak=0.9):
    m = float(np.max(np.abs(a)))
    if m < 1e-6:
        return a
    return (a * (peak / m)).astype(np.float32)


def pick_clean_slice(a, sr, dur):
    """从一段里取能量最均匀的 dur 秒，避开起音爆音。"""
    need = int(sr * dur)
    if len(a) <= need:
        return a
    W = need // 4
    best, bestv = 0, -1.0
    for i in range(0, len(a) - need, max(1, W // 2)):
        seg = a[i:i + need]
        # 以中间 80% 的 rms 均值为准，起音/衰减不计
        core = seg[int(need * 0.1):int(need * 0.9)]
        v = float(np.sqrt((core ** 2).mean()))
        if v > bestv:
            bestv, best = v, i
    return a[best:best + need]


def main():
    if not os.path.isdir(DST):
        os.makedirs(DST)
    picked = {}     # target_index -> (src_path, seg)
    stats = []

    for fn in CANDIDATES:
        p = os.path.join(SRC, fn)
        if not os.path.exists(p):
            continue
        a, sr = read_wav(p)
        if a is None:
            stats.append("%s 跳过（位深非 16bit）" % fn)
            continue
        ts, f0s, rmss, cls = f0_track(a[:sr * 90], sr)
        segs = stable_segments(ts, f0s, rmss, cls)
        reps = pick_one_per_cluster(segs, 8)
        stats.append("%s  稳定音高段 %d  音级簇 %d %s"
                     % (fn, len(segs), len(reps),
                        " ".join("%.1f" % r for r in reps)))
        for r in reps:
            # 找与该音高最接近、时长最足的一段
            cands = [s for s in segs if abs(fold_octave(s[2]) - r) <= 1.0]
            if not cands:
                continue
            cands.sort(key=lambda s: -(s[1] - s[0]))
            s = cands[0]
            # 分配到最接近的目标音（且还没被占）
            best_t, best_d = None, 1e9
            for ti, tm in enumerate(TARGET_MIDI):
                if ti in picked:
                    continue
                d = abs(fold_octave(tm) - r)
                if d < best_d:
                    best_d, best_t = d, ti
            if best_t is None:
                continue
            i0 = int(s[0] * sr)
            raw = a[i0:int(s[1] * sr)]
            if len(raw) < int(sr * 0.12):
                continue
            cur_hz = midi_to_hz(fold_octave(s[2])) * 2.0   # 折回真实八度
            for oct_try in (1.0, 0.5, 2.0):
                ratio = (midi_to_hz(TARGET_MIDI[best_t]) / cur_hz) * oct_try
                if 0.4 <= ratio <= 2.5:
                    break
            dur = 0.55                                   # 采样乐句：0.55s，够听清音高又不冗长
            sh = shift(raw, sr, ratio)
            sh = fade(sh, sr)
            sh = normalize(pick_clean_slice(sh, sr, min(dur, len(sh) / sr)))
            sh = np.concatenate([sh, np.zeros(int(sr * 0.12), np.float32)])  # 尾部补静音
            out = os.path.join(DST, "mel_%02d_%s.wav" % (best_t, TARGET_NAME[best_t]))
            write_wav(out, sh, sr)
            picked[best_t] = (fn, round(fold_octave(s[2]), 2))
            stats.append("   %s ← %s @原音高%.1f (ratio %.2f)  %.2fs"
                         % (os.path.basename(out), fn, fold_octave(s[2]),
                            ratio, len(sh) / float(sr)))
        if len(picked) >= len(TARGET_MIDI):
            break

    print("\n".join(stats))
    print("\n=== 成品 %d/%d ===" % (len(picked), len(TARGET_MIDI)))
    for i, nm in enumerate(TARGET_NAME):
        fp = os.path.join(DST, "mel_%02d_%s.wav" % (i, nm))
        print("  slot%d  %-5s %s  %s"
              % (i + 1, nm, "OK" if os.path.exists(fp) else "缺", picked.get(i, "")))


if __name__ == "__main__":
    main()
