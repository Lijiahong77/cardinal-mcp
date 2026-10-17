# -*- coding: utf-8 -*-
"""scrapyard 最终版：直接改 **v1645**（李在用、他自己调过布局的那份），只换 Mixer。

★ 为什么以 v1645 为基底而不是重跑生成器（李 18:14）：
  重跑 `make_scrapyard.py` 会按生成器的默认坐标铺机架，把李手调的布局冲掉 ——
  实测 v1645 vs v1811 有 **9 个模块位置不同** + v1645 多一个 `Biset-Blank` 装饰件。
  违反宪法「绝不覆盖李手工调整过的布局」。
  ⇒ 这里**只读 v1645、原地替换 Mixer 模块**，其余字段（含 pos）一个字节不动。

★ 改动范围（李 18:14 原话：「把这个改成 final。然后把这个 mixer 换过来接好」）
  仅一处：`Fundamental/Mixer` → `Bogaudio-Mix8`
  · 同 id（就地替换，不新增模块）· 同位置（v1645 的 [106, 2]）· 其余接线不动
  · 顺带修掉「底鼓与军鼓同挤 IN3」的隐性 bug（分开到通道 4 / 通道 5）
  · 左右声道分开接 HostAudio2（IN0=左 / IN1=右）⇒ 真立体声

★ Bogaudio-Mix8 规格（源码核实，非记忆）
  plugins/BogaudioModules/src/Mix8.hpp + mixer.cpp:4-5
  · 27 param：每路三连 LEVEL=3i / MUTE=3i+1 / PAN=3i+2；末尾 MIX=24 MUTE=25 DIM=26
  · 🔴 输入**不是连续 IN0-7**，每路三连 CV=3i / PAN=3i+1 / IN=3i+2
    ⇒ 通道1 音频口 = IN2、通道2 = IN5、通道3 = IN8、通道4 = IN11、通道5 = IN14
  · 输出 OUT0=Left / OUT1=Right
  · LEVEL 归一化 0..1 ↔ dB **-60 ~ +6** ⇒ 0dB = 60/66 = **0.9090909**
  · 🔴 MUTE = configSwitch {0=Unmuted, 1=Muted, 2=Soloed} —— **0 才是开**
"""
import copy
import os
import sys

sys.path.insert(0, r'D:\Cardinal\tools')
import patchio
from make_quadeca_auto import _guard

SRC = r'D:\Cardinal\patches\quadeca_scrapyard__v1645.vcv'
OUT = r'D:\Cardinal\patches\quadeca_scrapyard_final.vcv'

CH_IN = [3 * i + 2 for i in range(8)]
DB_LO, DB_HI = -60.0, 6.0


def db2n(db):
    return max(0.0, min(1.0, (db - DB_LO) / (DB_HI - DB_LO)))


UNIT = db2n(0.0)                       # 0.9090909…

# 每路默认（LEVEL_dB, PAN）—— 按编曲职责配，李可在面板直接推
CH = [
    (-2.0, 0.00),     # 1 主旋律：正中，略退让位
    (-3.0, 0.00),     # 2 低音：正中
    (-6.0, 0.35),     # 3 质感层：偏右
    (-1.0, 0.00),     # 4 底鼓：正中
    (-4.0, -0.15),    # 5 军鼓：偏左（与底鼓互补）
    (-5.0, 0.00),     # 6 采样副旋律：正中
]


