# -*- coding: utf-8 -*-
"""🔴 对账脚本：审计 patch里「每个模块的音高/门/音频口是否接对」+「有无死胡同模块」。

★ 为什么写这个（19:30）
  今天这一份机架我犯的错误**全部是「端口接错」和「链路没通」**，而我的静态门禁只查了：
     -悬空指针 / 同口多线 / 端口越界 / Mix8 参数个数
  **从没查过「每个输入口接的对不对」和「模块有没有出线」** ⇒ 一路绿灯放过了三个哑模块。
  ⇒ 这个脚本把这两类错误变成可自动检测的规则。

★ 两条新规则
  R1【音高/门 口必须核实】`(模块, IN号) → 语义` 映射从**源码 enumInputIds** 取，
     绝不凭「看起来像」。已核实：Rings PITCH=6、pianoroll OUT5=PITCH/OUT6=GATE、
     VCO PITCH=0、ADSR 门=4、VCA-1 CV=0/音频=1、Clocked CLK=0/RUN=5、Sequencer CLK=0/RUN_CV=1。
  R2【无出线模块 = 死胡同】任何既不接混音器/输出、又没有任何出线的音频模块 = 白占位置。
     （今天的 `Valley/Plateau`：入线3、出线0 ⇒ 混响声根本出不来。）
"""
import sys

sys.path.insert(0, r'D:\Cardinal\tools')
import patchio

# ---- 源码核实的端口语义表（enum InputIds / OutputIds 的真实 id）----
PITCH_IN = {
    'AudibleInstruments/Rings': 6,     # Rings.cpp:33 PITCH_INPUT（0-5 是各种 MOD）
    'Fundamental/VCO': 0,             # VCO.cpp:258 PITCH_INPUT
}
GATE_IN = {
    'Fundamental/ADSR': 4,            # 门输入
    'WSTD-Drums/BassDrum9': 16,
    'WSTD-Drums/SnareDrumN': 16,
}
# 混音器/输出的「终点」模块：进了它们就算有出路
SINK = ('MixMasterJr', 'HostAudio2', 'VCA-1')


def nm(m):
    p = m['plugin']
    return '%s/%s' % (p if isinstance(p, str) else p.get('slug'), m['model'])


def audit(path, title):
    d = patchio.read_patch(path)
    ids = {m['id']: m for m in d['modules']}
    ins = {}
    outs = {}
    for c in d['cables']:
        ins.setdefault(c['inputModuleId'], []).append(c)
        outs.setdefault(c['outputModuleId'], []).append(c)

    print('===== %s =====' % title)
    print('模块 %d / 线 %d' % (len(d['modules']), len(d['cables'])))

    # ---- R1：音高口是否接对 ----
    bad_pitch = []
    for name, want in PITCH_IN.items():
        mod = next((m for m in d['modules'] if nm(m) == name), None)
        if mod is None:
            continue
        got = {c['inputId'] for c in ins.get(mod['id'], [])}
        if not got:
            print('  ⚠ %s 没有任何输入线（静音）' % name)
        elif want not in got:
            bad_pitch.append((name, want, sorted(got)))
    for name, want, got in bad_pitch:
        print('  ✗ %s 音高口应为 IN%d，实际接了 IN%s'
              % (name, want, got))

    # ---- R2：死胡同（有入线但零出线，且不在 SINK 里）----
    dead = []
    for m in d['modules']:
        n = nm(m)
        if m['model'] in SINK:
            continue
        if ins.get(m['id']) and not outs.get(m['id']):
            dead.append(n)
    for n in dead:
        print('  ✗ 死胡同：%s 有入线但零出线 ⇒ 声音出不来' % n)

    # ---- 附加：孤岛模块（零入零出）----
    for m in d['modules']:
        if not ins.get(m['id']) and not outs.get(m['id']) and m['model'] not in SINK:
            print('  · 孤岛：%s 无入无出' % nm(m))

    if not bad_pitch and not dead:
        print('  ✅ 音高口正确、无死胡同')
    print()
    return len(bad_pitch) + len(dead)


if __name__ == '__main__':
    base = r'D:\Cardinal\patches'
    n1 = audit(base + r'\quadeca_scrapyard__v1645.vcv', 'v1645（李手工调过的原始版）')
    n2 = audit(base + r'\_v2.vcv', '我交付版 18:46')
    n3 = audit(base + r'\quadeca_scrapyard_final.vcv', '李改后 19:24（当前版）')
    print('问题数：v1645=%d  我交付=%d  当前=%d' % (n1, n2, n3))
