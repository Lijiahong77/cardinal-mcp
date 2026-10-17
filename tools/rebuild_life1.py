# -*- coding: utf-8 -*-
"""
life1 重建 —— 以 quadeca_auto_life1__v1339.vcv 为基底（不重跑生成器）。

本轮应用的纪律：
 1. 模块选型：从能打开的机架克隆模板（plugin slug 一律从模板反推）
 2. 端口全部查过源码 enum，不用直觉
 3. 混响做 send 式（并联在声部旁，湿声回混音器），不当终点
 4. 序列器/pianoroll 不自动开播 => sequenceRunning=False
"""
import sys, copy, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
import patchio

ROOT = 'D:/Cardinal'
SRC = ROOT + '/patches/quadeca_auto_life1__v1339.vcv'
STAMP = datetime.datetime.now().strftime('%H%M')
BASE = ROOT + '/patches/_baseline_life1__v%s.vcv' % STAMP
OUT = ROOT + '/patches/quadeca_auto_life1__v%s.vcv' % STAMP

# ---- 模板来源（都是能正常打开的机架）----
TPL = {
    ('Bogaudio', 'Bogaudio-VCO'):  ROOT + '/refs/examples/nooneknowspeter_-_Catalyst.vcv',
    ('Bogaudio', 'Bogaudio-ADSR'): ROOT + '/refs/examples/DRMR_-_BassGrowl.vcv',
    ('MindMeldModular', 'MixMasterJr'): ROOT + '/patches/helm_before_full.vcv',
    ('Valley', 'Feline'):          ROOT + '/refs/examples/VT_-_Jupiter_Ascent.vcv',
}

def find_tpl(plugin, model):
    """从可打开的机架里抓一个该模块的模板（保留真实 plugin/version/params）"""
    path = TPL.get((plugin, model))
    if not path:
        raise SystemExit('无模板: %s/%s' % (plugin, model))
    p = patchio.read_patch(path)
    for m in p['modules']:
        if m['plugin'] == plugin and m['model'] == model:
            return copy.deepcopy(m)
    raise SystemExit('模板机架 %s 里找不到 %s/%s' % (path, plugin, model))

p = patchio.read_patch(SRC)
patchio.write_patch(BASE, p)
print('基准快照 ->', os.path.basename(BASE))

by_model = {}
for m in p['modules']:
    by_model.setdefault(m['model'], []).append(m)

# ---- 新 id 段（避开现有）----
used = {m['id'] for m in p['modules']}
next_id = [max(used) + 1]
def new_id():
    v = next_id[0]; next_id[0] += 1; return v

# ============================================================
# 1) 混音：Fundamental/Mixer -> MindMeldModular/MixMasterJr
#    端口（源码核实）：轨 i 音频 IN(2i)=L / IN(2i+1)=R；主输出 OUT2=L, OUT3=R
# ============================================================
old_mixer = by_model['Mixer'][0]
tpl = find_tpl('MindMeldModular', 'MixMasterJr')
tpl['id'] = new_id()
tpl['pos'] = [old_mixer['pos'][0], old_mixer['pos'][1]]
tpl['leftModuleId'] = None
tpl['rightModuleId'] = None
p['modules'] = [m for m in p['modules'] if m['id'] != old_mixer['id']]
p['modules'].append(tpl)          # ← 必须真的插入模块表，否则接线指向不存在的模块
MIX = tpl['id']
assert MIX in {m['id'] for m in p['modules']}, 'MixMasterJr 没进模块表'

# 三路 VCA -> MixMasterJr 轨1/2/3 的 L 口（单声道源只接 L）
vcas = by_model['VCA-1']
old_cables = [c for c in p['cables']
              if c['outputModuleId'] == old_mixer['id'] or c['inputModuleId'] == old_mixer['id']]
p['cables'] = [c for c in p['cables'] if c not in old_cables]
for i, v in enumerate(vcas):
    p['cables'].append({
        'id': new_id(),
        'outputModuleId': v['id'], 'outputId': 0,
        'inputModuleId': MIX, 'inputId': 2 * i,
    })

# 主输出接回 HostAudio2：MixMasterJr OUT2=L, OUT3=R（源码核实）
# HostAudio2 IN0=左 IN1=右 —— 这是唯一保持真立体声的地方
host = [m for m in p['modules'] if m['model'] == 'HostAudio2'][0]
p['cables'].append({'id': new_id(), 'outputModuleId': MIX, 'outputId': 2,
                    'inputModuleId': host['id'], 'inputId': 0})
p['cables'].append({'id': new_id(), 'outputModuleId': MIX, 'outputId': 3,
                    'inputModuleId': host['id'], 'inputId': 1})

