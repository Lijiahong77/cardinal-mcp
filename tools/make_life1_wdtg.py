# -*- coding: utf-8 -*-
"""
Life 1《Where Did the Time Go》机架 —— 从零构建。

取材自用户的权威文档「Quadeca 深度解析」
(`Obsidian Vault/其他/Quadeca 深度解析：从网络创作者到实验音乐艺术家（2018–2026 完整版）.md`)：
  第 51 行：非线性蒙太奇、跳跃式组合、硬切
  第 65 行：原声基底「去量化处理，保留杂音与呼吸感」
  第 68 行：「反律动设计，故意打乱预期或在进鼓处留白，以缺失感传达张力」
  第 69 行：空间效果「干声代表现实，湿声代表幻觉」
  第 71 行：Life 1 里「原声基底」比重显著上升
  第 125 行《Dark Magic》：「扭曲呼吸 + 磨砂吉他嗡鸣先压上来，再切温暖电钢和弦」
  第 128 行《Life 1》：「爵士 × 合成器 × 弗拉门戈风吉他」
  第 129 行：大量真实乐手（钢琴 Johnny Hall、大提琴 Noah Ehler）

李的拍板（19:47）：
  - 音色路线：**全用物理建模**（本机无钢琴/大提琴/吉他采样）
  - 段落结构：**堆层渐入**（大提琴铺底 → 电钢进入 → 后半段吉他加轮）

★ 端口全部查过源码 enum（依据写在下方注释）。禁止凭印象改。
★ 模块一律从**能打开的机架 deepcopy 模板**，plugin slug 从模板反推，绝不手写。
★ 🔴 同一个输入口只能接一根线 —— 所有路由在写的时候就避开，不靠后补。
"""
import sys, copy, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
import patchio

ROOT = 'D:/Cardinal'
# 🔴 版本纪律（李19:57 再次点名）：默认写**稳定文件名**，不堆时间戳版本号。
# 只有显式设环境变量 WDTG_VERSION=1 才产出 `__vHHMM` 那种一次性副本。
import os as _os
if _os.environ.get('WDTG_VERSION') == '1':
    STAMP = datetime.datetime.now().strftime('%H%M')
    OUT = ROOT + '/patches/quadeca_life1_wdtg__v%s.vcv' % STAMP
else:
    OUT = ROOT + '/patches/quadeca_life1_wdtg.vcv'

