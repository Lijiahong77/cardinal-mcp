# -*- coding: utf-8 -*-
"""重建 Sequencer 的 data.tracks —— **这次维度按源码原文**。

★🔴 第二次维度错误（18:47修正）
  源码 Sequencer.cpp:104-121 原文：
      for (uint8_t i = 0; i <= NUM_PATTERNS; i++) {      // pattern，NUM_PATTERNS=16 ⇒ 17 个
        for (uint8_t j = 0; j < SEQ_BEATS; j++) {         // ★ 第2维 = 步(16)
          for (uint8_t k = 0; k < SEQ_TRACKS; k++)        // ★ 第3维 = 轨(8)
              tracks[i][j][k]
  ⇒ **tracks[pattern][beat][track] = 17 × 16 × 8**
  我第一次误写成 [pattern][track][step]（8×8×16）。
  ⚠️ **不崩、只静默填错位**：dataFromJson 的三层循环都带 `json_array_size(...) &&` 上限保护，
     所以维度不对时既不报错也不警告，只是音符落到别的位置 —— 这就是「鼓一直不响」的真因。
  ⇒ **教训：写data 里的嵌套数组，必须逐维对照源码的循环顺序，不能凭「看起来像」猜。**

★ Cardinal 自己的存盘是权威形状：它存出来是 17×16×8，与源码一致。
  之前那份 17×16×8 的 BASS/SNARE 绿格是**我第一版写错时被Cardinal 重新读写的产物**，
  所以画面上能看见但内容不对。本次按正确维度重写。
"""
import sys

sys.path.insert(0, r'D:\Cardinal\tools')
import patchio

SRC = r'D:\Cardinal\patches\quadeca_scrapyard_final.vcv'
OUT = r'D:\Cardinal\patches\quadeca_scrapyard_final.vcv'

NUM_PATTERNS = 16      # 源码: for i <= NUM_PATTERNS ⇒ 17 个pattern
SEQ_BEATS = 16          # 第2维：步
SEQ_TRACKS = 8          # 第3维：轨

# 面板行序（view/Sequencer.cpp: OUT 顺序 = 面板从上到下）
ROW = ['AUX1', 'AUX2', 'TOM1', 'TOM2', 'OPENHH', 'CLSDHH', 'SNARE', 'BASS']
T_SNARE, T_BASS = 6, 7

BASS_HITS = [0, 6, 8, 14]
SNARE_HITS = [4, 12, 15]


def main():
    d = patchio.read_patch(SRC)
    seq = next(m for m in d['modules'] if m['model'] == 'Sequencer')
    old = seq['data']['tracks']
    print('旧形状 = %d × %s × %s' % (
        len(old),
        sorted({len(p) for p in old}),
        sorted({len(r) for p in old for r in p})))

    tracks = []
    for pi in range(NUM_PATTERNS + 1):          # 0..16 ⇒ 17
        beat_rows = []
        for step in range(SEQ_BEATS):             # 第2维 = 步
            row = [0] * SEQ_TRACKS               # 第3维 = 轨
            if step in BASS_HITS:
                row[T_BASS] = 1
            if step in SNARE_HITS:
                row[T_SNARE] = 1
            beat_rows.append(row)
        tracks.append(beat_rows)
    seq['data']['tracks'] = tracks

    patch = dict(d)
    patch['modules'] = d['modules']
    patch['cables'] = d['cables']
    patch['path'] = OUT
    patchio.write_patch(OUT, patch, as_archive=True)

    # ---- 回读：形状 + 逐维断言 + 逐格比对 ----
    back = patchio.read_patch(OUT)
    bs = next(m for m in back['modules'] if m['model'] == 'Sequencer')
    t = bs['data']['tracks']
    assert len(t) == NUM_PATTERNS + 1, 'pattern 数=%d' % len(t)
    for pi, p in enumerate(t):
        assert len(p) == SEQ_BEATS, 'pattern%d 步数=%d' % (pi, len(p))
        for st, row in enumerate(p):
            assert len(row) == SEQ_TRACKS, 'p%d s%d 轨数=%d' % (pi, st, len(row))

    cp = bs['data']['currentPlay']
    print()
    print('写出 %s' % OUT)
    print('  新形状 = %d × %d × %d  ✅（pattern × 步 × 轨）'
          % (len(t), len(t[0]), len(t[0][0])))
    print('  当前 pattern = %d，各轨绿格：' % cp)
    for tr in range(SEQ_TRACKS):
        steps_hit = [st for st in range(SEQ_BEATS) if t[cp][st][tr]]
        print('    OUT%d %-7s %s' % (tr, ROW[tr], steps_hit if steps_hit else '(空)'))

    # 逐格精确验证
    for st in range(SEQ_BEATS):
        exp = [0] * SEQ_TRACKS
        if st in BASS_HITS:
            exp[T_BASS] = 1
        if st in SNARE_HITS:
            exp[T_SNARE] = 1
        assert t[cp][st] == exp, '步%d 不符：%s != %s' % (st, t[cp][st], exp)
    print('  ✅ 逐格比对全部一致（%d 步 × %d 轨）' % (SEQ_BEATS, SEQ_TRACKS))


if __name__ == '__main__':
    main()