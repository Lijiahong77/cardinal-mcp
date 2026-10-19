# -*- coding: utf-8 -*-
"""
Charli XCX / A.G. Cook 风格「伴奏 + 手弹」机架 ×3
================================================
《360》/《party 4 u》/《What You Think About Me》

🔴 目标运行环境：D:\\Cardinal\\win64\\CardinalNative.exe（含 Starsea 自建包）
   —— 李实际使用的就是这个编译版，它带 Starsea-MiniArranger。

🔴 与旧版相比只保留三个真修复：
   1. 模块/线缆 id **必须是整数**（Rack 用 json_integer_value 读，字符串 → 0 → 全乱 → 空指针崩）
   2. data 只做**合并**，绝不整替换（否则冲掉 Clocked 的 panelTheme 等 10 个字段）
   3. 模板 data 为 null 时保持 null，不写 {}（Rack 对 null 会跳过 dataFromJson）
   顶层 version 用 '2.0.0'、cable 只留 5 个键 —— 与能正常打开的 yorushika_shura.vcv 逐字段一致。

--------------------------------------------------------------------------
调研结论（每条都有出处）
--------------------------------------------------------------------------
1. 三首歌全部由 A.G. Cook 制作（Shazam credits 逐首核对）。
2. 《Brat》硬规则：**禁用鼓采样、只用 Roland TR-909**（Coda Music 对 Jon Shave
   的采访 + Cook 的 Tape Notes 访谈）⇒ 用 `WSTD-Drums/BassDrum9`。
3. 客观音乐数据：
   | 曲目 | BPM | 调 | 和弦骨架 | 出处 |
   | 360 | 120 | C 小调 | Cm → D♭（i → ♭II） | Wikipedia（120 BPM, common time）+ GuitarTuna 和弦页 |
   | party 4 u | 79 | D♭ 大调 | G♭sus2 → A♭6 → B♭m → D♭（IV-V-vi-I） | Shazam 79 BPM + Hooktheory 写 IVsus2 V(add6) vi I |
   | What You Think About Me | 115 | D 大调 | G → A → F♯m → Bm（IV-V-iii-vi） | Shazam 115 BPM + SongData 标 D Major + GuitarTabsExplorer |
   ⚠️ 360 调性有冲突：Wikipedia 写 C major，但和弦页给 Cm/D♭/E♭/Fm。
      以和弦为准取 C 小调（半音上行 i→♭II 正是辨识点）。

--------------------------------------------------------------------------
「自动」和「手弹」为什么能同时
--------------------------------------------------------------------------
Rack 铁律：一个输入口只能接一根线。所以不能让音序器和键盘共用一个 VCO 的音高口。
本机架用三条互不冲突的并联路径：

  A. 鼓 —— WSTD 鼓模块有 **2 个独立声部**（源码 `ClosedHH.cpp: numModules = 2`，
     基类 `enum InputIds { GATE_INPUT=16, NUM_INPUTS=48 }`，声部 i 触发口 = IN(16+i)）。
     声部 0 接 MiniArranger，声部 1 接鼓垫，音频分别从 OUT0 / OUT1 出。真并联。
  B. 旋律 —— 自动 4 轨走 MiniArranger，手弹走独立的 `HostMIDI → lead voice`。
  C. 音量 —— MixMasterJr 每轨独立推子 + mute/solo。

--------------------------------------------------------------------------
⚠️ 加载后不会自己响（宪法：不许自动开播）—— 按 MiniArranger 的 RUN 键。
--------------------------------------------------------------------------
"""
import os
import sys
import copy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patchio

ROOT = 'D:/Cardinal'
OUTDIR = ROOT + '/patches'

# ---------------- 模板：每个模块都从「能打开的机架」克隆 ----------------
TMPL_MA = ROOT + '/patches/mini_arranger_expanded.vcv'
TMPL_SYN = ROOT + '/patches/quadeca_auto_life1.vcv'
TMPL_MIX = ROOT + '/patches/helm_before_full.vcv'

