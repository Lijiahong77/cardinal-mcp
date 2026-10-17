# -*- coding: utf-8 -*-
"""给 final 补军鼓：WSTD-Drums/SnareDrumN OUT0 → Bogaudio-Mix8 通道6 (IN17)。

★ 基底 = `quadeca_scrapyard_final.vcv`（李当前在跑的那份），**不重跑 scrapyard 生成器**
  —— 重跑会把李手调的布局冲掉（v1645 vs v1811 有 9 个位置不同）。

★ 为什么要单独一个脚本而不是改 make_scrapyard_final.py：
  final 是李在用的稳定文件；军鼓线是他 18:21 追加的需求。
  这里以 final 为基底，只新增一根线，其余模块/线一个字节不动。

★ 端口核实（v1645 实测）：
  · `Sequencer OUT1 → SnareDrumN IN16` 已存在 ⇒ 军鼓已经在被触发，只是没人收它的声音
  · `BassDrum9 OUT0 → Mixer IN3` 用的是 outId=0 ⇒ 同族鼓机输出口一致，SnareDrumN 也取 OUT0
  · Mix8 每路三连：CV=3i / PAN=3i+1 / IN=3i+2 ⇒ 通道6 音频口 = 3*5+2 = **IN17**，
    对应 param：LEVEL=15 / MUTE=16 / PAN=17。
"""
import copy
import sys

sys.path.insert(0, r'D:\Cardinal\tools')
import patchio
from make_quadeca_auto import _guard

SRC = r'D:\Cardinal\patches\quadeca_scrapyard_final.vcv'
OUT = r'D:\Cardinal\patches\quadeca_scrapyard_final.vcv'

CH = 5                      # 通道 6（0 起算）
CH_IN = 3 * CH + 2          # 17
LEVEL_IDX = 3 * CH          # 15
MUTE_IDX = 3 * CH + 1       # 16
PAN_IDX = 3 * CH + 2        # 17
DB_LO, DB_HI = -60.0, 6.0


def db2n(db):
    return max(0.0, min(1.0, (db - DB_LO) / (DB_HI - DB_LO)))


def main():
    d = patchio.read_patch(SRC)
    mods, cables = d['modules'], d['cables']
    ids = {m['id']: m for m in mods}

    def nm(i):
        p = ids[i]['plugin']
        return '%s/%s' % (p if isinstance(p, str) else p.get('slug'), ids[i]['model'])

    mix = next(m for m in mods if m['model'] == 'Bogaudio-Mix8')
    snare = next(m for m in mods if m['model'] == 'SnareDrumN')
    mid, sid = mix['id'], snare['id']
    print('Mix8 id=%d pos=%s' % (mid, mix['pos']))
    print('SnareDrumN id=%d pos=%s' % (sid, snare['pos']))

    # ---- 幂等：已有这根线就直接退出 ----
    exist = [c for c in cables if c['inputModuleId'] == mid and c['inputId'] == CH_IN]
    if exist:
        print('通道6 已有进线（来自 %s），无需重复添加' % nm(exist[0]['outputModuleId']))
    else:
        # 同口多线检查
        assert not [c for c in cables if c['inputModuleId'] == mid and c['inputId'] == CH_IN]
        cid = max([c['id'] for c in cables] + [0]) + 1
        # 沿用一根进线的字段形状（color / type 等）
        proto = next(c for c in cables if c['inputModuleId'] == mid)
        c = copy.deepcopy(proto)
        c['id'] = cid
        c['outputModuleId'] = sid
        c['outputId'] = 0                 # 与 BassDrum9 一致
        c['inputModuleId'] = mid
        c['inputId'] = CH_IN
        cables.append(c)
        print('新增连线 #%d: SnareDrumN OUT0 → Mix8 IN%d (通道6)' % (cid, CH_IN))

    # ---- 通道6 默认电平/声像：军鼓居中略偏左，与底鼓(正中/ -1dB)区分开 ----
    #      通道5 是采样层（-4dB / -0.15），别和军鼓给成一样的值，否则面板上分不清
    for p in mix['params']:
        if p['id'] == LEVEL_IDX:
            p['value'] = db2n(-3.0)
            print('通道6 LEVEL → -3 dB (norm %.6f)' % p['value'])
        elif p['id'] == MUTE_IDX:
            p['value'] = 0.0              # ★ 0 = Unmuted
            print('通道6 MUTE  → 0 (Unmuted)')
        elif p['id'] == PAN_IDX:
            p['value'] = -0.08
            print('通道6 PAN   → -0.08 (略偏左，与底鼓区分)')

    patch = dict(d)
    patch['modules'] = mods
    patch['cables'] = cables
    patch['path'] = OUT
    _guard(patch, OUT)

    patchio.write_patch(OUT, patch, as_archive=True)

    # ---- 回读复验 ----
    back = patchio.read_patch(OUT)
    bids = {m['id'] for m in back['modules']}
    assert len(back['modules']) == len(mods), '模块数变了'
    assert len(back['cables']) == len(cables), '线数变了'
    dang = [(m['id'], k) for m in back['modules']
            for k in ('leftModuleId', 'rightModuleId')
            if m.get(k) is not None and m[k] not in bids]
    assert not dang, '悬空指针 %s' % dang
    seen = {}
    for c in back['cables']:
        k = (c['inputModuleId'], c['inputId'])
        seen[k] = seen.get(k, 0) + 1
    assert not [k for k, v in seen.items() if v > 1], '同口多线'
    m8 = next(m for m in back['modules'] if m['model'] == 'Bogaudio-Mix8')
    assert len(m8['params']) == 27, 'Mix8 param 数变了'
    assert m8['pos'] == mix['pos'], 'Mix8 位置被动了'

    print()
    print('写出 %s' % OUT)
    print('  模块 %d / 线 %d' % (len(back['modules']), len(back['cables'])))
    lv = {p['id']: p['value'] for p in m8['params']}
    for i in range(6):
        print('  通道%d IN%-2d  %+5.1f dB  pan=%+.2f  mute=%d'
              % (i + 1, 3 * i + 2, lv[3 * i] * 66.0 - 60.0, lv[3 * i + 2], int(lv[3 * i + 1])))
    print('  Master %+5.1f dB  mute=%d  dim=%d'
          % (lv[24] * 66.0 - 60.0, int(lv[25]), int(lv[26])))


if __name__ == '__main__':
    main()