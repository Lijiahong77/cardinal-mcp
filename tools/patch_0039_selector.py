# -*- coding: utf-8 -*-
"""
把 0039 版（李/对方 agent 在用的演奏版）做最小选型融合（2026-10-18）：

  BassDrum9 (TR909 电子底鼓) → CR78 (Roland CompuRhythm 1978 模拟电路鼓)
     依据：修羅鼓谱实证是原声鼓组；CR78 温暖圆润是库里最贴原声方向的型号。
     保留对方其他一切：param16/17=1.0 速度、Mixer 0.85、MixMasterJr 八轨推子、
     8 小节录音内容（BASS/CHD-*/KICK/SNARE/HAT/RIFF）、全部接线。
     只改两个采样号：
       param0: 1.0(909采样02) → 0.0(CR78采样01, 大小/面板首位推断为底鼓)
       param1: 7.0 → 3.0(CR78采样03, 李 helm_drums.vcv 验证过)

  Plateau (界面不直观) → SurgeXTFXReverb2 (李自己 Final Patch Work 在用的 Surge XT 系)
     保留 inline 位置（主输出后）与对方的轻湿调音（Wet 0.12）。
     参数映射（源码 Reverb2Effect.cpp 参数序）：
       Plateau Dry1.0/Wet0.12 inline → Reverb2 Mix 0.12（干湿交叉等效）
       Size 0.45 → Room Size 0.45 ｜ Decay 0.5 → Decay 0.5
       Diffusion 7(0-10) → 0.7 ｜ Pre 0.02s → 0.02 ｜ Mod rate 0.15 → 0.15
        Plateau 滤波 10=最通透 → Damping 0=不衰减 ｜ Width 1.0
     ⚠️ param 数量不同（Plateau 31 vs Reverb2 60）⇒ 不能原地改 model，
       必须 deepcopy Reverb2 模板再替换（宪法：A 模块克隆不能顶替 B）。

输入：D:/Cardinal/patches/base_0039_before_selector_1018.vcv（0039 备份，含录音）
输出：D:/Cardinal/patches/yorushika_shura_live.vcv
"""
import sys, copy, os
sys.path.insert(0, os.path.dirname(__file__))
import patchio

ROOT = 'D:/Cardinal'
SRC = ROOT + '/patches/base_0039_before_selector_1018.vcv'
OUT = ROOT + '/patches/yorushika_shura_live.vcv'
TPL_REV = ROOT + '/patches/Final Patch Work.vcv'   # SurgeXTFXReverb2 模板（李自己在用）

p = patchio.read_patch(SRC)
ids = {m['id'] for m in p['modules']}
n_before = len(p['modules'])

# ---------- 1) BassDrum9 → CR78（同包同基类, 32 params/48 in/16 out 结构相同, 原地改安全）
bd = next(m for m in p['modules'] if m['model'] == 'BassDrum9')
assert bd['plugin'] == 'WSTD-Drums', 'BassDrum9 的 plugin 不是 WSTD-Drums: %s' % bd['plugin']
bd['model'] = 'CR78'
ps = {x['id']: x for x in bd['params']}
assert len(ps) == 32, 'CR78 param 数量不是 32'
ps[0]['value'] = 0.0     # 声部1 采样01（推断底鼓）
ps[1]['value'] = 3.0     # 声部2 采样03（李验证）
# param16/17（速度）保持 1.0 原值不动
print('BassDrum9 -> CR78: p0=%.1f(909采样02->CR78采样01) p1=%.1f->3.0(李验证采样03)'
      % (1.0, 7.0))

# ---------- 2) Plateau → SurgeXTFXReverb2（param 数不同 ⇒ deepcopy 模板替换, id 保持不变）
tpl_patch = patchio.read_patch(TPL_REV)
tpl = next(m for m in tpl_patch['modules'] if m['model'] == 'SurgeXTFXReverb2')
assert len(tpl['params']) == 60, 'Reverb2 模板 param 数不是 60: %d' % len(tpl['params'])

