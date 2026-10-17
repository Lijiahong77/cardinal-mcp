# -*- coding: utf-8 -*-
"""把 6 个声部接进李手动添加的 MindMeldModular/MixMasterJr。

★ 背景（18:29）
  我之前推的 `Bogaudio-Mix8` 被李在 GUI 里删掉了，**这是对的** ——
  ① Mix8 与 HostAudio2 的 pos 差 5（[106,2] vs [111,2]）而 Mix8 远宽于5 ⇒ **面板重叠**；
  ② 更根本：我的「Mixin 存在」结论是从 **autosave 回读** 推的，
     而李 GUI 里的实际画面与那份回读对不上 —— 我把「文件里有」当成了「你看得见」。
  ⇒教训：**验收必须以李窗口的真实截图为准**，autosave 只证明文件，不证明画面。
  李自己挑了 `MixMasterJr`（8 轨、每轨 MUTE/SOLO/推子/PAN/HPF/LPF），这是更合适的选择。

★ 端口规格（源码核实，plugins/MindMeldModular/src/MixMaster/MixMaster.cpp:37-55）
  enum InputIds { ENUMS(TRACK_SIGNAL_INPUTS, N_TRK*2), ... }  // 注释原文：
      // Track 0: 0 = L, 1 = R, Track 1: 2 = L, 3 = R ...
  enum OutputIds { ENUMS(DIRECT_OUTPUTS, N_TRK/8 + 1), ENUMS(MAIN_OUTPUTS, 2), ... }
  ⇒ MixMasterJr (N_TRK=8)：**音频输入 0..15 = 轨i 的 L=2i / R=2i+1**
  ⇒ **主输出 L=2 / R=3**（李已接：OUT2→HostAudio IN0、OUT3→HostAudio IN1，实测吻合）

★ 单声道源接法：本机各声部（VCA-1 / BassDrum9 / SnareDrumN / samplerx8）都是单声道输出
  ⇒ 只接各轨的 **L 口（2i）**，由MixMasterJr 内部按 panLaw 折叠成立体声。
  不接R：两个口是同一轨的左右，不是「两个输入」。
"""
import copy
import sys

sys.path.insert(0, r'D:\Cardinal\tools')
import patchio

SRC = r'D:\Cardinal\patches\_probe_live.vcv'
OUT = r'D:\Cardinal\patches\quadeca_scrapyard_final.vcv'


def sig(trk):
    """MixMasterJr 轨 trk（0 起）的音频输入口 id = L。"""
    return 2 * trk


def main():
    d = patchio.read_patch(SRC)
    mods, cables = d['modules'], d['cables']
    ids = {m['id']: m for m in mods}

    def nm(i):
        p = ids[i]['plugin']
        return '%s/%s' % (p if isinstance(p, str) else p.get('slug'), ids[i]['model'])

    mix = next(m for m in mods if m['model'] == 'MixMasterJr')
    mid = mix['id']
    print('MixMasterJr id=%d pos=%s params=%d' % (mid, mix['pos'], len(mix['params'])))
    outs = [c for c in cables if c['outputModuleId'] == mid]
    print('已有出线（李接的）:',
          [(nm(c['inputModuleId']), c['outputId']) for c in outs])
    assert len(outs) == 2, '主输出应已有 2 根（L/R）'
    assert {c['outputId'] for c in outs} == {2, 3}, '主输出口不是 2/3，规格有变！停。'

    # ---- 6 个声部 → 轨 1..6 ----
    # 源模块 id（从 live 回读确认，不靠记忆）：
    #   1003 VCA-1 主旋律 · 3003 VCA-1 低音 · 4003 VCA-1 质感层
    #   6100 BassDrum9 · 6101 SnareDrumN · 2001 samplerx8
    route = [
        (0, 9500000000001003, '主旋律 VCA-1'),
        (1, 9500000000003003, '低音 VCA-1'),
        (2, 9500000000004003, '质感层 VCA-1'),
        (3, 9500000000006100, '底鼓 BassDrum9'),
        (4, 9500000000006101, '军鼓 SnareDrumN'),
        (5, 9500000000002001, '采样 samplerx8'),
    ]

    cid = max([c['id'] for c in cables] + [0])
    # 用李自己那条线做 proto —— 字段形状/color 由 Cardinal 自己生成过，最保险
    proto = next(c for c in cables if c['outputModuleId'] == mid)

    for trk, src, label in route:
        assert src in ids, '%s 不在机架里' % label
        p = sig(trk)
        exist = [c for c in cables if c['inputModuleId'] == mid and c['inputId'] == p]
        if exist:
            print('  轨%d IN%-2d 已有 ← %s（跳过）' % (trk + 1, p, nm(exist[0]['outputModuleId'])))
            continue
        # 同口多线门禁
        clash = [c for c in cables if c['inputModuleId'] == mid and c['inputId'] == p]
        assert not clash, '轨%d IN%d 已被占用' % (trk + 1, p)
        cid += 1
        c = copy.deepcopy(proto)
        c['id'] = cid
        c['outputModuleId'] = src
        c['outputId'] = 0# 各声部单声道，取 OUT0
        c['inputModuleId'] = mid
        c['inputId'] = p
        c.pop('color', None)          # 让 Cardinal 自己配色
        cables.append(c)
        print('  轨%d IN%-2d← %-22s (%s)' % (trk + 1, p, nm(src), label))

    patch = dict(d)
    patch['modules'] = mods
    patch['cables'] = cables
    patch['path'] = OUT

    # ---- 门禁：同口多线 + 悬空指针 ----
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
    bids = {m['id']: m for m in back['modules']}
    bm = next(m for m in back['modules'] if m['model'] == 'MixMasterJr')
    print()
    print('写出 %s' % OUT)
    print('  模块 %d / 线 %d（原来 %d）' % (len(back['modules']), len(back['cables']), len(d['cables'])))
    print('  MixMasterJr pos=%s params=%d' % (bm['pos'], len(bm['params'])))
    print('  --- 混音器接线 ---')
    for c in sorted([c for c in back['cables']
                     if c['inputModuleId'] == bm['id'] or c['outputModuleId'] == bm['id']],
                    key=lambda x: (x['inputModuleId'] != bm['id'], x['inputId'])):
        if c['outputModuleId'] == bm['id']:
            s = bids[c['inputModuleId']]
            sl = s['plugin'] if isinstance(s['plugin'], str) else s['plugin'].get('slug')
            print('    OUT%-2d → %s/%s IN%d' % (c['outputId'], sl, s['model'], c['inputId']))
        else:
            print('    轨%d IN%-2d ← %s' % (c['inputId'] // 2 + 1, c['inputId'], nm(c['outputModuleId'])))


if __name__ == '__main__':
    main()