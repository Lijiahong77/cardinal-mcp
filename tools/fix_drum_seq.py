# -*- coding: utf-8 -*-
"""让 WSTD-Drums/Sequencer 真的驱动鼓：接时钟 + 写音符 + 修正 CYCLE。

★ 三个独立缺陷（李18:37 现场听出来的：「没有 clock 连，也没有 run 按着」）
--------------------------------------------------------------------------------
① **Sequencer 时钟口空着**。`Clocked.OUT0` 只接了 4 个 rcm-pianoroll，一根没进 Sequencer。
   端口核实（WSTD-Drums/src/controller/Sequencer.hpp:28-37）：
       enum InputIds { CLOCK, RUN_CV, CYCLE_CV, RESET, PULSE_WIDTH_CV,
                       MAIN_SELECT, TRACK_SELECT, ... }   ⇒ CLOCK=0, RUN_CV=1
   ⇒ 接`Clocked.OUT0 → Sequencer.IN0`（与pianoroll 同一路时钟，全机同步）。

② 🔴 **音符内容几乎全空**（比① 更致命，接上时钟也不响）
   `data.tracks` 是 **17 条**（8 轨 × 2 小节? 实为 tracks[16]），但：
     · track0 有内容，前3 步 [on,off,on,off,...]
     · **track1..track16 全是 false**
   而接线是 `OUT0→BassDrum9`（底鼓）、`OUT1→SnareDrumN`（军鼓）
   ⇒ **军鼓那一轨一个音都没有，永远不会响**；底鼓也只有零星几步。
   ★ 根源：这些音符**从来没被写过** —— 我早前的机架只clone 了结构，没填 pattern。
   ⇒ 这里按**底鼓 backbeat + 军鼓 backbeat** 写一个能听的 2 小节节奏。

③ **CYCLE param 索引算错**。源码：
       PATTERN_UP, PATTERN_DOWN = PATTERN_UP + SEQ_PLAY, CYCLE = PATTERN_DOWN + SEQ_PLAY
       SEQ_TRACKS=8, SEQ_BEATS=16, SEQ_PLAY=8
   PAD_PARAM=0, PLAY=8*16=128, MAIN_UP=128, MAIN_DOWN=129,
   PULSE_WIDTH=130, PATTERN_UP=131, PATTERN_DOWN=131+8=139, **CYCLE=139+8=147**
   ⇒ CYCLE 按钮 = param **147**。（live 回读里 `param147=1.0` 是**别的含义**，不是CYCLE。）

★ 关键设计决定
- **不自动开播**（李的宪法：让他自己按一下）。
  ⇒ Sequencer 的 `data.running` **保持 False**；`Clocked` 的 `data.running` **保持 False**。
    李按 Clocked 的 RUN / Sequencer 的 RUN 才会走。**只补时钟线，不替他启动。**
- 时钟选 **Clocked.OUT0**：它已经驱动 4 个 pianoroll，接上即整机同步，
  不用新加模块、不用改李的布局。

★ 基底= final（李当前在跑的那份），不动李手摆的混音器与任何坐标。
"""
import copy
import sys

sys.path.insert(0, r'D:\Cardinal\tools')
import patchio

SRC = r'D:\Cardinal\patches\quadeca_scrapyard_final.vcv'
OUT = r'D:\Cardinal\patches\quadeca_scrapyard_final.vcv'

SEQ_CLOCK_IN = 0# Sequencer InputIds.CLOCK
# ---- CYCLE 按钮 param id（源码推导，见文件头③）----
PAD_PARAM = 0
PLAY = 8 * 16          # SEQ_TRACKS * SEQ_BEATS = 128
MAIN_UP = PLAY         # 128
MAIN_DOWN = MAIN_UP + 1        # 129
PULSE_WIDTH = MAIN_DOWN + 1        # 130
PATTERN_UP = PULSE_WIDTH + 1       # 131
PATTERN_DOWN = PATTERN_UP + 8     # 139  (= PATTERN_UP + SEQ_PLAY)
CYCLE_PARAM = PATTERN_DOWN + 8        # 147  (= PATTERN_DOWN + SEQ_PLAY)
CYCLE_ON = 1.0

# 2 小节 × 16 步。True = 该步触发
#底鼓：标准 backbeat，落1 / 3 / 5 / 9 / 11 / 15（偏 funky，不至于太闷）
BD = [1, 3, 5, 9, 11, 15]
# 军鼓：反拍 2 / 6 / 10 / 14，加第 3 小节前的16
SD = [2, 6, 10, 14]
# 采样副旋律：偶尔点缀
SP = [7, 15]


def step_list(hits, total=16):
    s = [False] * total
    for i in hits:
        if 0 <= i < total:
            s[i] = True
    return s


