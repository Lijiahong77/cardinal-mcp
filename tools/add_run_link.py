# -*- coding: utf-8 -*-
"""补上 RUN 启动线：Clocked.OUT5 (RUN_OUTPUT) → Sequencer.IN1 (RUN_CV)。

★ 李 18:45 的原话（本项目最值钱的一条领域知识）
  「如果没有接 run 的话，它是不会动的。哪怕你接 clock 也不会动，
    因为 clock 只传输一个节奏速率的数据，它不包含启动的指令」
  ⇒ **clock = 速率，run = 启动指令，两者缺一不可。** 我先前只补了 clock，鼓还是不动。

★ 端口规格（源码核实）
  ImpromptuModular/src/Clocked.cpp:215-221
      enum OutputIds { ENUMS(CLK_OUTPUTS,4), // master = index 0
                       RESET_OUTPUT,       // = 4（注释：autopatch 硬编码）
                       RUN_OUTPUT,         // = 5
                       BPM_OUTPUT, NUM_OUTPUTS }
  WSTD-Drums/src/controller/Sequencer.hpp:28-31
      enum InputIds { CLOCK=0, RUN_CV=1, CYCLE_CV=2, RESET=3, ... }
  源码 Sequencer.cpp:321-322：`if (inputs[RUN_CV].isConnected()) runCV->update(...)`
  ⇒ RUN_CV 一旦接线，就**由 CV 决定运行状态**（而不是面板按钮）。

★ 这样接的好处（也是李要的）
  李只需按 **Clocked 的 RUN** 一个键 → RUN 信号同时送到 Sequencer
  ⇒ 整机（4 个 pianoroll + 鼓 sequencer）一次启动、永不脱拍。
  ⚠️ 仍遵守「不替李开播」：`Clocked.data.running = False` 保持不变，他自己按。

★ 基底 = final（李当前在跑的那份），不动任何坐标、不动他手摆的混音器。
"""
import copy
import sys

sys.path.insert(0, r'D:\Cardinal\tools')
import patchio

SRC = r'D:\Cardinal\patches\quadeca_scrapyard_final.vcv'
OUT = r'D:\Cardinal\patches\quadeca_scrapyard_final.vcv'

CLK_RUN_OUT = 5      # Clocked OutputIds.RUN_OUTPUT
SEQ_RUN_IN = 1        # Sequencer InputIds.RUN_CV


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

    have = [c for c in cables
            if c['inputModuleId'] == sid and c['inputId'] == SEQ_RUN_IN]
    if have:
        print('RUN 线已存在 ← %s.OUT%d（跳过）'
              % (nm(have[0]['outputModuleId']), have[0]['outputId']))
    else:
        cid = max([c['id'] for c in cables] + [0]) + 1
        proto = next(c for c in cables
                     if c['outputModuleId'] == kid and c['outputId'] == 0)
        c = copy.deepcopy(proto)
        c['id'] = cid
        c['outputModuleId'] = kid
        c['outputId'] = CLK_RUN_OUT
        c['inputModuleId'] = sid
        c['inputId'] = SEQ_RUN_IN
        c.pop('color', None)
        cables.append(c)
        print('新增 Clocked.OUT%d(RUN) → Sequencer.IN%d(RUN_CV)'
              % (CLK_RUN_OUT, SEQ_RUN_IN))

    # ---- 不替李开播 ----
    ck['data']['running'] = False
    seq['data']['running'] = False
    print('running 保持 False —— 李按 Clocked 的 RUN 才启动')

    # ---- 门禁 ----
    seen = {}
    for c in cables:
        k = (c['inputModuleId'], c['inputId'])
        seen[k] = seen.get(k, 0) + 1
    dup = [k for k, v in seen.items() if v > 1]
    assert not dup, '同口多线 %s' % dup
    ids2 = {m['id'] for m in mods}
    dang = [(m['id'], k) for m in mods
            for k in ('leftModuleId', 'rightModuleId')
            if m.get(k) is not None and m[k] not in ids2]
    assert not dang, '悬空指针 %s' % dang

    patch = dict(d)
    patch['modules'] = mods
    patch['cables'] = cables
    patch['path'] = OUT
    patchio.write_patch(OUT, patch, as_archive=True)

    # ---- 回读复验 ----
    back = patchio.read_patch(OUT)
    bc = next(m for m in back['modules'] if m['model'] == 'Clocked')
    bs = next(m for m in back['modules'] if m['model'] == 'Sequencer')
    ckout = sorted({c['outputId'] for c in back['cables']
                    if c['outputModuleId'] == bc['id']})
    seqin = sorted({c['inputId'] for c in back['cables']
                    if c['inputModuleId'] == bs['id']})
    run = [c for c in back['cables']
           if c['inputModuleId'] == bs['id'] and c['inputId'] == SEQ_RUN_IN]
    print()
    print('写出 %s' % OUT)
    print('  模块 %d / 线 %d' % (len(back['modules']), len(back['cables'])))
    print('  Clocked 用到的输出口 = %s（0=CLK，4=RESET，5=RUN）' % ckout)
    print('  Sequencer 用到的输入口 = %s（0=CLOCK，1=RUN_CV）' % seqin)
    print('  RUN 线:', ('Clocked.OUT%d → Sequencer.IN%d ✅'
                        % (run[0]['outputId'], SEQ_RUN_IN)) if run else '❌ 缺')
    print('  Clocked.running=%s  Sequencer.running=%s'
          % (bc['data']['running'], bs['data']['running']))
    assert run and run[0]['outputId'] == CLK_RUN_OUT, 'RUN 线不对'
    t = bs['data']['tracks']
    assert len(t) == 8 and len(t[0]) == 8 and len(t[0][0]) == 16, '矩阵形状被改坏'
    print('  矩阵 8×8×16 未被破坏 ✅')


if __name__ == '__main__':
    main()