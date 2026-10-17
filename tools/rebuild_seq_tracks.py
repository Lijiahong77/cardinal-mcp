# -*- coding: utf-8 -*-
"""重建 WSTD-Drums/Sequencer 的tracks 数据矩阵（之前形状就是错的）。

★🔴 事故根因（18:40 定位）
  `data.tracks` 的正确形状是 **三层**（源码 Sequencer.cpp:104-121）：
      tracks[pattern][track][step]    pattern ∈ 0..SEQ_PLAY-1 (8)
                                      track   ∈ 0..SEQ_TRACKS-1 (8)   ← 行：BASS/SNARE/TOM/HH/AUX
                                      step    ∈ 0..SEQ_BEATS-1  (16)
  而我早前手搓 JSON 时**压错了一维**，只写出 `2 轨 × 16 步`，还把它当成了「第1维=小节」。
  ⇒ 面板上 BASS/SNARE 那些行读不到任何数据 ⇒ **鼓永远不响**（这不是「没接时钟」那么浅）。
  ⚠️ 面板 8 行从上到下： AUX1 / AUX2 / TOM1 / TOM2 / OPEN HH / CLSD HH / SNARE / BASS
     **BASS = 轨 7（最后一行）**，SNARE = 轨 6。我先前把音符写到轨 0/1/2 = AUX1/AUX2/TOM1 ⇒ 错行。

★ 正确接法（决定一并修正）
  轨 7 = BASS   → OUT7 → BassDrum9.IN16
  轨 6 = SNARE  → OUT6 → SnareDrumN.IN16
  （之前我接的是 OUT0→BassDrum9 / OUT1→SnareDrumN ⇒ **接错行**，AUX1/AUX2 有声而底鼓军鼓哑。）

★ 节奏设计（16 步 = 1 小节 16 分音符；8 个 pattern 保持同一节奏 = 简单好听的 loop）
  BASS  (轨7)：每小节 1 / 3 / 9 / 11（backbeat 骨架，留空隙给军鼓）
  SNARE (轨6)：反拍 2 / 6 / 10 / 14 + 第4 拍的16（切分）
"""
import copy
import sys

sys.path.insert(0, r'D:\Cardinal\tools')
import patchio

SRC = r'D:\Cardinal\patches\quadeca_scrapyard_final.vcv'
OUT = r'D:\Cardinal\patches\quadeca_scrapyard_final.vcv'

SEQ_PLAY = 8      # pattern 数
SEQ_TRACKS = 8    # 轨数（=面板行数）
SEQ_BEATS = 16    # 每轨步数

# 面板行序（从上到下）→ 轨号
ROW = {'AUX1': 0, 'AUX2': 1, 'TOM1': 2, 'TOM2': 3,
       'OPENHH': 4, 'CLSDHH': 5, 'SNARE': 6, 'BASS': 7}
T_BASS, T_SNARE = ROW['BASS'], ROW['SNARE']

BASS_HITS = [0, 6, 8, 14]
SNARE_HITS = [4, 12, 15]

# 鼓机触发输入口
DRUM_IN = 16
BASS_DRUM = 'BassDrum9'
SNARE_DRUM = 'SnareDrumN'


def steps(hits):
    return [1 if i in hits else 0 for i in range(SEQ_BEATS)]