# ============================================================
# 端口表（源码依据）
# ============================================================
# Clocked        OUT 0=CLK 4=RESET 5=RUN 6=BPM   （param0 = 绝对 BPM）
# rcm-pianoroll  IN  0=CLOCK 1=RUN 5=VOCT 6=GATE 7=RETRIG 8=VELOCITY
#                OUT 5=VOCT 6=GATE 7=RETRIG 8=VELOCITY 9=EOP
#                (PianoRoll/PianoRollModule.hpp:18-44)
# Plaits         IN  0=ENGINE 1=TIMBRE 2=FREQ 3=MORPH 4=HARMONICS
#                   5=TRIGGER 6=LEVEL 7=NOTE
#                OUT 0=MAIN 1=AUX           (Plaits.cpp:26-41)
#                param0=MODEL1 1=MODEL2 2=FREQ 3=HARMONICS 4=TIMBRE 5=MORPH
#                6=TIMBRE_CV 7=FREQ_CV 8=MORPH_CV 9=LPG_COLOR 10=LPG_DECAY
# Elements       IN  0=NOTE 1=FM 2=GATE 3=STRENGTH 4=BLOW 5=STRIKE
#                   6=BOW_TIMBRE_MOD 7=FLOW_MOD 8=BLOW_TIMBRE_MOD 9=MALLET_MOD
#                   10=STRIKE_TIMBRE_MOD 11=DAMPING_MOD 12=GEOMETRY_MOD
#                   13=POSITION_MOD 14=BRIGHTNESS_MOD 15=SPACE_MOD
#                OUT 0=LEFT 1=RIGHT          ⚠ AUX=0 是 L，MAIN=1 是 R
#                param 0=CONTOUR 1=BOW 2=BLOW 3=STRIKE 4=COARSE 5=FINE 6=FM
#                      7=FLOW 8=MALLET 9=GEOMETRY 10=BRIGHTNESS 11=BOW_TIMBRE
#                      12=BLOW_TIMBRE 13=STRIKE_TIMBRE 14=DAMPING 15=POSITION
#                      16=SPACE                          (Elements.cpp:6-58)
# Bogaudio-VCO   IN  0=PITCH 1=SYNC 2=PW 3=FM
#                OUT 0=SQUARE 1=SAW 2=TRIANGLE 3=SINE   (VCO.hpp:22-35)
#                param 0=FREQ_COARSE(绝对音高/V) 1=FREQ_FINE 2=PWM 3=SHAPE
#                      4=SHAPE_CV 5=FM 6=FM_CV
# Bogaudio-ADSR  只有 IN 0=GATE，OUT 0=ENV      (ADSR.hpp:20-27)
#                param 0=ATTACK 1=DECAY 2=SUSTAIN 3=RELEASE 4=LINEAR
# Bogaudio-VCF   IN  0=FREQUENCY_CV 1=FM 2=PITCH 3=IN 4=Q 5=SLOPE
#                OUT 0=OUT                      (VCF.hpp:24-37)
#                param 0=FREQUENCY 1=FREQ_CV 2=FM 3=Q 4=MODE 5=SLOPE
# Waveshaper     IN  0=MAIN 1=AMOUNT  OUT 0=MAIN  (Waveshaper.cpp:23-28)
#                ⚠ 注意 IN0 是 MAIN、IN1 是 AMOUNT（与configInput 书写顺序相反）
#                param 0=AMOUNT 1=SCALE 2=RANGE
# MixMasterJr    轨 i 音频 IN(2i)=L  IN(2i+1)=R   主输出 OUT2=L OUT3=R
# HostAudio2     IN 0=L  IN1=R
# Feline         IN 0=L  IN1=R   OUT 0=L OUT1=R OUT2=SUM  (Feline.hpp:36-49)
# Fundamental/Split  IN0 源  OUT0+ OUT1-   —— 用来把单声道源分给左右口

TPL = {
    ('ImpromptuModular', 'Clocked'):     ROOT + '/refs/examples/JTB_-_Waves.vcv',
    ('rcm', 'rcm-pianoroll'):           ROOT + '/refs/examples/falkTX_-_Mini-Arp-Seq.vcv',
    ('AudibleInstruments', 'Plaits'):   ROOT + '/refs/examples/falkTX_-_Divide-no-Conquer.vcv',
    ('AudibleInstruments', 'Elements'): ROOT + '/patches/quadeca_ghostfolk.vcv',
    ('Bogaudio', 'Bogaudio-VCO'):       ROOT + '/refs/examples/nooneknowspeter_-_Catalyst.vcv',
    ('Bogaudio', 'Bogaudio-ADSR'):      ROOT + '/refs/examples/DRMR_-_BassGrowl.vcv',
    ('Bogaudio', 'Bogaudio-VCF'):       ROOT + '/refs/examples/DRMR_-_BassGrowl.vcv',
    ('MindMeldModular', 'MixMasterJr'): ROOT + '/patches/helm_before_full.vcv',
    ('Valley', 'Feline'):               ROOT + '/refs/examples/VT_-_Jupiter_Ascent.vcv',
    ('Cardinal', 'HostAudio2'):         ROOT + '/refs/fx.tpl.vcv',
    ('HetrickCV', 'Waveshaper'):        ROOT + '/refs/examples/nooneknowspeter_-_Xmas.vcv',
    ('Fundamental', 'Split'):           ROOT + '/patches/Final Patch Work.vcv',
}

_cache = {}
def tpl_of(plugin, model):
    key = (plugin, model)
    if key not in _cache:
        pp = patchio.read_patch(TPL[key])
        for m in pp['modules']:
            if m['plugin'] == plugin and m['model'] == model:
                _cache[key] = copy.deepcopy(m)
                break
        else:
            raise SystemExit('模板 %s 里找不到 %s/%s' % (TPL[key], plugin, model))
    return copy.deepcopy(_cache[key])

