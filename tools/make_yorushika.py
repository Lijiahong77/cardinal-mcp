# -*- coding: utf-8 -*-
"""
Yorushika 风格「键盘即兴 + 自动伴奏」机架生成器（2026-10-18）

设计来源（全部有据）：
  调研：专辑《二人称》(2026-03-04, 22 曲, 书信体小说联动)
        代表曲《修羅》(C大调/100BPM/4/4/97小节, 日剧主题曲, 宫泽贤治《春と修司》)
              《花も騒めく》(E♭大调/4/4, 原声梦幻中速 ~78BPM【BPM待核实】)
        和声习惯实证：vi-IV-I-V 循环(《花に亡霊》《夜行》)、小室进行变体、
                      七和弦色彩、半音转调
  设备：李的 M-VAVE SMK25（见 docs/SMK25-midi-map.md）
        琴键 ch1 复音 → MiniArranger 分轨录制
        旋钮 CC20-27 → HostMIDIMap（channel=0 OMNI, smooth）
        鼓垫 Note48-55 → HostMIDIGate（velocity=false 满幅门）
        Transport PLAY/STOP/REC = Note94/93/95 → MiniArranger RUN/RESET/RECORD
        触控条 = 弯音(ch9) + CC1(弹回式, 只映射"归零=自然"的参数)
  编排核心：李昨天验收的 Starsea-MiniArranger —— 键盘弹和弦,
        复音按声道分轨录制(MA_REC_CHAN=4), 4 轨 x 4 小节循环,
        每轨输出 VOCT/GATE/VELOCITY 给独立合成链。
        李弹什么和弦, 伴奏就织什么体 —— 不是 pianoroll 写死循环。

🔴 2026-10-18 选型重做（李反馈：Plateau 界面不直观 + 鼓组音色要重新想）：
  混响 Plateau → SurgeXTFXReverb2：李自己的 Final Patch Work.vcv 就在用
    Surge XT 系（4 个 Reverb2），旋钮带名称+数值、有预设选择器，比 Plateau 直观。
    参数序（源码 Reverb2Effect.cpp）：p0 Pre-Delay / p1 Room Size / p2 Decay /
    p3 Diffusion / p4 Buildup / p5 Modulation / p6 HF Damp / p7 LF Damp /
    p8 Width / p9 Mix。
  鼓组 BassDrum9(TR909 电子底鼓)/DMX(Oberheim 电子鼓机) → CR78：修羅鼓谱实证
    是原声鼓组（Bass Drum/Acoustic Snare/Toms/Crash/Ride），Cardinal 全库无
    原声鼓采样包（29 个 drum 命中已盘点），WSTD 内 CR78 = Roland CompuRhythm
    1978 模拟电路鼓，温暖圆润，是库里最贴原声底鼓方向的型号（DrumKit README
    实证硬件原型）。CR78 双声部：声部1=自动底鼓(param0=0 采样01, 文件大小/
    CR-78 面板首位推断为底鼓), 声部2=鼓垫拉丁打击(param1=3, 李 helm_drums.vcv
    验证过 03 号采样)。军鼓/闭镲/开镲/通鼓保留。

两个 patch（李拍板 A 方案）：
  yorushika_shura.vcv  100 BPM 摇滚驱动 (修羅)
  yorushika_hana.vcv    78 BPM 梦幻原声 (花も騒めく)

★ 端口全部查过源码/验收实证, 禁止凭印象改。
★ 模块一律 deepcopy 自能打开的机架, plugin slug 从模板反推。
★ 🔴 同一个输入口只能接一根线 —— wire() 带断言。
★ 🔴 Expander 必须紧贴 MiniArranger 右侧 (Rack rightExpander 只认物理紧邻)。
★ 🔴 加载后不自动开播: Clocked/MiniArranger 的 data.running 全 False。
"""
import sys, copy, os, json
sys.path.insert(0, os.path.dirname(__file__))
import patchio