def main():
    d = patchio.read_patch(SRC)
    mods, cables = d['modules'], d['cables']
    ids = {m['id']: m for m in mods}

    def nm(i):
        p = ids[i]['plugin']
        return '%s/%s' % (p if isinstance(p, str) else p.get('slug'), ids[i]['model'])

    seq = next(m for m in mods if m['model'] == 'Sequencer')
    seqid = seq['id']
    print('Sequencer id=%d pos=%s currentPlay=%s'
          % (seqid, seq['pos'], seq['data']['currentPlay']))

    # ---- ① 重建完整矩阵 ----
    old = seq['data']['tracks']
    print('① 旧形状: %d 个 pattern，各轨数=%s'
          % (len(old), sorted({len(p) for p in old})))

    pat_bass, pat_snare = steps(BASS_HITS), steps(SNARE_HITS)
    tracks = []
    for pi in range(SEQ_PLAY):
        pattern = []
        for tr in range(SEQ_TRACKS):
            if tr == T_BASS:
                pattern.append(list(pat_bass))
            elif tr == T_SNARE:
                pattern.append(list(pat_snare))
            else:
                pattern.append([0] * SEQ_BEATS)   # AUX/TOM/HH 全空
        tracks.append(pattern)
    seq['data']['tracks'] = tracks
    print('   新形状: %d pattern × %d 轨 × %d 步 ✅' % (SEQ_PLAY, SEQ_TRACKS, SEQ_BEATS))
    print('   BASS  (轨%d) hits = %s' % (T_BASS, BASS_HITS))
    print('   SNARE (轨%d) hits = %s' % (T_SNARE, SNARE_HITS))

    # ---- ② 修正接线：OUT7→BassDrum9, OUT6→SnareDrumN ----
    bd = next(m for m in mods if m['model'] == BASS_DRUM)
    sd = next(m for m in mods if m['model'] == SNARE_DRUM)
    for drum, want_out, label in ((bd, T_BASS, '底鼓←BASS'), (sd, T_SNARE, '军鼓←SNARE')):
        c = next((x for x in cables
                  if x['inputModuleId'] == drum['id'] and x['inputId'] == DRUM_IN), None)
        if c is None:
            print('② ⚠ %s 没有触发线，跳过' % drum['model'])
            continue
        oldout = c['outputId']
        c['outputModuleId'] = seqid
        c['outputId'] = want_out
        print('② %s: Sequencer.OUT%d → OUT%d  (%s)'
              % (drum['model'], oldout, want_out, label))

    # ---- 门禁 ----
    seen = {}
    for c in cables:
        k = (c['inputModuleId'], c['inputId'])
        seen[k] = seen.get(k, 0) + 1
    dup = [k for k, v in seen.items() if v > 1]
    assert not dup, '同口多线 %s' % dup

    patch = dict(d)
    patch['modules'] = mods
    patch['cables'] = cables
    patch['path'] = OUT
    patchio.write_patch(OUT, patch, as_archive=True)

    # ---- 回读复验 ----
    back = patchio.read_patch(OUT)
    bs = next(m for m in back['modules'] if m['model'] == 'Sequencer')
    t = bs['data']['tracks']
    assert len(t) == SEQ_PLAY, 'pattern 数不对'
    for pi, p in enumerate(t):
        assert len(p) == SEQ_TRACKS, 'pattern%d 轨数=%d' % (pi, len(p))
        for tr, row in enumerate(p):
            assert len(row) == SEQ_BEATS, 'pattern%d 轨%d 步数=%d' % (pi, tr, len(row))
    cp = bs['data']['currentPlay']
    live = t[cp]
    print()
    print('写出 %s' % OUT)
    print('  模块 %d / 线 %d' % (len(back['modules']), len(back['cables'])))
    print('  ✅ 矩阵形状全部合法: %d×%d×%d' % (SEQ_PLAY, SEQ_TRACKS, SEQ_BEATS))
    print('  当前 pattern=%d → BASS(轨%d)=%s  SNARE(轨%d)=%s'
          % (cp, T_BASS,
             [i for i, v in enumerate(live[T_BASS]) if v],
             T_SNARE,
             [i for i, v in enumerate(live[T_SNARE]) if v]))
    for m in back['modules']:
        if m['model'] in (BASS_DRUM, SNARE_DRUM):
            c = next(x for x in back['cables']
                     if x['inputModuleId'] == m['id'] and x['inputId'] == DRUM_IN)
            print('  %-11s.IN%d ← Sequencer.OUT%d' % (m['model'], DRUM_IN, c['outputId']))


if __name__ == '__main__':
    main()