# -*- coding: utf-8 -*-
"""life1 交付版自查：端口核对 + 同口挤占 + 悬空指针 + 死胡同 + 自动开播"""
import sys, os, collections
sys.path.insert(0, os.path.dirname(__file__))
import patchio

F = sys.argv[1] if len(sys.argv) > 1 else 'D:/Cardinal/patches/quadeca_auto_life1__v1942.vcv'
p = patchio.read_patch(F)
mods = p['modules']
name = {m['id']: '%s/%s' % (m['plugin'], m['model']) for m in mods}
pos = {m['id']: m.get('pos') for m in mods}
errs = []

# 1) 悬空指针
ids = {m['id'] for m in mods}
for m in mods:
    for k in ('leftModuleId', 'rightModuleId'):
        v = m.get(k)
        if v not in (None, '') and v not in ids:
            errs.append('悬空指针 %s %s=%s' % (name[m['id']], k, v))

# 2) 同口挤占（一个输入口接多根线 = 后一根挤掉前一根）
slot = collections.Counter()
for c in p['cables']:
    slot[(c['inputModuleId'], c['inputId'])] += 1
for (mid, pid), n in slot.items():
    if n > 1:
        errs.append('同口挤占 %s IN%d 接了 %d 根线' % (name[mid], pid, n))

# 3) 音频路径核对表（全部查过源码 enum）
PITCH_IN = {'AudibleInstruments/Rings': 6, 'Fundamental/VCO': 0, 'Bogaudio/Bogaudio-VCO': 0}
GATE_IN = {'Fundamental/ADSR': 4, 'Bogaudio/Bogaudio-ADSR': 0,
           'WSTD-Drums/BassDrum9': 16, 'WSTD-Drums/SnareDrumN': 16}
RINGS_PITCH = 6
MIXMASTER_TRACK = {'MindMeldModular/MixMasterJr': (2, 2)}  # 2i=L, 2i+1=R
FELINE = {'Valley/Feline': dict(Lin=0, Rin=1, Lout=0, Rout=1, Sum=2)}

print('=== 接线全表 ===')
for c in sorted(p['cables'], key=lambda x: name[x['outputModuleId']]):
    print('  %-34s OUT%-2d -> %-34s IN%-2d'
          % (name[c['outputModuleId']], c['outputId'],
             name[c['inputModuleId']], c['inputId']))

# 4) 音高口
for c in p['cables']:
    tgt = name[c['inputModuleId']]
    src = name[c['outputModuleId']]
    if 'pianoroll' in src and 'VCO' in tgt and 'Rings' not in tgt:
        exp = PITCH_IN.get(tgt)
        if exp is not None and c['inputId'] != exp:
            errs.append('音高口错 %s -> %s 应 IN%d 实 IN%d' % (src, tgt, exp, c['inputId']))
    if 'pianoroll' in src and 'Rings' in tgt and c['inputId'] != RINGS_PITCH:
        errs.append('Rings 音高口应 IN%d 实 IN%d' % (RINGS_PITCH, c['inputId']))
    if 'pianoroll' in src and 'ADSR' in tgt:
        exp = GATE_IN.get(tgt)
        if exp is not None and c['inputId'] != exp:
            errs.append('ADSR 门口错 %s -> %s 应 IN%d 实 IN%d' % (src, tgt, exp, c['inputId']))

# 5) 死胡同（有入线零出线 / 有出线零入线）
for m in mods:
    nin = sum(1 for c in p['cables'] if c['inputModuleId'] == m['id'])
    nout = sum(1 for c in p['cables'] if c['outputModuleId'] == m['id'])
    if nin > 0 and nout == 0 and 'Audio' not in m['model'] and 'Text' not in m['model']:
        errs.append('死胡同 %s 有入线(%d)零出线' % (name[m['id']], nin))

# 6) 自动开播
for m in mods:
    d = m.get('data') or {}
    if d.get('sequenceRunning'):
        errs.append('自动开播 %s sequenceRunning=True' % name[m['id']])
    if m['model'] == 'Clocked' and d.get('running'):
        errs.append('Clocked running=True')

# 6b) 🔴 序列模块必须有 RUN 线（只有 clock 不动 —— 李19:40 的血泪）
for m in mods:
    if m['model'] != 'rcm-pianoroll':
        continue
    has_clock = any(c['inputModuleId'] == m['id'] and c['inputId'] == 0 for c in p['cables'])
    has_run = any(c['inputModuleId'] == m['id'] and c['inputId'] == 1 for c in p['cables'])
    if has_clock and not has_run:
        errs.append('缺 RUN 线 %s：接了 CLOCK(IN0) 但没接 RUN(IN1) ⇒ 永不出声' % name[m['id']])
    if not has_clock and not has_run:
        errs.append('%s 既无 CLOCK 也无 RUN，完全没被驱动' % name[m['id']])

# 7) data 类型
for m in mods:
    if m.get('version') is None or not isinstance(m.get('version'), str):
        errs.append('version 非字符串 %s' % name[m['id']])
    if 'data' in m and m['data'] is None:
        errs.append('data=None %s' % name[m['id']])
    if 'plugin' not in m:
        errs.append('缺 plugin 字段 %s' % name.get(m['id'], m.get('id')))

# 8) 摆放重叠（同 pos）
seen = collections.Counter(tuple(m.get('pos') or []) for m in mods)
for k, n in seen.items():
    if n > 1:
        errs.append('摆放重叠 pos=%s 有 %d 个模块' % (list(k), n))

print()
print('模块 %d / 线 %d' % (len(mods), len(p['cables'])))
if errs:
    print('❌ 问题 %d：' % len(errs))
    for e in errs:
        print('  ✗', e)
else:
    print('✅ 全部检查通过')