ROOT = 'D:/Cardinal'
TMPL_MA   = ROOT + '/patches/mini_arranger_expanded.vcv'   # MiniArranger + Expander + Clocked + HostMIDI + TextEditor
TMPL_HELM = ROOT + '/patches/helm_full.vcv'                # HostMIDIGate + HostMIDIMap + HostAudio2
TMPL_CR78 = ROOT + '/patches/helm_drums.vcv'               # CR78（李验证过的用法：param1=3 采样03）
TMPL_REV  = ROOT + '/patches/Final Patch Work.vcv'         # SurgeXTFXReverb2（李自己在用的 Surge XT 系）
TMPL_SEQ  = os.path.expandvars(r'%TEMP%\Cardinal.0003\patch.json')  # Sequencer(151 params) + 鼓组模板
TPL = {
    ('ImpromptuModular', 'Clocked'):     TMPL_MA,
    ('Cardinal', 'HostMIDI'):            TMPL_MA,
    ('Cardinal', 'HostMIDIGate'):        TMPL_HELM,
    ('Cardinal', 'HostMIDIMap'):         TMPL_HELM,
    ('Cardinal', 'HostAudio2'):          TMPL_HELM,
    ('Cardinal', 'TextEditor'):          TMPL_MA,
    ('Starsea', 'Starsea-MiniArranger'):         TMPL_MA,
    ('Starsea', 'Starsea-MiniArrangerExpander'): TMPL_MA,
    ('WSTD-Drums', 'Sequencer'):   TMPL_SEQ,
    ('WSTD-Drums', 'CR78'):        TMPL_CR78,
    ('WSTD-Drums', 'SnareDrumN'):  TMPL_SEQ,
    ('WSTD-Drums', 'ClosedHiHat'): TMPL_SEQ,
    ('WSTD-Drums', 'OpenHiHat'):   TMPL_SEQ,
    ('WSTD-Drums', 'Tomi'):        TMPL_SEQ,
    ('Bogaudio', 'Bogaudio-VCO'):  ROOT + '/refs/examples/nooneknowspeter_-_Catalyst.vcv',
    ('Bogaudio', 'Bogaudio-VCF'):  ROOT + '/refs/examples/DRMR_-_BassGrowl.vcv',
    ('Bogaudio', 'Bogaudio-ADSR'): ROOT + '/refs/examples/DRMR_-_BassGrowl.vcv',
    ('Fundamental', 'VCA-1'):       TMPL_HELM,
    ('Fundamental', 'Sum'):         TMPL_HELM,
    ('Fundamental', 'Mixer'):       TMPL_HELM,
    ('AudibleInstruments', 'Plaits'): ROOT + '/refs/examples/falkTX_-_Divide-no-Conquer.vcv',
    ('MindMeldModular', 'MixMasterJr'): TMPL_HELM,
    ('SurgeXTRack', 'SurgeXTFXReverb2'): TMPL_REV,
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

# ============================================================
# 两种风格配方（差异全部集中在这里）
# ============================================================
MODES = {
    # 《修羅》C 大调 100 BPM：riff 驱动 + 8-beat 摇滚鼓 + 亮 pad
    'shura': dict(
        bpm=100.0,
        kick=[0, 4, 8, 12], snare=[4, 12], hat=list(range(0, 16, 2)),
        pad_vcf_f=1200.0, pad_vcf_q=1.2,        # 电吉力和弦感：亮 + 带共振
        pluck_h=0.40, pluck_t=0.55,             # 琶音更亮更攻击
        rev_room=0.50, rev_decay=0.45, rev_mix=1.0,   # 短混响，干脆
        lead_shape=0.45,
    ),
    # 《花も騒めく》E♭ 大调 ~78 BPM【BPM待核实】：原声琶音 + 轻鼓 + 长混响
    'hana': dict(
        bpm=78.0,
        kick=[0, 8], snare=[4, 12], hat=[0, 4, 8, 12],
        pad_vcf_f=800.0, pad_vcf_q=0.6,         # 更柔更暗
        pluck_h=0.25, pluck_t=0.45,
        rev_room=0.65, rev_decay=0.65, rev_mix=1.0,   # 长混响，梦幻
        lead_shape=0.40,
    ),
}

def build(mode):
    cfg = MODES[mode]
    p = {'version': '2.0.0', 'zoom': 0.7, 'modules': [], 'cables': [], 'gridOffset': [0, 0]}

    _nid = [7200000000000000]
    def nid():
        _nid[0] += 1
        return _nid[0]

    def add(plugin, model, params=None, data=None):
        m = tpl_of(plugin, model)
        m['id'] = nid()
        m['pos'] = [0, 0]
        m['leftModuleId'] = None
        m['rightModuleId'] = None
        assert isinstance(m.get('version'), str), '%s version 非字符串' % model
        if m.get('data') is None:
            m['data'] = {}
        if params:
            for pid, val in params.items():
                assert pid < len(m['params']), '%s 没有 param%d(共%d)' % (model, pid, len(m['params']))
                m['params'][pid]['value'] = float(val)
        if data:
            m['data'].update(data)
        p['modules'].append(m)
        return m['id']

    def wire(src, so, dst, di):
        for c in p['cables']:
            assert not (c['inputModuleId'] == dst and c['inputId'] == di), \
                '同口挤占：模块 %s 的 IN%d 接了两根线' % (dst, di)
        p['cables'].append({'id': nid(), 'outputModuleId': src, 'outputId': so,
                            'inputModuleId': dst, 'inputId': di})

    # ============================================================
    # 行 0：时钟 + MIDI 入口 + 编排核心
    # ============================================================
    # Clocked：param0=绝对 BPM；param1=5（Clk1 ratio=×4 ⇒ OUT1=16分音符, §11.6 实证）
    CLK = add('ImpromptuModular', 'Clocked', {0: cfg['bpm'], 1: 5.0},
              {'running': False})

    # HostMIDI：OMNI 收全部通道(琴键ch1/旋钮ch1+ch10/鼓垫ch2-8,10/触控条ch9)；
    #   channels=8 复音 ⇒ MiniArranger 按声道分轨录和弦（李弹4音=4轨各一音）
    HMI = add('Cardinal', 'HostMIDI', {},
              {'pwRange': 2.0, 'smooth': False, 'forceGateGaps': False,
               'channels': 8, 'polyMode': 0, 'lastPitch': 8192, 'lastMod': 0,
               'inputChannel': 0, 'outputChannel': 0})

    # HostMIDIMap：占位先建（maps 等模块 id 齐了再写）
    MAP = add('Cardinal', 'HostMIDIMap', {},
              {'maps': [], 'smooth': True, 'channel': 0})

    # HostMIDIGate：鼓垫 48-55(前3个用) + Transport 94/93/95
    #   velocity=false ⇒ 满幅 10V 门（鼓阈值 0.5V, 轻敲不漏）
    GATE = add('Cardinal', 'HostMIDIGate', {},
               {'notes': [48, 49, 50, 51, 52, 53, 54, 55, 94, 93, 95,
                          -1, -1, -1, -1, -1, -1, -1],
                'velocity': False, 'mpeMode': False,
                'inputChannel': 0, 'outputChannel': 0})

    # MiniArranger：4 轨 x 4 小节空循环。TRACK_EDIT=0(轨1)。RUN/REC 靠面板按钮
    #   或键盘 Transport（OUT8/9/10）。加载后 running=False —— 李自己按 RUN。
    MA = add('Starsea', 'Starsea-MiniArranger',
             {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0},
             {'running': False, 'currentStep': 0,
              'arranger': {'editTrack': 0, 'stepsPerQuarter': 4.0,
                           'tracks': [
                               {'label': 'Track 1', 'mute': False, 'measures': 4, 'notes': []},
                               {'label': 'Track 2', 'mute': False, 'measures': 4, 'notes': []},
                               {'label': 'Track 3', 'mute': False, 'measures': 4, 'notes': []},
                               {'label': 'Track 4', 'mute': False, 'measures': 4, 'notes': []}]}})

    # Expander：必须紧贴 MiniArranger 右侧（layout 表保证物理相邻）
    EXP = add('Starsea', 'Starsea-MiniArrangerExpander', {},
              {'arranger': {'editTrack': 0, 'stepsPerQuarter': 4.0,
                            'tracks': [
                                {'label': 'E1', 'mute': False, 'measures': 4, 'notes': []},
                                {'label': 'E2', 'mute': False, 'measures': 4, 'notes': []},
                                {'label': 'E3', 'mute': False, 'measures': 4, 'notes': []},
                                {'label': 'E4', 'mute': False, 'measures': 4, 'notes': []}]}})

    # Sequencer：鼓型步进器。running=True 无所谓 —— 总闸是 Clocked
    #   （Clocked 不跑就没时钟, 鼓不响; 李按 Clocked RUN 才走）
    tracks = [[[False] * 8 for _ in range(16)] for _ in range(17)]
    for st in cfg['kick']:
        tracks[1][st][0] = True
    for st in cfg['snare']:
        tracks[1][st][1] = True
    for st in cfg['hat']:
        tracks[1][st][2] = True
    SEQ = add('WSTD-Drums', 'Sequencer', {},
              {'running': True, 'cycling': True, 'currentPlay': 0,
               'tracks': tracks, 'programs': [1, 0, 0, 0, 0, 0, 0, 0]})

    TXT = add('Cardinal', 'TextEditor', {},
              {'filepath': '', 'lang': 'None', 'etext': ETEXT, 'width': 26})

    # ============================================================
    # 行 1：声音链
    # ============================================================
    # --- 手弹直通层：温暖电钢（复音 8 声道 → Sum 折单声道, LEVEL 0.5 留 headroom）
    EP_VCO = add('Bogaudio', 'Bogaudio-VCO', {0: 261.63, 2: 0.50, 3: 0.55})
    EP_VCF = add('Bogaudio', 'Bogaudio-VCF', {0: 1500.0, 3: 1.6, 4: 1})
    EP_AD  = add('Bogaudio', 'Bogaudio-ADSR', {0: 0.015, 1: 0.40, 2: 0.45, 3: 0.35})
    EP_VCA = add('Fundamental', 'VCA-1')
    EP_SUM = add('Fundamental', 'Sum', {0: 0.5})

    # --- MiniArranger 轨1 → 贝斯（sine, 低八度）
    BS_VCO = add('Bogaudio', 'Bogaudio-VCO', {0: 65.41, 3: 0.30})
    BS_AD  = add('Bogaudio', 'Bogaudio-ADSR', {0: 0.005, 1: 0.20, 2: 0.70, 3: 0.15})
    BS_VCA = add('Fundamental', 'VCA-1')
    BS_SUM = add('Fundamental', 'Sum')

    # --- MiniArranger 轨2 → pad（saw + VCF, 软包络）
    PD_VCO = add('Bogaudio', 'Bogaudio-VCO', {0: 130.81, 2: 0.50, 3: 0.50})
    PD_VCF = add('Bogaudio', 'Bogaudio-VCF', {0: cfg['pad_vcf_f'], 3: cfg['pad_vcf_q'], 4: 1})
    PD_AD  = add('Bogaudio', 'Bogaudio-ADSR', {0: 0.08, 1: 0.30, 2: 0.60, 3: 0.50})
    PD_VCA = add('Fundamental', 'VCA-1')
    PD_SUM = add('Fundamental', 'Sum')

    # --- MiniArranger 轨3 → 琶音（Plaits PLUCK, 拨弦瞬态）
    AR_PL  = add('AudibleInstruments', 'Plaits',
                 {0: 4, 2: 440.0, 3: cfg['pluck_h'], 4: 0.50, 5: cfg['pluck_t']})
    AR_AD  = add('Bogaudio', 'Bogaudio-ADSR', {0: 0.005, 1: 0.25, 2: 0.0, 3: 0.20})
    AR_VCA = add('Fundamental', 'VCA-1')
    AR_SUM = add('Fundamental', 'Sum')

    # --- MiniArranger 轨4 → 旋律（triangle, 亮而柔）
    LD_VCO = add('Bogaudio', 'Bogaudio-VCO', {0: 261.63, 3: cfg['lead_shape']})
    LD_AD  = add('Bogaudio', 'Bogaudio-ADSR', {0: 0.01, 1: 0.30, 2: 0.40, 3: 0.30})
    LD_VCA = add('Fundamental', 'VCA-1')
    LD_SUM = add('Fundamental', 'Sum')

    # --- 鼓：CR78 双声部（声部1=自动层底鼓, 声部2=鼓垫拉丁打击）+ 军鼓/闭镲/开镲/通鼓
    #   CR78 = Roland CompuRhythm 1978 模拟电路鼓，温暖圆润，最贴修羅原声鼓组方向
    #   param0=0: 声部1 采样01（大小/CR-78 面板首位推断为底鼓；不对就拧 SELECT）
    #   param1=3: 声部2 采样03（李 helm_drums.vcv 验证过、听过的）
    #   param16/17=1.0: 两声部播放速度正常
    BD = add('WSTD-Drums', 'CR78', {0: 0.0, 1: 3.0, 16: 1.0, 17: 1.0})
    SD = add('WSTD-Drums', 'SnareDrumN')
    CH = add('WSTD-Drums', 'ClosedHiHat')
    OH = add('WSTD-Drums', 'OpenHiHat')
    TM = add('WSTD-Drums', 'Tomi')
    DR_MIX = add('Fundamental', 'Mixer', {0: 0.9})
    DR_SUM = add('Fundamental', 'Sum')

    # --- send 汇总：电钢/pad/琶音三路先过一个 Mixer 并流
    #   （🔴 一个输入口只能接一根线，李 10-17 实测后接挤掉先接）
    SND = add('Fundamental', 'Mixer', {0: 0.8})

    # --- 混响（SurgeXTFXReverb2, 李自己在用的 Surge XT 系, 界面直观）
    #   参数序（源码 Reverb2Effect.cpp）：0 PreDelay 1 RoomSize 2 Decay 3 Diffusion
    #   4 Buildup 5 Modulation 6 HFDamp 7 LFDamp 8 Width 9 Mix
    #   send 模式：Mix=1.0 全湿（干声已从各轨直进 MIX）
    REV = add('SurgeXTRack', 'SurgeXTFXReverb2',
              {0: 0.10, 1: cfg['rev_room'], 2: cfg['rev_decay'], 3: 0.70, 4: 0.0,
               5: 0.30, 6: 0.50, 7: 0.30, 8: 1.0, 9: cfg['rev_mix']})

    # --- 主混音台（8 轨）+ 输出
    MIX = add('MindMeldModular', 'MixMasterJr',
              {0: 1.0, 1: 0.9, 2: 0.75, 3: 0.7, 4: 0.8, 5: 0.85, 6: 0.9})
    HOST = add('Cardinal', 'HostAudio2')

    # ============================================================
    # 接线
    # ============================================================
    # --- 时钟（一个输出口出多根线到不同输入口是合法的）
    wire(CLK, 1, MA, 0)      # 16分时钟 → MiniArranger
    wire(CLK, 1, SEQ, 0)     # 16分时钟 → Sequencer（16步=1小节）

    # --- 键盘 → MiniArranger（复音按声道分轨录和弦）
    wire(HMI, 0, MA, 4)      # VOCT
    wire(HMI, 1, MA, 5)      # GATE
    wire(HMI, 2, MA, 7)      # VELOCITY

    # --- 键盘 Transport → MiniArranger 走带（边沿翻转, 源码 SchmittTrigger）
    wire(GATE, 8, MA, 2)     # PLAY(94)  → RUN
    wire(GATE, 9, MA, 1)     # STOP(93)  → RESET
    wire(GATE, 10, MA, 3)    # REC(95)   → RECORD

    # --- 键盘 → 电钢直通层（复音链）
    wire(HMI, 0, EP_VCO, 0)  # VOCT(复音电缆)
    wire(HMI, 1, EP_AD, 0)   # GATE
    wire(EP_VCO, 1, EP_VCF, 3)   # SAW → 音频入
    wire(EP_AD, 0, EP_VCA, 0)    # ENV → VCA CV
    wire(EP_AD, 0, EP_VCF, 1)    # ENV → VCF FM（触键亮度=电钢味）
    wire(EP_VCF, 0, EP_VCA, 1)   # VCF → VCA 音频
    wire(EP_VCA, 0, EP_SUM, 0)   # 复音 → 单声道
    wire(EP_SUM, 0, MIX, 0)      # 轨0 L
    wire(EP_SUM, 0, MIX, 1)      # 轨0 R
    wire(EP_SUM, 0, SND, 0)      # send 进混响汇总

    # --- MiniArranger 轨1 → 贝斯
    wire(MA, 5, BS_VCO, 0)
    wire(MA, 6, BS_AD, 0)
    wire(BS_VCO, 3, BS_VCA, 1)   # SINE
    wire(BS_AD, 0, BS_VCA, 0)
    wire(BS_VCA, 0, BS_SUM, 0)
    wire(BS_SUM, 0, MIX, 2)
    wire(BS_SUM, 0, MIX, 3)

    # --- MiniArranger 轨2 → pad
    wire(MA, 8, PD_VCO, 0)
    wire(MA, 9, PD_AD, 0)
    wire(PD_VCO, 1, PD_VCF, 3)   # SAW
    wire(PD_AD, 0, PD_VCA, 0)
    wire(PD_AD, 0, PD_VCF, 1)
    wire(PD_VCF, 0, PD_VCA, 1)
    wire(PD_VCA, 0, PD_SUM, 0)
    wire(PD_SUM, 0, MIX, 4)
    wire(PD_SUM, 0, MIX, 5)
    wire(PD_SUM, 0, SND, 1)      # send

    # --- MiniArranger 轨3 → 琶音
    wire(MA, 11, AR_PL, 7)       # VOCT → NOTE
    wire(MA, 12, AR_PL, 5)       # GATE → TRIGGER（拨弦瞬态）
    wire(MA, 12, AR_AD, 0)       # GATE → ADSR
    wire(AR_PL, 0, AR_VCA, 1)    # MAIN
    wire(AR_AD, 0, AR_VCA, 0)
    wire(AR_VCA, 0, AR_SUM, 0)
    wire(AR_SUM, 0, MIX, 6)
    wire(AR_SUM, 0, MIX, 7)
    wire(AR_SUM, 0, SND, 2)      # send

    # --- MiniArranger 轨4 → 旋律
    wire(MA, 14, LD_VCO, 0)
    wire(MA, 15, LD_AD, 0)
    wire(LD_VCO, 2, LD_VCA, 1)   # TRIANGLE
    wire(LD_AD, 0, LD_VCA, 0)
    wire(LD_VCA, 0, LD_SUM, 0)
    wire(LD_SUM, 0, MIX, 8)
    wire(LD_SUM, 0, MIX, 9)

    # --- 鼓：Sequencer 自动层 → CR78声部1(底鼓)/军鼓/闭镲; 鼓垫手动层 → CR78声部2/通鼓/开镲
    wire(SEQ, 0, BD, 16)     # 轨0 kick   → CR78 声部1
    wire(SEQ, 1, SD, 16)     # 轨1 snare  → 军鼓
    wire(SEQ, 2, CH, 16)     # 轨2 hat    → 闭镲
    wire(GATE, 0, BD, 17)    # 垫1 → CR78 声部2（拉丁打击, 李验证过的 03 采样）
    wire(GATE, 1, TM, 16)    # 垫2 → 通鼓
    wire(GATE, 2, OH, 16)    # 垫3 → 开镲
    for drum, iin in ((BD, 0), (SD, 1), (CH, 2), (BD, 3), (OH, 4), (TM, 5)):
        # ⚠️ CR78 两个输出口：OUT0=声部1(底鼓) OUT1=声部2(拉丁打击)
        out_id = 1 if (drum is BD and iin == 3) else 0
        wire(drum, out_id, DR_MIX, iin)
    wire(DR_MIX, 0, DR_SUM, 0)
    wire(DR_SUM, 0, MIX, 10)
    wire(DR_SUM, 0, MIX, 11)

    # --- 混响湿声回混音台轨6, 主输出真立体声
    #   Surge FX 单边接的镜像行为未实证 ⇒ L/R 两口都送（一出口两入口合法）
    wire(SND, 0, REV, 0)
    wire(SND, 0, REV, 1)
    wire(REV, 0, MIX, 12)
    wire(REV, 1, MIX, 13)
    wire(MIX, 2, HOST, 0)        # 主输出 L
    wire(MIX, 3, HOST, 1)        # 主输出 R

    # ============================================================
    # HostMIDIMap：8 旋钮 + 触控条（弹回式只映射"归零=自然态"参数）
    # ============================================================
    maps = [
        {'cc': 20, 'moduleId': EP_VCF, 'paramId': 0},   # 旋钮1 电钢明暗 (Cutoff Hz)
        {'cc': 21, 'moduleId': REV,    'paramId': 2},   # 旋钮2 混响尾巴 (Reverb2 Decay)
        {'cc': 22, 'moduleId': MIX,    'paramId': 5},   # 旋钮3 鼓音量
        {'cc': 23, 'moduleId': MIX,    'paramId': 1},   # 旋钮4 贝斯音量
        {'cc': 24, 'moduleId': MIX,    'paramId': 2},   # 旋钮5 pad 音量
        {'cc': 25, 'moduleId': MIX,    'paramId': 3},   # 旋钮6 琶音音量
        {'cc': 26, 'moduleId': CLK,    'paramId': 0},   # 旋钮7 现场速度 (BPM)
        {'cc': 27, 'moduleId': EP_AD,  'paramId': 3},   # 旋钮8 电钢余音 (Release)
        {'cc': 1,  'moduleId': REV,    'paramId': 5},   # 触控条上下 混响运动
        #   （CC1 弹回式: Reverb2 Modulation 归零=混响静止=自然态, 松手不破坏声音）
    ]
    for m in p['modules']:
        if m['id'] == MAP:
            m['data']['maps'] = maps

    # ============================================================
    # 落盘前总断言
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
    # Expander 紧贴 MiniArranger（layout 后校验物理相邻）
    def autolayout():
        import layout_patch as LP
        out = ROOT + '/patches/yorushika_%s.vcv' % mode
        lay = LP.pick_layout(os.path.basename(out))
        pos, _d, unreg, log = LP.do_layout(p, lay)
        if unreg:
            raise SystemExit('这些模块没登记进 YORUSHIKA_LAYOUT：\n  '
                             + '\n  '.join('%s/%s id=%s' % (m.get('plugin'), m.get('model'), m['id'])
                                           for m in unreg))
        by = {str(m['id']): m for m in p['modules']}
        for mid, xy in pos.items():
            by[str(mid)]['pos'] = list(xy)
        for line in log:
            print('  [layout] ' + line.strip())
        # 相邻校验：MiniArranger 与 Expander 的 x 必须首尾相接（同行）
        ma = next(m for m in p['modules'] if m['model'] == 'Starsea-MiniArranger')
        ex = next(m for m in p['modules'] if m['model'] == 'Starsea-MiniArrangerExpander')
        assert ma['pos'][1] == ex['pos'][1], 'MiniArranger 与 Expander 不同行!'
        assert ex['pos'][0] > ma['pos'][0], 'Expander 不在 MiniArranger 右侧!'
        gap = ex['pos'][0] - ma['pos'][0]
        # 列间距 = 宽度(40) + GAP(2) = 42; 中间没有插别的模块 = 物理紧邻
        assert gap == 42, 'Expander 与 MiniArranger 之间有间隙 (%s 格, 应为 42=40+2)' % gap

    print('排班：')
    autolayout()

    out = ROOT + '/patches/yorushika_%s.vcv' % mode
    patchio.write_patch(out, p)
    print('交付 ->', os.path.basename(out))
    print('模块 %d / 线 %d' % (len(p['modules']), len(p['cables'])))
    print('  BPM=%.0f  kick=%s  snare=%s  hat=%s' % (cfg['bpm'], cfg['kick'], cfg['snare'], cfg['hat']))
    return out

ETEXT = """YORUSHIKA LIVE RIG
==================
FLOW:
1 RUN on Clocked (far left, row0)
  -> style drum pattern starts
2 REC on MiniArranger (or REC key)
  -> play 4 bars of chords on keys
  -> T1 low=bass T2=pad T3=arp T4=lead
     (each key of a chord goes to its
      own track - play 2-4 notes)
  -> press REC again to stop
3 RUN on MiniArranger (or PLAY key)
  -> your loop plays; solo over it
  on the electric-piano voice

LIVE CONTROLS:
KNOB1 keys brightness
KNOB2 reverb tail
KNOB3 drums  KNOB4 bass
KNOB5 pad    KNOB6 arp
KNOB7 tempo  KNOB8 key release
TOUCHSTRIP up/down = reverb motion
TOUCHSTRIP left/right = pitch bend
PADS 1/2/3 = CR78 latin perc / tom /
  open hat (live fills over the loop)

! Do NOT press KNOB-B or PAD-B
  (they switch to layer 2 which
   Cardinal cannot map)
! SC/CH on keyboard: one key =
  full chord, spread across tracks
! Knobs need Cardinal MIDI input
  set to SMK25
! Kick voice is CR78 sample 01.
  If it sounds wrong, turn the
  SELECT knob on CR78 (1-6).
"""

if __name__ == '__main__':
    modes = sys.argv[1:] or ['shura', 'hana']
    for md in modes:
        if md not in MODES:
            raise SystemExit('unknown mode: %s (have %s)' % (md, list(MODES)))
        print('===== %s =====' % md)
        build(md)
        print()