TPL = {
    ('ImpromptuModular', 'Clocked'):            ROOT + '/patches/demo_S1_8tracks.vcv',
    ('Starsea', 'Starsea-MiniArranger'):        TMPL_MA,
    ('Starsea', 'Starsea-MiniArrangerExpander'): TMPL_MA,
    ('WSTD-Drums', 'BassDrum9'):                ROOT + '/patches/Final Patch Work.vcv',
    ('WSTD-Drums', 'SnareDrumN'):               ROOT + '/patches/Final Patch Work.vcv',
    ('WSTD-Drums', 'ClosedHiHat'):              ROOT + '/patches/helm_drums.vcv',
    ('Bogaudio', 'Bogaudio-VCO'):               TMPL_SYN,
    ('Bogaudio', 'Bogaudio-VCF'):               ROOT + '/patches/quadeca_life1_wdtg.vcv',
    ('Bogaudio', 'Bogaudio-ADSR'):              TMPL_SYN,
    ('Fundamental', 'VCA-1'):                   ROOT + '/patches/demo_S1_8tracks.vcv',
    ('Fundamental', 'Mixer'):                   ROOT + '/patches/before_yorushika_1018.vcv',
    ('MindMeldModular', 'MixMasterJr'):         TMPL_MIX,
    ('Valley', 'Plateau'):                      TMPL_MIX,
    ('Cardinal', 'HostAudio2'):                 ROOT + '/patches/before_yorushika_1018.vcv',
    ('Cardinal', 'HostMIDI'):                   ROOT + '/patches/demo_S1_8tracks.vcv',
    ('Cardinal', 'HostMIDIGate'):               ROOT + '/patches/helm_full.vcv',
    ('Cardinal', 'HostMIDIMap'):                ROOT + '/patches/Final Patch Work.vcv',
    ('Cardinal', 'TextEditor'):                 ROOT + '/patches/demo_S1_8tracks.vcv',
}

# ---------------- 固定整数 id ----------------
MID = {
    'CLK':     8400000000000001,
    'MA':      8400000000000002,
    'EXP':     8400000000000003,
    'KICK':    8400000000000004,
    'SNARE':   8400000000000005,
    'HAT':     8400000000000006,
    'B_VCO':   8400000000000007,
    'B_VCF':   8400000000000008,
    'B_ADSR':  8400000000000009,
    'B_VCA':   8400000000000010,
    'C_VCO1':  8400000000000011,
    'C_VCO2':  8400000000000012,
    'C_VCO3':  8400000000000013,
    'C_MIX':   8400000000000014,
    'C_VCF':   8400000000000015,
    'C_ADSR':  8400000000000016,
    'C_VCA':   8400000000000017,
    'L_VCO':   8400000000000018,
    'L_VCF':   8400000000000019,
    'L_ADSR':  8400000000000020,
    'L_VCA':   8400000000000021,
    'DRUM_BUS': 8400000000000022,
    'MIX':     8400000000000023,
    'VERB':    8400000000000024,
    'HOST':    8400000000000025,
    'HMIDI':   8400000000000026,
    'HGATE':   8400000000000027,
    'HMAP':    8400000000000028,
    'TEXT':    8400000000000029,
}

_tpl_cache = {}


def tpl_of(plugin, model):
    key = (plugin, model)
    if key not in _tpl_cache:
        pp = patchio.read_patch(TPL[key])
        for m in pp['modules']:
            if m.get('plugin') == plugin and m.get('model') == model:
                _tpl_cache[key] = copy.deepcopy(m)
                break
        else:
            raise SystemExit('模板 %s 里找不到 %s/%s' % (TPL[key], plugin, model))
    return copy.deepcopy(_tpl_cache[key])


# ============================================================
# 音符数据结构（MiniArranger）
#   note = {step, length, pitch, velocity}；step 是跨小节绝对步号
#   stepsPerQuarter = 4 ⇒ 每小节 16 步
# ============================================================