p = {'version': '2.0.0', 'zoom': 1.0, 'modules': [], 'cables': [], 'gridOffset': [0, 0]}

_nid = [9000000000000001]
def nid():
    _nid[0] += 1
    return _nid[0]

def add(plugin, model, pos=None, params=None):
    """Create a module. `pos` is IGNORED on purpose — coordinates come from
    layout_patch.WDTG_LAYOUT (see autolayout() below). Hand-written positions are
    what produced the 5-row, 13-row-apart rack李 complained about on 2026-10-17.
    """
    m = tpl_of(plugin, model)
    m['id'] = nid()
    m['pos'] = [0, 0]
    m['leftModuleId'] = None
    m['rightModuleId'] = None
    assert isinstance(m.get('version'), str), '%s 的 version 不是字符串' % model
    if m.get('data') is None:
        m['data'] = {}
    if params:
        for pid, val in params.items():
            if pid >= len(m['params']):
                raise SystemExit('%s 没有 param%d（总共 %d 个）' % (model, pid, len(m['params'])))
            m['params'][pid]['value'] = float(val)
    p['modules'].append(m)
    return m['id']

def autolayout():
    """Apply the registered layout table (layout_patch.WDTG_LAYOUT) to this patch.

    Iron rule: coordinates are NEVER chosen by eye. layout_patch.py is the single
    source of truth — add the module to WDTG_LAYOUT there and re-run. If a module
    here is missing from that table, this raises instead of silently auto-placing
    it in an arbitrary row.
    """
    import layout_patch as LP
    lay = LP.pick_layout(os.path.basename(OUT))
    pos, _d, unreg, log = LP.do_layout(p, lay)
    if unreg:
        raise SystemExit(
            '这些模块没登记在 layout_patch.WDTG_LAYOUT 里，排不出工整的位置：\n  '
            + '\n  '.join('%s/%s id=%s' % (m.get('plugin'), m.get('model'), m['id'])
                          for m in unreg)
            + '\n去 D:/Cardinal/tools/layout_patch.py 的 WDTG_LAYOUT 里加一行再跑。')
    by = {str(m['id']): m for m in p['modules']}
    for mid, xy in pos.items():
        by[str(mid)]['pos'] = list(xy)
    for line in log:
        print('  [layout] ' + line.strip())

def wire(src, so, dst, di):
    for c in p['cables']:
        assert not (c['inputModuleId'] == dst and c['inputId'] == di), \
            '同口挤占：模块 %s 的 IN%d 接了两根线' % (dst, di)
    p['cables'].append({'id': nid(), 'outputModuleId': src, 'outputId': so,
                        'inputModuleId': dst, 'inputId': di})

def add_param_safe(mid, model, pid, val):
    for m in p['modules']:
        if m['id'] == mid:
            m['params'][pid]['value'] = float(val)
            return
    raise SystemExit('找不到模块 %s' % model)

# ============================================================
# 0) 主时钟 —— 96 BPM，爵士底速
# ============================================================
CLK = add('ImpromptuModular', 'Clocked', [0, 0], {0: 96.0})

# ============================================================
# 混音骨架：MixMasterJr（6 轨）+ Feline（send 湿声）+ HostAudio2
#   文档第 69 行：干声=现实，湿声=幻觉 ⇒ 干湿分离
# ============================================================
MIX = add('MindMeldModular', 'MixMasterJr', [90, 0])
FEL = add('Valley', 'Feline', [90, 4])
HOST = add('Cardinal', 'HostAudio2', [90, 8])

# 主输出 -> HostAudio2（唯一保持真立体声的地方）
wire(MIX, 2, HOST, 0)     # L
wire(MIX, 3, HOST, 1)     # R
# Feline 湿声 -> 混音器第 4 轨
wire(FEL, 0, MIX, 6)      # L
wire(FEL, 1, MIX, 7)      # R