def main():
    d = patchio.read_patch(SRC)
    mods, cables = d['modules'], d['cables']
    ids = {m['id']: m for m in mods}

    def nm(i):
        p = ids[i]['plugin']
        return '%s/%s' % (p if isinstance(p, str) else p.get('slug'), ids[i]['model'])

    seq = next(m for m in mods if m['model'] == 'Sequencer')
    ck = next(m for m in mods if m['model'] == 'Clocked')
    sid, kid = seq['id'], ck['id']
    print('Sequencer id=%d pos=%s' % (sid, seq['pos']))
    print('Clocked   id=%d pos=%s' % (kid, ck['pos']))

    # ---- ① 接时钟 ----
    have = [c for c in cables if c['inputModuleId'] == sid and c['inputId'] == SEQ_CLOCK_IN]
    if have:
        print('① Sequencer.IN0 已有时钟 ← %s（跳过）' % nm(have[0]['outputModuleId']))
    else:
        cid = max([c['id'] for c in cables] + [0]) + 1
        # 用 pianoroll 那条同源线做proto（字段形状同源最保险）
        proto = next(c for c in cables
                     if c['outputModuleId'] == kid and c['outputId'] == 0)
        c = copy.deepcopy(proto)
        c['id'] = cid
        c['outputModuleId'] = kid
        c['outputId'] = 0
        c['inputModuleId'] = sid
        c['inputId'] = SEQ_CLOCK_IN
        c.pop('color', None)
        cables.append(c)
        print('① 新增 Clocked.OUT0 → Sequencer.IN%d（CLOCK）' % SEQ_CLOCK_IN)

    # ---- ② 写音符 ----
    dd = seq['data']
    tracks = dd.get('tracks')
    print('② 原tracks：%d 条，非空轨=%s'
          % (len(tracks), [i for i, t in enumerate(tracks) if any(any(b) for b in t)]))
    pat_kd = step_list(BD) * 2         # 32 步 = 2 小节
    pat_sd = step_list(SD) * 2
    pat_sp = step_list(SP) * 2
    assert all(len(x) == 32 for x in (pat_kd, pat_sd, pat_sp))
    for trk, pat in ((0, pat_kd), (1, pat_sd), (2, pat_sp)):
        # 每轨结构：[[16 步] x 2 小节]
        tracks[trk] = [pat[0:16], pat[16:32]]
    dd['tracks'] = tracks
    print('   轨0 底鼓 hits =', BD, 'x2 小节')
    print('   轨1 军鼓 hits =', SD, 'x2 小节')
    print('   轨2 采样 hits =', SP, 'x2 小节')
    seq['data'] = dd

    # ---- ③ CYCLE 按钮 ----
    pr = {p['id']: p['value'] for p in seq['params']}
    before = pr.get(CYCLE_PARAM)
    for p in seq['params']:
        if p['id'] == CYCLE_PARAM:
            p['value'] = CYCLE_ON
    print('③ CYCLE param=%d : %s → %.1f（On）' % (CYCLE_PARAM, before, CYCLE_ON))

    # ---- 不自动开播 ----
    seq['data']['running'] = False
    print('   running 保持 False（不替你启动，你自己按 RUN）')

    patch = dict(d)
    patch['modules'] = mods
    patch['cables'] = cables
    patch['path'] = OUT

    # ---- 门禁 ----
    seen = {}
    for c in patch['cables']:
        k = (c['inputModuleId'], c['inputId'])
        seen[k] = seen.get(k, 0) + 1
    dup = [k for k, v in seen.items() if v > 1]
    assert not dup, '同口多线 %s' % dup
    ids2 = {m['id'] for m in patch['modules']}
    dang = [(m['id'], k) for m in patch['modules']
            for k in ('leftModuleId', 'rightModuleId')
            if m.get(k) is not None and m[k] not in ids2]
    assert not dang, '悬空指针 %s' % dang

    patchio.write_patch(OUT, patch, as_archive=True)

    # ---- 回读复验 ----
    back = patchio.read_patch(OUT)
    bs = next(m for m in back['modules'] if m['model'] == 'Sequencer')
    bc = next(m for m in back['modules'] if m['model'] == 'Clocked')
    print()
    print('写出 %s' % OUT)
    print('  模块 %d / 线 %d' % (len(back['modules']), len(back['cables'])))
    print('  Clocked pos=%s (未动)   Sequencer pos=%s (未动)'
          % (bc['pos'], bs['pos']))
    print('  Sequencer running=%s  cycling=%s  CYCLE(param%d)=%.1f'
          % (bs['data']['running'], bs['data']['cycling'], CYCLE_PARAM,
             next(p['value'] for p in bs['params'] if p['id'] == CYCLE_PARAM)))
    clk = [c for c in back['cables']
           if c['inputModuleId'] == bs['id'] and c['inputId'] == 0]
    print('  时钟线:', ('Clocked.OUT0 → Sequencer.IN0' if clk else '❌ 缺'))
    # 鼓机触发线
    for m in back['modules']:
        if m['model'] in ('BassDrum9', 'SnareDrumN'):
            t = [c for c in back['cables']
                 if c['inputModuleId'] == m['id'] and c['inputId'] == 16]
            print('  %-11s IN16 ← %s' % (m['model'],
                                          nm(t[0]['outputModuleId']) if t else '❌'))
    for trk, pat in ((0, BD), (1, SD), (2, SP)):
        t = bs['data']['tracks'][trk]
        got = [i for i, b in enumerate(t[0] + t[1]) if b]
        assert got == pat + [x + 16 for x in pat], '轨%d 音符写入不符：%s' % (trk, got)
    print('  ✅ 三轨音符回读一致')


if __name__ == '__main__':
    main()