def chords_to_tracks(chords, bars=8, spb=16):
    """和弦 -> 3 条轨道。

    🔴 源码 （= 1 小节），
       单个音符写 length=32 会被 clampValues() 静默钳到 16，音乐就不对了。
       ⇒ 每个和弦按小节拆成多个 length=16 的音符（顺带让 pad 每小节重新起音，更自然）。
    """
    out = [[], [], []]
    for i, (sb, triad) in enumerate(chords):
        eb = chords[i + 1][0] if i + 1 < len(chords) else bars
        for b in range(sb, eb):
            for k in range(3):
                out[k].append({'step': b * spb, 'length': spb,
                               'pitch': triad[k], 'velocity': 0.72})
    return out


def bass_eighths(roots, bars=8, spb=16):
    out = []
    for b in range(bars):
        r = roots[b]
        for k in range(8):
            pitch = r + 12 if k == 6 else r
            out.append({'step': b * spb + k * 2, 'length': 1, 'pitch': pitch,
                        'velocity': 0.92 if k % 2 == 0 else 0.62})
    return out


def bass_whole(roots2, bars=8, spb=16):
    """长音 bass —— 同样受 MA_MAX_LENGTH=16 限制，按小节拆成一段段 length=16。"""
    out = []
    for i, (sb, p) in enumerate(roots2):
        eb = roots2[i + 1][0] if i + 1 < len(roots2) else bars
        for b in range(sb, eb):
            out.append({'step': b * spb, 'length': spb,
                        'pitch': p, 'velocity': 0.88})
    return out


def drum_pattern(pat, bars=8, spb=16):
    out = []
    for b in range(bars):
        for s, v, p in pat:
            out.append({'step': b * spb + s, 'length': 1, 'pitch': p, 'velocity': v})
    return out


def riff_pattern(fig, bars=8, spb=16):
    out = []
    for b in range(bars):
        for s, p, ln in fig:
            out.append({'step': b * spb + s, 'length': ln, 'pitch': p, 'velocity': 0.8})
    return out