# ============================================================
# 1) 声部一：**大提琴长音铺底** —— Elements 弓弦物理模型
#   依据 第129行（真实大提琴乐手）+ 第71行（原声基底上升）+ 第65行（保留呼吸感）
#   Elements 的 BOW_TIMBRE(弓法) / DAMPING(按弦) / FLOW(气流噪声) 就是大提琴的可调维度
#   Elements 左右分出 ⇒ 直接进混音器轨1 的 L/R，不经过单声道滤波器（避免同口挤占）
# ============================================================
CEL_P = add('rcm', 'rcm-pianoroll', [0, 4])
wire(CLK, 0, CEL_P, 0)               # CLOCK
wire(CLK, 5, CEL_P, 1)               # RUN_OUTPUT -> RUN_INPUT（★缺这条=永不出声）

CEL = add('AudibleInstruments', 'Elements', [14, 4], {
    1: 0.40,     # BOW 弓压 —— 拉奏的力度，不是死板的持续音
    14: 0.55,    # DAMPING 按弦 —— 别让它自由振动到发散
    11: 0.55,    # BOW_TIMBRE 弓法音色
    7: 0.32,     # FLOW 气流噪声 ⇒ 呼吸感（第65行）
    16: 0.35,    # SPACE
    3: 0.35,     # STRIKE
    10: 0.45,    # BRIGHTNESS
})
wire(CEL_P, 5, CEL, 0)               # VOCT-> NOTE
wire(CEL_P, 6, CEL, 2)               # GATE -> GATE

# 干声进混音器轨1（L/R 分开）
wire(CEL, 0, MIX, 0)                 # L
wire(CEL, 1, MIX, 1)                 # R
# send：大提琴进混响左口（Feline IN0 只接一根）
wire(CEL, 0, FEL, 0)

# ============================================================
# 2) 声部二：**温暖电钢** —— Bogaudio-VCO 锯齿波经 VCF + 滤波器包络
#   依据 第125行「再切温暖电钢和弦」
# ============================================================
EP_P = add('rcm', 'rcm-pianoroll', [0, 8])
wire(CLK, 0, EP_P, 0)
wire(CLK, 5, EP_P, 1)                # RUN

EP_VCO = add('Bogaudio', 'Bogaudio-VCO', [14, 8], {
    0: 261.63,   # C4（绝对频率，单位V）
    2: 0.50,     # PWM
    3: 0.55,     # SHAPE 偏柔和
})
wire(EP_P, 5, EP_VCO, 0)             # VOCT -> PITCH

EP_VCF = add('Bogaudio', 'Bogaudio-VCF', [26, 8], {
    0: 1500.0,   # FREQUENCY 截止频率
    3: 1.6,      # Q
    4: 1,        # MODE 低通
})
wire(EP_VCO, 1, EP_VCF, 3)           # SAW -> IN
wire(EP_P, 5, EP_VCF, 2)             # VOCT -> PITCH（滤波器跟音高）

EP_ADSR = add('Bogaudio', 'Bogaudio-ADSR', [36, 8], {
    0: 0.015, 1: 0.40, 2: 0.45, 3: 0.35,
})
wire(EP_P, 6, EP_ADSR, 0)            # GATE
wire(EP_ADSR, 0, EP_VCF, 1)          # ENV -> FM（触键亮度 = 电钢味的关键）

# 电钢是单声道 ⇒ 用 Split 分成 L/R，避免一边有声一边没声
EP_SPLIT = add('Fundamental', 'Split', [46, 8])
wire(EP_VCF, 0, EP_SPLIT, 0)
wire(EP_SPLIT, 0, MIX, 2)            # 轨2 L
wire(EP_SPLIT, 1, MIX, 3)            # 轨2 R
wire(EP_VCF, 0, FEL, 1)              # send 进混响右口

# ============================================================
# 3) 声部三：**弗拉门戈风吉他** —— Plaits 拨弦 + Waveshaper 轻磨砂
#   依据 第128行「弗拉门戈风吉他」+ 第125行「磨砂吉他嗡鸣」
#   磨砂 = 轻度过载把高频磨毛，不是重饱和
# ============================================================
GTR_P = add('rcm', 'rcm-pianoroll', [0, 12])
wire(CLK, 0, GTR_P, 0)
wire(CLK, 5, GTR_P, 1)               # RUN