plateau = next(m for m in p['modules'] if m['model'] == 'Plateau')
plateau_id = plateau['id']
# 该 id 上现有接线（保持不变, 只换模块本体）
n_cables_in = sum(1 for c in p['cables'] if c['inputModuleId'] == plateau_id)
n_cables_out = sum(1 for c in p['cables'] if c['outputModuleId'] == plateau_id)
print('Plateau -> SurgeXTFXReverb2: id=%s 上有 %d 入 %d 出接线（保持不动）'
      % (plateau_id, n_cables_in, n_cables_out))

new_rev = copy.deepcopy(tpl)
new_rev['id'] = plateau_id          # 🔴 id 不变 ⇒ 所有接线原样有效
new_rev['pos'] = plateau['pos']     # 保留位置
new_rev['leftModuleId'] = None
new_rev['rightModuleId'] = None
new_rev['version'] = '2.0'
if new_rev.get('data') is None:
    new_rev['data'] = {}
# inline 轻湿配方（ Plateau Dry1.0/Wet0.12/Size0.45/Decay0.5/Diff7/Pre0.02/ModRate0.15 等效映射）
REV_PARAMS = {0: 0.02,   # Pre-Delay 秒
              1: 0.45,   # Room Size
              2: 0.50,   # Decay Time
              3: 0.70,   # Diffusion
              4: 0.0,    # Buildup
              5: 0.15,   # Modulation（触控条 CC1 目标, 归零=自然态）
              6: 0.0,    # HF Damping（Plateau 滤波10=最通透 → 0=不衰减）
              7: 0.0,    # LF Damping
              8: 1.0,    # Width
              9: 0.12}   # Mix = Plateau Wet 0.12 等效（inline 轻湿）
for pid, val in REV_PARAMS.items():
    new_rev['params'][pid]['value'] = float(val)

# 替换模块条目
for i, m in enumerate(p['modules']):
    if m['id'] == plateau_id:
        p['modules'][i] = new_rev
        break

# ---------- 3) 自审（宪法四查）
assert len(p['modules']) == n_before, '模块数变了 (%d -> %d)' % (n_before, len(p['modules']))
live = {m['id'] for m in p['modules']}
assert len(live) == len(p['modules']), '重复 id'
for c in p['cables']:
    assert c['outputModuleId'] in live and c['inputModuleId'] in live, '线端模块不存在'
seen = set()
for c in p['cables']:
    k = (c['inputModuleId'], c['inputId'])
    assert k not in seen, '同口挤占 %s IN%d' % k
    seen.add(k)
for m in p['modules']:
    for k in ('leftModuleId', 'rightModuleId'):
        assert m.get(k) is None or m[k] in live, '悬空指针 %s %s' % (m['model'], k)
    assert isinstance(m.get('version'), str), '%s version 非字符串' % m['model']
    assert m.get('data') is not None, '%s data 为 None' % m['model']
# 录音内容必须原样还在
ma = next(m for m in p['modules'] if m['model'] == 'Starsea-MiniArranger')
notes = sum(len(t.get('notes') or []) for t in (ma['data']['arranger']['tracks']))
assert notes == 76, 'MiniArranger 录音笔记数不对: %d（应 76：BASS64+CHD12）' % notes
ex = next(m for m in p['modules'] if m['model'] == 'Starsea-MiniArrangerExpander')
enotes = sum(len(t.get('notes') or []) for t in (ex['data']['arranger']['tracks']))
assert enotes == 240, 'Expander 录音笔记数不对: %d（应 240：KICK32+SNARE16+HAT128+RIFF64）' % enotes
print('录音内容保留：主机 %d 音 + Expander %d 音' % (notes, enotes))

patchio.write_patch(OUT, p)
print('交付 ->', os.path.basename(OUT))
print('模块 %d / 线 %d（与源一致）' % (len(p['modules']), len(p['cables'])))