SONGS = [
    # 1) 360 — 120 BPM / C 小调 / i -> bII
    dict(
        fname='charli_360.vcv', title='360', bpm=120.0,
        key_note='C minor  |  Cm -> Db  (i -> bII)',
        chords=[(0, [60, 63, 67]), (2, [61, 65, 68]),
                (4, [60, 63, 67]), (6, [61, 65, 68])],
        bass=('eighths', {0: 36, 1: 36, 2: 37, 3: 37, 4: 36, 5: 36, 6: 37, 7: 37}),
        kick=[(0, 1.00, 36), (4, 0.95, 36), (8, 1.00, 36), (12, 0.95, 36)],
        snare=[(4, 0.90, 38), (12, 0.90, 38)],
        hat=[(i, 0.78 if i % 4 == 0 else 0.42, 42) for i in range(0, 16)],
        riff=[(0, 72, 1), (2, 72, 1), (4, 70, 2), (6, 67, 2),
              (8, 72, 1), (10, 72, 1), (12, 70, 2), (14, 67, 2)],
        voice=dict(
            bass_vcf=900.0, bass_q=1.3, bass_env=(0.005, 0.18, 0.65, 0.12),
            chord_vcf=2400.0, chord_q=1.0, chord_env=(0.012, 0.45, 0.85, 0.55),
            lead_vcf=3200.0, lead_q=1.4, lead_env=(0.010, 0.30, 0.50, 0.25),
        ),
        verb=dict(wet=0.12, size=0.45, diff=7.0, decay=0.50),
        mix_levels=dict(bass=0.95, chord=0.72, lead=0.80,
                        kick=0.95, snare=0.80, hat=0.52, manual=0.80),
    ),
    # 2) party 4 u — 79 BPM / Db 大调 / IV-V-vi-I
    dict(
        fname='charli_party4u.vcv', title='party 4 u', bpm=79.0,
        key_note='Db major  |  Gbsus2 -> Ab6 -> Bbm -> Db  (IV-V-vi-I)',
        chords=[(0, [54, 56, 61]), (2, [56, 60, 65]),
                (4, [58, 61, 65]), (6, [61, 65, 68])],
        bass=('whole', [(0, 42), (2, 44), (4, 46), (6, 37)]),
        kick=[(0, 0.88, 36), (10, 0.78, 36)],
        snare=[(8, 0.85, 38)],
        hat=[(0, 0.66, 42), (2, 0.38, 42), (4, 0.46, 42), (6, 0.38, 42),
             (8, 0.66, 42), (10, 0.38, 42), (12, 0.46, 42), (14, 0.38, 42)],
        riff=[(0, 73, 2), (2, 68, 2), (4, 73, 2), (6, 80, 2),
              (8, 75, 2), (10, 70, 2), (12, 75, 2), (14, 82, 2)],
        voice=dict(
            bass_vcf=550.0, bass_q=0.9, bass_env=(0.030, 0.60, 0.75, 0.50),
            chord_vcf=1500.0, chord_q=0.8, chord_env=(0.280, 0.70, 0.90, 1.30),
            lead_vcf=2100.0, lead_q=1.0, lead_env=(0.090, 0.50, 0.75, 0.90),
        ),
        verb=dict(wet=0.38, size=0.62, diff=9.0, decay=0.72),
        mix_levels=dict(bass=0.90, chord=0.80, lead=0.72,
                        kick=0.85, snare=0.70, hat=0.40, manual=0.75),
    ),
    # 3) What You Think About Me — 115 BPM / D 大调 / IV-V-iii-vi
    dict(
        fname='charli_wytam.vcv', title='What You Think About Me', bpm=115.0,
        key_note='D major  |  G -> A -> F#m -> Bm  (IV-V-iii-vi)',
        chords=[(0, [55, 59, 62]), (2, [57, 61, 64]),
                (4, [54, 57, 61]), (6, [59, 62, 66])],
        bass=('eighths', {0: 43, 1: 43, 2: 45, 3: 45, 4: 42, 5: 42, 6: 47, 7: 47}),
        kick=[(0, 1.00, 36), (8, 0.95, 36)],
        snare=[(4, 0.92, 38), (12, 0.92, 38)],
        hat=[(0, 0.60, 42), (2, 0.72, 42), (4, 0.60, 42), (6, 0.72, 42),
             (8, 0.60, 42), (10, 0.72, 42), (12, 0.60, 42), (14, 0.72, 42)],
        riff=[(0, 67, 3), (4, 71, 3), (8, 66, 3), (12, 71, 3)],
        voice=dict(
            bass_vcf=1200.0, bass_q=2.0, bass_env=(0.002, 0.14, 0.55, 0.10),
            chord_vcf=2900.0, chord_q=1.5, chord_env=(0.004, 0.28, 0.70, 0.30),
            lead_vcf=4200.0, lead_q=2.6, lead_env=(0.004, 0.22, 0.45, 0.20),
        ),
        verb=dict(wet=0.13, size=0.42, diff=6.0, decay=0.46),
        mix_levels=dict(bass=0.92, chord=0.70, lead=0.82,
                        kick=0.95, snare=0.82, hat=0.46, manual=0.80),
    ),
]


# ============================================================
# 构建
# ============================================================