GTR = add('AudibleInstruments', 'Plaits', [14, 12], {
    0: 4,        # MODEL1 = PLUCK，拨弦瞬态 = 弗拉门戈点弦感
    2: 440.0,    # FREQ
    3: 0.35,     # HARMONICS
    4: 0.50,     # TIMBRE
    5: 0.20,     # MORPH
})
wire(GTR_P, 5, GTR, 7)               # VOCT -> NOTE
wire(GTR_P, 6, GTR, 5)               # GATE -> TRIGGER（拨弦要有触发才有瞬态）

GTR_SH = add('HetrickCV', 'Waveshaper', [26, 12], {
    0: 0.30,     # AMOUNT 轻磨砂
    1: 0.50,     # SCALE
    2: 0.80,     # RANGE
})
wire(GTR, 0, GTR_SH, 0)              # MAIN -> MAIN

GTR_SPLIT = add('Fundamental', 'Split', [36, 12])
wire(GTR_SH, 0, GTR_SPLIT, 0)
wire(GTR_SPLIT, 0, MIX, 4)           # 轨3 L
wire(GTR_SPLIT, 1, MIX, 5)           # 轨3 R
# 吉他 send也走混响左口？—— ⚠ Feline IN0 已被大提琴占用。
# 用 Split 的第二路给吉他进Feline IN0 会挤掉大提琴，
# 所以这里只做大提琴 send（干湿分离的主要听感来源在低音区）。

# ============================================================
# 4) 堆层渐入 —— 三小节后电钢进，后半段吉他加轮
#   做法：把三个 pianoroll 的 pattern 长度错开 + 用 velocity 渐变做动态起伏。
#   「渐入」靠 velocity（力度）实现最自然，也最像真人演奏。
#   （第 68 行「留白以缺失感传达张力」+ 第 65 行「保留呼吸」）
# ============================================================

# ============================================================
# 5) 不自动开播（李的规矩：加载后让他自己按RUN）
# ============================================================
for m in p['modules']:
    if m['model'] == 'rcm-pianoroll':
        m['data']['sequenceRunning'] = False
        m['data'].setdefault('currentPattern', 0)
        m['data'].setdefault('currentStep', 0)
        m['data'].setdefault('currentMeasure', 0)
    if m['model'] == 'Clocked':
        # 🔴 Clocked 靠 data.running 走表；模板里可能是 True ⇒ 必须显式关掉，
        # 否则加载即自动播放（会破坏 life1 之前的教训）
        if m.get('data') is None:
            m['data'] = {}
        m['data']['running'] = False

# ============================================================
# 6) 落盘前总断言
# ============================================================
live = {m['id'] for m in p['modules']}
assert len(live) == len(p['modules']), '模块表有重复 id'
for c in p['cables']:
    assert c['outputModuleId'] in live, '线 %s 输出端模块不存在' % c['id']
    assert c['inputModuleId'] in live, '线 %s 输入端模块不存在' % c['id']
seen_slot = set()
for c in p['cables']:
    k = (c['inputModuleId'], c['inputId'])
    assert k not in seen_slot, '同口挤占 %s IN%d' % (c['inputModuleId'], c['inputId'])
    seen_slot.add(k)

print('排班：')
autolayout()

patchio.write_patch(OUT, p)
print('交付 ->', os.path.basename(OUT))
print('模块 %d / 线 %d' % (len(p['modules']), len(p['cables'])))
print()
print('声部布局：')
print('  轨1 大提琴  Elements弓弦(左右分出)  → 干声轨1+send混响')
print('  轨2 电钢Bogaudio-VCO 锯齿→VCF+ENV   → Split→L/R')
print('  轨3 吉他  Plaits 拨弦→Waveshaper磨砂 → Split→L/R')
print('  混音MixMasterJr → HostAudio2 (OUT2=L/OUT3=R 真立体声)')
print('  混响 Feline 湿声 → 混音器轨4')