# ============================================================
# 2) 振荡器：Fundamental/VCO -> Bogaudio/Bogaudio-VCO
#    端口（VCO.hpp:22-35）：IN0=PITCH, IN1=SYNC, IN2=PW, IN3=FM
#                          OUT0=SQUARE, OUT1=SAW, OUT2=TRI, OUT3=SINE
# ============================================================
def swap_module(old, plugin, model, in_map):
    """替换单个模块，按 in_map 改写它身上的接线"""
    tpl = find_tpl(plugin, model)
    keep_id = old['id']
    old_pos = list(old['pos'])
    old_in = [c for c in p['cables'] if c['inputModuleId'] == keep_id]
    old_out = [c for c in p['cables'] if c['outputModuleId'] == keep_id]
    for c in old_in + old_out:
        p['cables'].remove(c)

    tpl['id'] = keep_id          # 保 id，让外部接线不动
    tpl['pos'] = old_pos
    tpl['leftModuleId'] = None
    tpl['rightModuleId'] = None
    idx = p['modules'].index(old)
    p['modules'][idx] = tpl

    for c in old_in:
        tgt = in_map.get(c['inputId'])
        if tgt is None:
            # 目标模块没有这个口 —— 明确丢弃这条线，不静默硬接
            print('  丢弃入线 IN%d -> %s/%s（该模块无此口）'
                  % (c['inputId'], plugin, model))
            continue
        p['cables'].append({
            'id': new_id(),
            'outputModuleId': c['outputModuleId'], 'outputId': c['outputId'],
            'inputModuleId': keep_id, 'inputId': tgt,
        })
    for c in old_out:
        p['cables'].append(c)
    return keep_id

vcos = by_model['VCO']
vco_ids = []
for i, v in enumerate(vcos):
    # Fundamental/VCO OUT1=TRI? / OUT2=SQR —— 统一改成 Bogaudio OUT2=TRI(最接近原三角波音色)
    swap_module(v, 'Bogaudio', 'Bogaudio-VCO', {0: 0})
    # 找到它那条音频出线，重指向 OUT2(TRI)
    for c in p['cables']:
        if c['outputModuleId'] == v['id']:
            c['outputId'] = 2
    vco_ids.append(v['id'])

# ============================================================
# 3) 包络：Fundamental/ADSR -> Bogaudio/Bogaudio-ADSR
#    端口（ADSR.hpp:20-27）：只有 IN0=GATE，OUT0=Envelope
#    ⇒ 现有那条 pianoroll.OUT7(RETRIG) → IN5 必须撤掉（Bogaudio 无此口）
# ============================================================
adirs = by_model['ADSR']
for a in adirs:
    # Fundamental/ADSR IN4=GATE -> Bogaudio IN0=GATE；IN5=RETRIG -> 丢弃（Bogaudio 无此口）
    swap_module(a, 'Bogaudio', 'Bogaudio-ADSR', {4: 0, 5: None})

# ============================================================
# 4) 混响 send：Valley/Feline（用户说别用用过的 Galaxy）
#    端口（Feline.hpp:36-49）：IN0=L IN1=R / OUT0=L OUT1=R OUT2=SUM
#    做法：pianoroll 的 gate 作为 send 触发源太复杂，
#         这里用【干声总线分一路】做 send —— 但 MixMasterJr 已是最后一级，
#         所以改用：声部 1/3 的 VCA 额外各引一根到 Feline，湿声回 MixMasterJr 轨 4/5。
#    ⚠ 同一模块的同一输入口只能接一根线 —— 三个 VCA 分别接 Feline IN0 会挤掉，
#      故用 MindMeld 之外的口：Feline IN0 只接声部1，IN1 只接声部3。
# ============================================================
fel = find_tpl('Valley', 'Feline')
fel['id'] = new_id()
fel['pos'] = [124, 4]
fel['leftModuleId'] = None
fel['rightModuleId'] = None
p['modules'].append(fel)
FEL = fel['id']

# send 分线：声部1 的 VCA → Feline IN0（左），声部3 的 VCA → Feline IN1（右）
# 同一个输入口只能接一根线，所以左右各接一路，中间那层不进混响。
# 输出端可以扇出（VCA.OUT0 已有线进 MIX，再引一根进 Feline 不冲突）。
p['cables'].append({'id': new_id(), 'outputModuleId': vcas[0]['id'], 'outputId': 0,
                    'inputModuleId': FEL, 'inputId': 0})
p['cables'].append({'id': new_id(), 'outputModuleId': vcas[2]['id'], 'outputId': 0,
                    'inputModuleId': FEL, 'inputId': 1})

# 湿声进混音器轨 4（L=IN6）
p['cables'].append({'id': new_id(), 'outputModuleId': FEL, 'outputId': 0,
                    'inputModuleId': MIX, 'inputId': 6})

# ============================================================
# 5) 不自动开播
# ============================================================
for m in p['modules']:
    if m['model'] == 'rcm-pianoroll':
        m['data']['sequenceRunning'] = False

# ---- 落盘前总断言：所有线的两端都必须指向真实存在的模块 ----
live = {m['id'] for m in p['modules']}
for c in p['cables']:
    assert c['outputModuleId'] in live, '线 %s 的输出端模块不存在' % c['id']
    assert c['inputModuleId'] in live, '线 %s 的输入端模块不存在' % c['id']
assert len(live) == len(p['modules']), '模块表有重复 id'

patchio.write_patch(OUT, p)
print('交付 ->', os.path.basename(OUT))
print('模块 %d / 线 %d' % (len(p['modules']), len(p['cables'])))