class Builder:
    def __init__(self, song):
        self.song = song
        self.p = {'version': '2.0.0', 'zoom': 0.9,
                  'modules': [], 'cables': [], 'gridOffset': [0, 0]}
        self.by_id = {}

    def add(self, key, plugin, model, params=None, data_patch=None):
        m = tpl_of(plugin, model)
        m['id'] = MID[key]
        m['pos'] = [0, 0]
        m['leftModuleId'] = None
        m['rightModuleId'] = None
        assert isinstance(m.get('version'), str), '%s 的 version 不是字符串' % model
        if params:
            for pid, val in params.items():
                if pid >= len(m['params']):
                    raise SystemExit('%s 只有 %d 个 param，写不到 param%d'
                                     % (model, len(m['params']), pid))
                m['params'][pid]['value'] = float(val)
        if data_patch:
            if m.get('data') is None:
                m['data'] = dict(data_patch)
            else:
                m['data'].update(data_patch)
        # 🔴 TextEditor 的 dataFromJson 第一段是 Rack Core Notes 兼容分支：
        #    只要存在 "text" 键，就 text = json_string_value(textJ) 然后 return，
        #    而 json_string_value() 对「对象/数字」返回 nullptr -> std::string(nullptr) -> 崩。
        #    模板 demo_S1_8tracks.vcv 里带着 {"text": {...}} 这个残留，必须清掉。
        if isinstance(m.get('data'), dict):
            m['data'].pop('text', None)
        # data 一律 dict（能正常打开的 yorushika 里 VCA-1/鼓都是 {}，不是 null）
        if m.get('data') is None:
            m['data'] = {}
        self.p['modules'].append(m)
        self.by_id[key] = m
        return MID[key]

    def wire(self, src_key, so, dst_key, di):
        used = {(c['inputModuleId'], c['inputId']) for c in self.p['cables']}
        if (MID[dst_key], di) in used:
            raise SystemExit('同口挤占：%s 的 IN%d 已有一根线' % (dst_key, di))
        self.p['cables'].append({
            'id': len(self.p['cables']) + 1,
            'outputModuleId': MID[src_key], 'outputId': so,
            'inputModuleId': MID[dst_key], 'inputId': di,
        })

    def layout(self):
        import layout_patch as LP
        lay = LP.pick_layout(os.path.basename(self.out_path))
        pos, _declared, unreg, log = LP.do_layout(self.p, lay)
        if unreg:
            raise SystemExit('未登记的模块：\n  '
                             + '\n  '.join('%s/%s id=%s' % (m.get('plugin'),
                                                            m.get('model'), m['id'])
                                           for m in unreg))
        for mid, xy in pos.items():
            for m in self.p['modules']:
                if str(m['id']) == str(mid):
                    m['pos'] = list(xy)
                    break

    def verify(self):
        errs = []
        ids = [m['id'] for m in self.p['modules']]
        if len(ids) != len(set(ids)):
            errs.append('模块 id 重复')
        if not all(isinstance(i, int) for i in ids):
            errs.append('模块 id 必须全为整数')
        known = set(ids)
        for c in self.p['cables']:
            if c['outputModuleId'] not in known:
                errs.append('线缆输出指向不存在的模块 %s' % c['outputModuleId'])
            if c['inputModuleId'] not in known:
                errs.append('线缆输入指向不存在的模块 %s' % c['inputModuleId'])
        used = set()
        for c in self.p['cables']:
            k = (c['inputModuleId'], c['inputId'])
            if k in used:
                errs.append('输入口双接 %s' % (k,))
            used.add(k)
        for m in self.p['modules']:
            if not isinstance(m.get('version'), str):
                errs.append('%s version 非字符串' % m.get('model'))
            if 'data' not in m:
                errs.append('%s 缺 data 键' % m.get('model'))
            if m.get('leftModuleId') is not None or m.get('rightModuleId') is not None:
                errs.append('%s 有悬空 moduleId 指针' % m.get('model'))
        # Expander 必须紧贴 MiniArranger 右侧
        ma = next(m for m in self.p['modules'] if m['model'] == 'Starsea-MiniArranger')
        ex = next(m for m in self.p['modules'] if m['model'] == 'Starsea-MiniArrangerExpander')
        if ma['pos'][1] != ex['pos'][1]:
            errs.append('MiniArranger 与 Expander 不在同一行')
        gap = ex['pos'][0] - ma['pos'][0]
        if gap != 42:
            errs.append('Expander 与 MiniArranger 间距 = %s 格，应为 42（40+2）' % gap)
        if errs:
            raise SystemExit('自查失败：\n  ' + '\n  '.join(errs))
        return len(self.p['modules']), len(self.p['cables'])


