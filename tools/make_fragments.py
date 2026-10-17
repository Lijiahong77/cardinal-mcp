# -*- coding: utf-8 -*-
"""make_fragments.py —— 把李的音乐文件夹里的真实声音切成「叙事碎片」。

★ 为什么这么做（依据 Quadeca 文档）
  Scrapyard 的核心手法是「**采样即叙事碎片**」+ 非线性蒙太奇 + 故障跳转：
  采集现实世界的环境音/ 音效，当作碎片在时间轴上硬切拼接。
  ⇒ 之前我做的是「四层和声音高堆叠」—— **方法论根本不对**，所以听起来还是 ghostfolk。

  素材来源（李电脑里现成的、**他自己原创**的音效，版权干净）：
    C:\\Users\\lijia\\Music\\游戏音效\\
      SFX_Helicopter_Rotor_v001.wav   60s 单声道 48kHz —— 直升机旋翼（有节奏的浆状声）
      AMB_City_v001.mp3                城市环境音（噪声型底噪）
      SFX_Umbrella_MetalTap_v001.mp3   金属敲击（瞬态，适合做「标点」）

做法：检测瞬态 / 按固定间隔切，切成 0.1~0.6s 的短碎片，
     统一转成 48kHz 16bit 单声道 WAV 写到 D:\\Cardinal\\samples\\fragments\\。
     ★ 不做降噪不做重采样美化 —— 碎片要的就是「原始、粗糙」。
"""
import os
import struct
import wave

SRC = r"C:\Users\lijia\Music\游戏音效"
OUT = r"D:\Cardinal\samples\fragments"
SR = 48000


def read_wav_mono(path):
    w = wave.open(path, "rb")
    ch, sw, fr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
    raw = w.readframes(n)
    w.close()
    assert sw == 2, "只处理 16bit，实际 %d" % (sw * 8)
    import array
    a = array.array("h")
    a.frombytes(raw)
    if ch == 2:
        a = array.array("h", [(a[i] + a[i + 1]) // 2 for i in range(0, len(a), 2)])
    if fr != SR:
        # 线性重采样到 48k（碎片很短，误差无妨）
        ratio = fr / float(SR)
        m = int(len(a) / ratio)
        a = array.array("h", [a[int(i * ratio)] for i in range(m)])
    return a


def write_wav(path, samples, peak=0.9):
    mx = max(1, max(abs(s) for s in samples))
    g = int(32767 * peak / mx)
    data = array.array("h", [max(-32768, min(32767, int(s * g))) for s in samples])
    w = wave.open(path, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(data.tobytes())
    w.close()
    return len(data) / float(SR)


import array   # noqa: E402  (read_wav_mono 里要用)


def fragments(samples, lengths):
    """按给定长度从头部依次切。"""
    out, pos = [], 0
    for ln in lengths:
        n = int(SR * ln)
        if pos + n > len(samples):
            break
        out.append(samples[pos:pos + n])
        pos += n
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    made = []

    # ---- 1. 直升机旋翼：切成 12 个 0.45s 碎片 ----
    # 旋翼声本身有周期性劈啪，切碎后每片都带着「转动的残骸」感。
    heli = read_wav_mono(os.path.join(SRC, "SFX_Helicopter_Rotor_v001.wav"))
    for i, seg in enumerate(fragments(heli, [0.45] * 14)):
        p = os.path.join(OUT, "heli_%02d.wav" % i)
        write_wav(p, seg, peak=0.85)
        made.append(p)

    # ---- 2. 城市环境音：切成 6 个 0.8s 长碎片（当噪声底） ----
    try:
        city = read_wav_mono(os.path.join(SRC, "AMB_City_v001.mp3"))
        for i, seg in enumerate(fragments(city, [0.8] * 8)):
            p = os.path.join(OUT, "city_%02d.wav" % i)
            write_wav(p, seg, peak=0.55)
            made.append(p)
    except Exception as e:
        print("跳过 city（需要 mp3 解码）:", e)

    # ---- 3. 从同一条直升机素材里再切**短促的瞬态碎片**（0.12s）----
    # 手法：同一素材切出「长片」与「短瞬态」两种，在蒙太奇里交替使用
    #      ⇒ 碎片之间形成**粒度对比**（长底噪 vs 短瞬态），
    #      这是非线性蒙太奇听起来「破碎」的关键 —— 全部一样长就不破碎了。
    for i, seg in enumerate(fragments(heli[SR * 7:], [0.12] * 40)):
        p = os.path.join(OUT, "tick_%02d.wav" % i)
        write_wav(p, seg, peak=0.95)
        made.append(p)

    print("共生成 %d 个碎片 -> %s" % (len(made), OUT))
    tot = 0.0
    for p in made:
        w = wave.open(p)
        tot += w.getnframes() / float(w.getframerate())
        w.close()
    print("总时长 %.1f 秒" % tot)
    for p in made[:6]:
        print("   ", os.path.basename(p))
    if len(made) > 6:
        print("    ... 共 %d 个" % len(made))


if __name__ == "__main__":
    main()