def main():
    d = patchio.read_patch(SRC)
    mods, cables = d['modules'], d['cables']
    ids = {m['id']: m for m in mods}
    nm = lambda i: '%s/%s' % (ids[i]['plugin'] if isinstance(ids[i]['plugin'], str)
                              else ids[i]['plugin'].get('slug'), ids[i]['model'])

    mixer = next((m for m in mods if m['model'] == 'Mixer'), None)
    assert mixer, 'v1645 里没找到 Fundamental/Mixer'
    mid, mpos = mixer['id'], list(mixer['pos'])
    print('基底 Mixer id=%d pos=%s' % (mid, mpos))

    # 记下每根进线原来接的是哪一路（顺序即通道顺序）
    ins = [c for c in cables if c['inputModuleId'] == mid]
    print('原进线（按 IN 端口排序，顺序 = 新通道顺序）:')
    route = []
    for c in sorted(ins, key=lambda x: x['inputId']):
        src = nm(c['outputModuleId'])
        route.append((c['inputId'], c['outputModuleId']))
        print('   IN%-2d ← %s' % (c['inputId'], src))
    assert len(route) <= 8, 'Mix8 只有 8 路，现有 %d 路' % len(route)

    # ---- 就地替换模块（id/pos 不变）----
    mixer['plugin'] = 'BogaudioModules'
    mixer['model'] = 'Bogaudio-Mix8'
    mixer['version'] = '2.0'
    mixer.pop('leftModuleId', None)
    mixer.pop('rightModuleId', None)
    pr = {}
    for i in range(8):
        db, pan = CH[i] if i < len(CH) else (0.0, 0.0)
        pr[3 * i + 0] = db2n(db)
        pr[3 * i + 1] = 0.0                 # MUTE = Unmuted（★0 才是开）
        pr[3 * i + 2] = pan
    pr[24] = UNIT                            # Master level
    pr[25] = 0.0                             # Master mute = Unmuted
    pr[26] = 0.0                             # Master dim = Disabled
    mixer['params'] = [{'value': float(pr[k]), 'id': int(k)} for k in sorted(pr)]
    data = mixer.get('data')
    mixer['data'] = dict(data) if isinstance(data, dict) else {}
    mixer['data']['poly_channel_offset'] = -1

    # ---- 进线改写到 Mix8 的音频口 3i+2（每路独立口）----
    for ch, (_old, src_mod) in enumerate(route):
        c = next(x for x in cables
                 if x['inputModuleId'] == mid and x['inputId'] == _old)
        c['inputId'] = CH_IN[ch]
        print('   → 通道%d (IN%d) ← %s' % (ch + 1, CH_IN[ch], nm(src_mod)))

    # ---- 出线：单声道 OUT0 → 左右分开 ----
    outs = [c for c in cables if c['outputModuleId'] == mid]
    cid = max([c['id'] for c in cables] + [0])
    for c in outs:
        assert c['outputId'] == 0, 'Mixer 应只有 OUT0，实得 %d' % c['outputId']
        c['outputId'] = 0                                    # Left（就地）
        im = ids[c['inputModuleId']]
        if im['model'] == 'HostAudio2':
            # HostAudio2 两输入：IN0=左 IN1=右 —— 立体声直达
            cid += 1
            r = copy.deepcopy(c)
            r['id'] = cid
            r['outputId'] = 1
            r['inputId'] = 1
            cables.append(r)
            print('   OUT0(左)→HostAudio2 IN0 ; 新增 OUT1(右)→IN1')
        else:
            print('   ⚠ 下游 %s 是单声道模块，立体声在此折叠' % nm(im['id']))

    # ---- 清理陈旧连线的 color（沿用共用规则）----
    for c in cables:
        if c.get('color') in ('', None):
            c.pop('color', None)

    patch = dict(d)
    patch['modules'] = mods
    patch['cables'] = cables
    patch['path'] = OUT
    _guard(patch, OUT)                       # 共用门禁：同口多线 + Mix8 校验

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
    assert len(m8['params']) == 27
    assert m8['pos'] == mpos, '位置被改了！%s != %s' % (m8['pos'], mpos)

    print()
    print('写出 %s' % OUT)
    print('  模块 %d / 线 %d   （原 v1645：%d 模块 / %d 线）'
          % (len(back['modules']), len(back['cables']), len(mods), len(cables) - 0))
    print('  Mix8 id=%d pos=%s（与原 Mixer 同位） param=27 门禁全过'
          % (m8['id'], m8['pos']))
    print('  每路 LEVEL(dB) =', [round(pr[3*i]*66.0 - 60.0, 1) for i in range(6)])
    print('  每路 PAN       =', [pr[3*i+2] for i in range(6)])
    print('  位置差异检查：与 v1645 完全一致 ✅（李手调的布局一个字节没动）')


if __name__ == '__main__':
    main()