def build(song):
    b = Builder(song)
    b.out_path = OUTDIR + '/' + song['fname']
    v = song['voice']
    lv = song['mix_levels']

    chord_t = chords_to_tracks(song['chords'])
    if song['bass'][0] == 'eighths':
        bass_notes = bass_eighths(song['bass'][1])
    else:
        bass_notes = bass_whole(song['bass'][1])
    kick_notes = drum_pattern(song['kick'])
    snare_notes = drum_pattern(song['snare'])
    hat_notes = drum_pattern(song['hat'])
    riff_notes = riff_pattern(song['riff'])

    def mk_track(label, notes):
        return {'label': label, 'mute': False, 'measures': 8, 'notes': notes}

    # ---------------- 1. 主时钟 ----------------
    b.add('CLK', 'ImpromptuModular', 'Clocked',
          params={0: song['bpm'], 1: 5.0},
          data_patch={'running': False})

    # ---------------- 2. 编排核心 ----------------
    b.add('MA', 'Starsea', 'Starsea-MiniArranger',
          params={11: 0.0, 12: 0.0},
          data_patch={
              'running': False, 'currentStep': 0,
              'arranger': {
                  'editTrack': 0, 'stepsPerQuarter': 4.0,
                  'tracks': [
                      mk_track('BASS', bass_notes),
                      mk_track('CHD-LO', chord_t[0]),
                      mk_track('CHD-MID', chord_t[1]),
                      mk_track('CHD-HI', chord_t[2]),
                  ]}})
    b.add('EXP', 'Starsea', 'Starsea-MiniArrangerExpander',
          data_patch={
              'arranger': {
                  'editTrack': 0, 'stepsPerQuarter': 4.0,
                  'tracks': [
                      mk_track('KICK', kick_notes),
                      mk_track('SNARE', snare_notes),
                      mk_track('HAT', hat_notes),
                      mk_track('RIFF', riff_notes),
                  ]}})
    b.wire('CLK', 1, 'MA', 0)          # 16 分时钟

    # ---------------- 3. 鼓 ----------------
    b.add('KICK', 'WSTD-Drums', 'BassDrum9')
    b.add('SNARE', 'WSTD-Drums', 'SnareDrumN')
    b.add('HAT', 'WSTD-Drums', 'ClosedHiHat')
    b.wire('EXP', 1, 'KICK', 16)       # E1 gate -> 声部0
    b.wire('EXP', 4, 'SNARE', 16)
    b.wire('EXP', 7, 'HAT', 16)

    # ---------------- 4. 手弹 ----------------
    b.add('HMIDI', 'Cardinal', 'HostMIDI',
          data_patch={'pwRange': 2.0, 'smooth': True, 'channels': 8,
                      'polyMode': 1, 'lastPitch': 0.0, 'lastMod': 0.0,
                      'inputChannel': 0, 'outputChannel': 0})
    b.add('HGATE', 'Cardinal', 'HostMIDIGate',
          data_patch={'notes': [48, 49, 50] + [-1] * 15,
                      'velocity': False, 'mpeMode': False,
                      'inputChannel': 0, 'outputChannel': 0})
    b.wire('HGATE', 0, 'KICK', 17)
    b.wire('HGATE', 1, 'SNARE', 17)
    b.wire('HGATE', 2, 'HAT', 17)

    # ---------------- 5. 贝斯 ----------------
    b.add('B_VCO', 'Bogaudio', 'Bogaudio-VCO', params={3: 0.50})
    b.wire('MA', 5, 'B_VCO', 0)
    b.add('B_VCF', 'Bogaudio', 'Bogaudio-VCF',
          params={0: v['bass_vcf'], 3: v['bass_q'], 4: 1.0})
    b.wire('B_VCO', 1, 'B_VCF', 3)
    b.add('B_ADSR', 'Bogaudio', 'Bogaudio-ADSR',
          params={0: v['bass_env'][0], 1: v['bass_env'][1],
                  2: v['bass_env'][2], 3: v['bass_env'][3], 4: 0.0})
    b.wire('MA', 6, 'B_ADSR', 0)
    b.wire('B_ADSR', 0, 'B_VCF', 1)
    b.add('B_VCA', 'Fundamental', 'VCA-1', params={0: lv['bass'], 1: lv['bass']})
    b.wire('B_VCF', 0, 'B_VCA', 1)
    b.wire('B_ADSR', 0, 'B_VCA', 0)

    # ---------------- 6. 和弦 ----------------
    for i, key in enumerate(['C_VCO1', 'C_VCO2', 'C_VCO3']):
        b.add(key, 'Bogaudio', 'Bogaudio-VCO', params={3: 0.55})
        b.wire('MA', 8 + i * 3, key, 0)   # OUT8/11/14
    b.add('C_MIX', 'Fundamental', 'Mixer', params={0: 0.85})
    for i, key in enumerate(['C_VCO1', 'C_VCO2', 'C_VCO3']):
        b.wire(key, 1, 'C_MIX', i)
    b.add('C_VCF', 'Bogaudio', 'Bogaudio-VCF',
          params={0: v['chord_vcf'], 3: v['chord_q'], 4: 1.0})
    b.wire('C_MIX', 0, 'C_VCF', 3)
    b.add('C_ADSR', 'Bogaudio', 'Bogaudio-ADSR',
          params={0: v['chord_env'][0], 1: v['chord_env'][1],
                  2: v['chord_env'][2], 3: v['chord_env'][3], 4: 0.0})
    b.wire('MA', 9, 'C_ADSR', 0)      # T2 gate
    b.wire('C_ADSR', 0, 'C_VCF', 1)
    b.add('C_VCA', 'Fundamental', 'VCA-1', params={0: lv['chord'], 1: lv['chord']})
    b.wire('C_VCF', 0, 'C_VCA', 1)
    b.wire('C_ADSR', 0, 'C_VCA', 0)

    # ---------------- 7. 手弹 lead ----------------
    b.add('L_VCO', 'Bogaudio', 'Bogaudio-VCO', params={3: 0.50})
    b.wire('HMIDI', 0, 'L_VCO', 0)
    b.add('L_VCF', 'Bogaudio', 'Bogaudio-VCF',
          params={0: v['lead_vcf'], 3: v['lead_q'], 4: 1.0})
    b.wire('L_VCO', 1, 'L_VCF', 3)
    b.add('L_ADSR', 'Bogaudio', 'Bogaudio-ADSR',
          params={0: v['lead_env'][0], 1: v['lead_env'][1],
                  2: v['lead_env'][2], 3: v['lead_env'][3], 4: 0.0})
    b.wire('HMIDI', 1, 'L_ADSR', 0)
    b.wire('L_ADSR', 0, 'L_VCF', 1)
    b.add('L_VCA', 'Fundamental', 'VCA-1', params={0: lv['lead'], 1: lv['lead']})
    b.wire('L_VCF', 0, 'L_VCA', 1)
    b.wire('L_ADSR', 0, 'L_VCA', 0)

    # ---------------- 8. 手弹鼓总线 ----------------
    b.add('DRUM_BUS', 'Fundamental', 'Mixer', params={0: 0.9})
    b.wire('KICK', 1, 'DRUM_BUS', 0)
    b.wire('SNARE', 1, 'DRUM_BUS', 1)
    b.wire('HAT', 1, 'DRUM_BUS', 2)

    # ---------------- 9. 混音 + 混响 + 输出 ----------------
    b.add('MIX', 'MindMeldModular', 'MixMasterJr', params={
        0: lv['bass'], 1: lv['chord'], 2: lv['lead'], 3: lv['kick'],
        4: lv['snare'], 5: lv['hat'], 6: lv['manual'],
    })

    def to_track(src, so, track):
        b.wire(src, so, 'MIX', track * 2)
        b.wire(src, so, 'MIX', track * 2 + 1)

    to_track('B_VCA', 0, 0)
    to_track('C_VCA', 0, 1)
    to_track('L_VCA', 0, 2)
    to_track('KICK', 0, 3)
    to_track('SNARE', 0, 4)
    to_track('HAT', 0, 5)
    to_track('DRUM_BUS', 0, 6)

    b.add('VERB', 'Valley', 'Plateau',
          params={0: 1.0, 1: song['verb']['wet'], 2: 0.02,
                  5: song['verb']['size'], 6: song['verb']['diff'],
                  7: song['verb']['decay']})
    b.wire('MIX', 2, 'VERB', 0)
    b.wire('MIX', 3, 'VERB', 1)
    b.add('HOST', 'Cardinal', 'HostAudio2', params={0: 0.79})
    b.wire('VERB', 0, 'HOST', 0)
    b.wire('VERB', 1, 'HOST', 1)

    # ---------------- 10. 8 个旋钮 ----------------
    maps = [
        {'cc': 20, 'moduleId': int(MID['C_VCF']),  'paramId': 0},
        {'cc': 21, 'moduleId': int(MID['C_VCF']),  'paramId': 2},
        {'cc': 22, 'moduleId': int(MID['C_ADSR']), 'paramId': 3},
        {'cc': 23, 'moduleId': int(MID['B_VCF']),  'paramId': 0},
        {'cc': 24, 'moduleId': int(MID['B_ADSR']), 'paramId': 1},
        {'cc': 25, 'moduleId': int(MID['VERB']),   'paramId': 1},
        {'cc': 26, 'moduleId': int(MID['L_VCF']),  'paramId': 0},
        {'cc': 27, 'moduleId': int(MID['L_ADSR']), 'paramId': 3},
    ]
    b.add('HMAP', 'Cardinal', 'HostMIDIMap',
          data_patch={'maps': maps, 'smooth': True, 'channel': 0})

    # ---------------- 11. 面板说明 ----------------
    etext = (
        "CHARLI XCX - {title}\n"
        "{note}\n"
        "BPM {bpm}  |  A.G. Cook style\n"
        "================================\n"
        "START: press RUN on MiniArranger\n"
        "(green lamp). It is silent\n"
        "until you do -- by design.\n"
        "\n"
        "[AUTO] 8 tracks\n"
        " T1 BASS   T2/3/4 CHORDS\n"
        " E1 KICK   E2 SNARE   E3 HAT\n"
        " E4 RIFF\n"
        "\n"
        "[HAND PLAY] works at the same\n"
        "time as AUTO. Nothing unplugs.\n"
        " KEYS  -> lead voice\n"
        " PADS  1 kick 2 snare 3 hat\n"
        "        (added on top of auto)\n"
        " KNOBS 1 chord bright\n"
        "       2 chord reso\n"
        "       3 chord tail\n"
        "       4 bass bright\n"
        "       5 bass decay\n"
        "       6 reverb wet\n"
        "       7 lead bright\n"
        "       8 lead tail\n"
        "\n"
        "[MIX] 8 tracks, own fader\n"
        " T1 bass T2 chord T3 lead\n"
        " T4-6 drums T7 your drums\n"
        "\n"
        "! Do NOT press KNOB-B.\n"
        "  Layer 2 sends pitch-bend\n"
        "  and cannot be mapped.\n"
    ).format(title=song['title'], note=song['key_note'], bpm=int(song['bpm']))
    b.add('TEXT', 'Cardinal', 'TextEditor',
          data_patch={'filepath': '', 'lang': 'None',
                      'etext': etext, 'width': 26})

    b.layout()
    n_mod, n_cab = b.verify()
    patchio.write_patch(b.out_path, b.p)
    print('  -> %-24s %2d modules / %2d cables' % (song['fname'], n_mod, n_cab))
    return b.out_path


if __name__ == '__main__':
    print('== Charli XCX trio (D-drive build, Starsea available) ==')
    for s in SONGS:
        build(s)
    print('done')
