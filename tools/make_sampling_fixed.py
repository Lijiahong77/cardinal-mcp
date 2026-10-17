# -*- coding: utf-8 -*-
"""重做采样演示机架 S4 / S5 —— 修三处「静态全绿但加载即崩 / 加载后永哑」。

★ 为什么重做而不是打补丁：根因在**生成器**（D:/Cardinal/tmp/fix_patches.py），
  改产物下次重跑又坏。这里把正确写法固化成新生成器。

── 本次修的三处（10-17 17:40 复查定位）────────────────────────────
① **悬空 leftModuleId / rightModuleId**（加载即崩的真元凶）
   生成器用 `copy.deepcopy(_tpl[...])` 从模板克隆模块，模板里残留的
   面包屑指针被一起带了过来，指向源机架里已不存在的模块 ⇒ 加载即崩。
   S4 有 6 处悬空、S5 有 12 处。
   ✅ 修法：sanitize() 批量删除这两个字段（判据 = 悬空数必须为 0）。

② **samplerx8 的 MUTE = 0.0 ⇒ 永哑**（本项目最坑，10-17 16:25 李手点才发现）
   源码 SamplerX8.hpp:132 `if (params[MUTE_BUTTONS+i].getValue() == true)`
   —— **1.0 才发声**，语义与「静音」直觉相反。MUTE 在 param id **16-23**。
   旧生成器 `params[16+i] = mute`，默认值 0.0 ⇒ 八个槽全哑。
   ✅ 修法：默认 MUTE = 1.0。

③ **samplerx8 的 param 个数不齐**
   4 槽的模块只写了 12 个 param（VOL/PAN/MUTE 各 4），8 槽的写 24 个。
   同型号模块 param 结构不一致，容易触发反序列化意外。
   ✅ 修法：一律写满 24 个（VOL 0-7 / PAN 8-15 / MUTE 16-23），
             没装素材的槽位 MUTE 写 0.0（不发声，符合预期）。

★ 保持不变（已核实是对的，别动）：
   - Clocked param0 = 120.0（绝对 BPM，不是归一化值）、20 个 param、
     data={"running": true}（True = 正在放，standalone 里自走）
   - version 一律字符串（顶层 '2.4.1'，模块照抄各自模板）
   - data 一律 dict（不能留 None）
"""
import copy
import os
import sys

sys.path.insert(0, r'D:\Cardinal\tools')
import patchio
from audit_ports import LIMITS

BASE = r'D:\Cardinal\patches\mini_arranger_expanded.vcv'
EXTRA = [r'D:\Cardinal\refs\examples\SpotlightKid_-_Classic-Polysynth.vcv',
         r'D:\Cardinal\patches\Final Patch Work.vcv']
S = r'D:\Cardinal\samples'
V = __import__('datetime').datetime.now().strftime('%H%M')

# ---- 模板：只能从「能正常加载」的机架取，字段类型天然正确 ----
_tpl = {}
for _f in [BASE] + EXTRA:
    try:
        _p = patchio.read_patch(_f)
    except Exception:
        continue
    for _m in _p.get('modules', _p):
        _tpl.setdefault(_m['model'], _m)
PVER = patchio.read_patch(BASE)['version']          # '2.4.1'


def sanitize(m):
    """★ 清掉面包屑指针 —— 悬空即加载即崩。返回清除的数量。"""
    n = 0
    for k in ('leftModuleId', 'rightModuleId'):
        if k in m:
            del m[k]
            n += 1
    return n


def prow(pairs):
    return [{'value': float(v), 'id': int(k)} for k, v in sorted(pairs.items())]


def clone(model, new_id, x, y, params=None):
    m = copy.deepcopy(_tpl[model])
    sanitize(m)
    m['id'] = new_id
    m['pos'] = [x, y]
    if params is not None:
        m['params'] = params
    if m.get('data') is None:
        m['data'] = {}
    return m


# ---- Clocked：param0 = 绝对 BPM，20 个 param，running = True ----
def clock(new_id=1, x=0, y=0):
    ps = copy.deepcopy(_tpl['Clocked']['params'])
    for p in ps:
        if p.get('id') == 0:
            p['value'] = 120.0
    m = clone('Clocked', new_id, x, y, ps)
    m['data'] = {'running': True}
    return m


def samplerx8(new_id, x, y, kit):
    """voxglitch/samplerx8 —— 一律写满 24 个 param。
       VOL 0-7 / PAN 8-15 / MUTE 16-23（MUTE 1.0 = 发声，反直觉但源码如此）。
       空槽 MUTE=0.0 / VOL=0 / PAN=0.5（居中）。"""
    data = {}
    params = {}
    for i in range(8):
        params[0 + i] = 0.0            # VOL
        params[8 + i] = 0.5            # PAN 居中
        params[16 + i] = 0.0           # MUTE 空槽不发声
    for i, (fn, vol, pan) in enumerate(kit):
        data['loaded_sample_path_%d' % (i + 1)] = '%s\\%s' % (S, fn)
        params[0 + i] = vol
        params[8 + i] = pan
        params[16 + i] = 1.0           # ★ 1.0 才发声
    return {
        'id': new_id, 'plugin': 'voxglitch', 'model': 'samplerx8',
        'version': '2.0', 'pos': [x, y],
        'params': prow(params), 'data': data,
    }


def audio_out(new_id, x, y):
    return clone('HostAudio2', new_id, x, y)


def vcf(new_id, x, y, cutoff=0.42, res=0.35):
    return clone('VCF', new_id, x, y, prow({0: cutoff, 1: 0.0, 2: res,
                                            3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0}))


def mixer(new_id, x, y, level=0.78):
    return clone('Mixer', new_id, x, y, prow({0: level}))


def text_editor(new_id, x, y, body):
    m = clone('TextEditor', new_id, x, y)
    m['data'] = {'filepath': '', 'lang': 'None', 'etext': body}
    return m


# ============================================================ 审计
def key_of(m):
    pl = m['plugin'] if isinstance(m['plugin'], str) else m['plugin'].get('slug')
    return '%s/%s' % (pl, m['model'])


def audit(mods, cables, name):
    errs = []
    ids = {m['id'] for m in mods}
    byid = {m['id']: key_of(m) for m in mods}

    # ① 悬空指针必须为 0
    for m in mods:
        for k in ('leftModuleId', 'rightModuleId'):
            if k in m:
                errs.append('%s 仍带 %s' % (byid[m['id']], k))

    # ② samplerx8 必须写满 24 param，且装了素材的槽 MUTE=1.0
    for m in mods:
        if m['model'] != 'samplerx8':
            continue
        pv = {p['id']: p['value'] for p in m['params']}
        if len(m['params']) != 24:
            errs.append('samplerx8 id=%s 只有 %d 个 param，应 24' % (m['id'], len(m['params'])))
        slots = [k for k in m['data'] if k.startswith('loaded_sample_path_')]
        for k in slots:
            i = int(k.rsplit('_', 1)[1]) - 1
            if pv.get(16 + i) != 1.0:
                errs.append('samplerx8 槽 %d MUTE=%s，应 1.0 才发声' % (i + 1, pv.get(16 + i)))

    # ③ 逐线端口上限
    for c in cables:
        om, im, oi, ii = c['outputModuleId'], c['inputModuleId'], c['outputId'], c['inputId']
        if om not in ids:
            errs.append('输出模块不存在 %s' % om)
        if im not in ids:
            errs.append('输入模块不存在 %s' % im)
        if om in ids and byid[om] in LIMITS:
            hi = LIMITS[byid[om]][1]
            if hi is not None and oi > hi:
                errs.append('%s OUT%d 越界(上限%d)' % (byid[om], oi, hi))
        if im in ids and byid[im] in LIMITS:
            lo = LIMITS[byid[im]][0]
            if lo is not None and ii > lo:
                errs.append('%s IN%d 越界(上限%d)' % (byid[im], ii, lo))

    # ④ version 必须是字符串、data 必须是 dict
    for m in mods:
        if not isinstance(m.get('version'), str):
            errs.append('%s version 不是字符串' % byid[m['id']])
        if not isinstance(m.get('data'), dict):
            errs.append('%s data 不是 dict' % byid[m['id']])

    # ⑤ 摆放：同行不得重叠
    rows = {}
    for m in mods:
        rows.setdefault(m['pos'][1], []).append((m['pos'][0], m['model']))
    for y, lst in rows.items():
        lst.sort()
        for a, b in zip(lst, lst[1:]):
            if b[0] <= a[0]:
                errs.append('第 %d 行重叠 %s(x=%d)/%s(x=%d)' % (y, a[1], a[0], b[1], b[0]))

    assert not errs, '%s 审计失败:\n  ' % name + '\n  '.join(errs)
    print('  [%s] 五项审计全过' % name)


def build(mods, cables, path, name):
    patch = {'version': PVER, 'modules': mods, 'cables': cables,
             'gridOffset': [-2.4444010257720947, -0.49984580278396606],
             'zoom': 0.75, 'path': path}
    audit(mods, cables, name)
    patchio.write_patch(path, patch, as_archive=True)
    back = patchio.read_patch(path)
    assert len(back['modules']) == len(mods) and len(back['cables']) == len(cables)
    # 回读再核一次悬空
    bids = {m['id'] for m in back['modules']}
    d2 = [(m['id'], k) for m in back['modules'] for k in ('leftModuleId', 'rightModuleId')
          if m.get(k) is not None and m[k] not in bids]
    assert not d2, '回读发现悬空指针 %s' % d2
    n_mute = sum(1 for m in back['modules'] if m['model'] == 'samplerx8'
                 for p in m['params'] if 16 <= p['id'] <= 23 and p['value'] == 1.0)
    print('  写出 %-42s 模块%2d 线%2d  发声槽 %d' % (
        os.path.basename(path), len(back['modules']), len(back['cables']), n_mute))


# ============================================================ 音色表
KIT_A = [('kick.wav', 0.95, 0.50), ('snare.wav', 0.70, 0.52),
         ('hihat_closed.wav', 0.50, 0.63), ('clap.wav', 0.44, 0.37),
         ('bass_A1.wav', 0.78, 0.47), ('pluck_C4.wav', 0.58, 0.57),
         ('stab_Am.wav', 0.40, 0.50), ('tom_low.wav', 0.46, 0.44)]
KIT_B = [('bass_A1.wav', 0.78, 0.47), ('pluck_C4.wav', 0.58, 0.57),
         ('pluck_E4.wav', 0.50, 0.61), ('pluck_A3.wav', 0.52, 0.55)]
KIT_C = [('stab_Am.wav', 0.40, 0.50), ('stab_F.wav', 0.34, 0.50),
         ('tom_low.wav', 0.46, 0.44), ('hihat_open.wav', 0.34, 0.66)]

TEXT_S4 = (
    'SAMPLING DEMO  (8 slots, all loaded and armed)\n'
    '=================================================\n'
    '\n'
    'CLOCKED     the metronome. 120 BPM, running.\n'
    '            four outputs drive the first four slots.\n'
    'SAMPLERX8   8 sample slots, all files loaded:\n'
    '              1 kick      2 snare     3 closed hat  4 clap\n'
    '              5 bass A1   6 pluck C4  7 stab Am     8 low tom\n'
    '            each slot has volume / pan / MUTE knobs.\n'
    '            ★ MUTE reads backwards: 1 = playing, 0 = off.\n'
    'VCF         low-pass - takes the edge off so they sit together.\n'
    'MIXER       sums everything to stereo.\n'
    'HOSTAUDIO2  the speakers.\n'
    '\n'
    'TRY THIS\n'
    '  1. Turn VCF CUTOFF up   -> brighter, more raw samples\n'
    '  2. Turn slot 3 (hihat) volume up -> hats get louder\n'
    '  3. Click a MUTE knob - it toggles between 1 and 0\n'
    '  4. Play your keyboard on slots 5-8 - they have no clock,\n'
    '     so they are free for you to trigger by hand.\n'
    '\n'
    'All 14 wav files in D:\\Cardinal\\samples\\ are synthetic -\n'
    'generated with numpy. No third-party material.\n'
)

TEXT_S5 = (
    'SAMPLING FULL KIT  (all 12 slots wired, 120 BPM, running)\n'
    '=========================================================\n'
    '\n'
    'ROW 0  THE DRUM KIT\n'
    '  Clocked + samplerx8 A (kick/snare/hat/clap)\n'
    '  -> Mixer -> VCF (cutoff 0.40)  drum bus, filtered harder\n'
    '\n'
    'ROW 1  THE MUSIC\n'
    '  samplerx8 B (bass/pluck C/pluck E/pluck A)\n'
    '  samplerx8 C (stab Am/stab F/low tom/open hat)\n'
    '  -> Mixer -> VCF (cutoff 0.55)  brighter, keeps definition\n'
    '  -> ADSR -> VCA   gentle ducking, the mix breathes\n'
    '\n'
    'MIXING NOTES\n'
    '  Only the kick sits at 0.95. Everything else is below 0.8\n'
    '  so nothing clips when the layers stack.\n'
    '  Open hat is hard right (0.66), clap hard left (0.37),\n'
    '  bass stays centre. Stereo is a job split, not a 50/50.\n'
    '\n'
    '★ samplerx8 MUTE reads backwards (1 = playing). Every wired\n'
    '  slot is set to 1. Empty slots are 0.\n'
    '\n'
    'UNUSED (swap in any time): tom_high.wav, rim.wav, bass_F1.wav\n'
)

# ---------------------------------------------------------------- S4
print('S4 教学版 —— 悬空指针归零 / MUTE=1.0 / 参数写满')
s4 = [clock(1, 0, 0),
      samplerx8(2, 10, 0, KIT_A),
      mixer(3, 30, 0, 0.82),
      vcf(4, 38, 0, 0.42, 0.35),
      audio_out(5, 50, 0),
      text_editor(6, 0, 2, TEXT_S4)]
c4 = [
    {'id': 1, 'outputModuleId': 1, 'outputId': 0, 'inputModuleId': 2, 'inputId': 0, 'color': '#52ff7d'},
    {'id': 2, 'outputModuleId': 1, 'outputId': 2, 'inputModuleId': 2, 'inputId': 1, 'color': '#527dff'},
    {'id': 3, 'outputModuleId': 1, 'outputId': 1, 'inputModuleId': 2, 'inputId': 2, 'color': '#ff5252'},
    {'id': 4, 'outputModuleId': 1, 'outputId': 3, 'inputModuleId': 2, 'inputId': 3, 'color': '#7d52ff'},
    {'id': 5, 'outputModuleId': 2, 'outputId': 16, 'inputModuleId': 3, 'inputId': 0, 'color': '#ffb252'},
    {'id': 6, 'outputModuleId': 2, 'outputId': 17, 'inputModuleId': 3, 'inputId': 1, 'color': '#52ffff'},
    {'id': 7, 'outputModuleId': 3, 'outputId': 0, 'inputModuleId': 4, 'inputId': 3, 'color': '#7d52ff'},
    {'id': 8, 'outputModuleId': 4, 'outputId': 0, 'inputModuleId': 5, 'inputId': 0, 'color': '#ff52b2'},
]
p4 = r'D:\Cardinal\patches\demo_S4_sampling__v%s.vcv' % V
build(s4, c4, p4, 'S4')

# ---------------------------------------------------------------- S5
print('S5 大阵仗版 —— 同上')
s5 = [clock(1, 0, 0),
      samplerx8(2, 10, 0, KIT_A),
      mixer(3, 30, 0, 0.82),
      vcf(4, 38, 0, 0.40, 0.30),
      samplerx8(5, 10, 1, KIT_B),
      samplerx8(6, 10, 2, KIT_C),
      mixer(7, 30, 1, 0.76),
      vcf(8, 38, 1, 0.55, 0.22),
      clone('ADSR', 9, 46, 1, prow({0: 0.02, 1: 0.35, 2: 0.55, 3: 0.30,
                                    4: 0.0, 5: 0.0, 6: 0.0, 7: 0.0, 8: 0.0})),
      clone('VCA-1', 10, 52, 1, prow({0: 1.0, 1: 1.0})),
      mixer(11, 58, 1, 0.80),
      audio_out(12, 66, 1),
      text_editor(13, 0, 3, TEXT_S5)]
c5 = [
    {'id': 1, 'outputModuleId': 1, 'outputId': 0, 'inputModuleId': 2, 'inputId': 0, 'color': '#52ff7d'},
    {'id': 2, 'outputModuleId': 1, 'outputId': 2, 'inputModuleId': 2, 'inputId': 1, 'color': '#527dff'},
    {'id': 3, 'outputModuleId': 1, 'outputId': 1, 'inputModuleId': 2, 'inputId': 2, 'color': '#ff5252'},
    {'id': 4, 'outputModuleId': 1, 'outputId': 3, 'inputModuleId': 2, 'inputId': 3, 'color': '#7d52ff'},
    {'id': 5, 'outputModuleId': 1, 'outputId': 1, 'inputModuleId': 5, 'inputId': 0, 'color': '#52ffd0'},
    {'id': 6, 'outputModuleId': 1, 'outputId': 2, 'inputModuleId': 5, 'inputId': 1, 'color': '#d052ff'},
    {'id': 7, 'outputModuleId': 1, 'outputId': 0, 'inputModuleId': 6, 'inputId': 0, 'color': '#ffb252'},
    {'id': 8, 'outputModuleId': 2, 'outputId': 16, 'inputModuleId': 3, 'inputId': 0, 'color': '#ffb252'},
    {'id': 9, 'outputModuleId': 2, 'outputId': 17, 'inputModuleId': 3, 'inputId': 1, 'color': '#52ffff'},
    {'id': 10, 'outputModuleId': 3, 'outputId': 0, 'inputModuleId': 4, 'inputId': 3, 'color': '#7d52ff'},
    {'id': 11, 'outputModuleId': 4, 'outputId': 0, 'inputModuleId': 7, 'inputId': 0, 'color': '#ff52b2'},
    {'id': 12, 'outputModuleId': 5, 'outputId': 16, 'inputModuleId': 7, 'inputId': 1, 'color': '#52b2ff'},
    {'id': 13, 'outputModuleId': 5, 'outputId': 17, 'inputModuleId': 7, 'inputId': 2, 'color': '#ff7d52'},
    {'id': 14, 'outputModuleId': 6, 'outputId': 16, 'inputModuleId': 7, 'inputId': 3, 'color': '#7dff52'},
    {'id': 15, 'outputModuleId': 6, 'outputId': 17, 'inputModuleId': 7, 'inputId': 4, 'color': '#ffd052'},
    {'id': 16, 'outputModuleId': 7, 'outputId': 0, 'inputModuleId': 8, 'inputId': 3, 'color': '#7d52ff'},
    {'id': 17, 'outputModuleId': 8, 'outputId': 0, 'inputModuleId': 11, 'inputId': 0, 'color': '#ff52b2'},
    {'id': 18, 'outputModuleId': 11, 'outputId': 0, 'inputModuleId': 10, 'inputId': 1, 'color': '#52ffd0'},
    {'id': 19, 'outputModuleId': 9, 'outputId': 0, 'inputModuleId': 10, 'inputId': 0, 'color': '#b2ff52'},
    {'id': 20, 'outputModuleId': 10, 'outputId': 0, 'inputModuleId': 12, 'inputId': 0, 'color': '#52ff7d'},
]
p5 = r'D:\Cardinal\patches\demo_S5_fullkit__v%s.vcv' % V
build(s5, c5, p5, 'S5')

print()
print('本轮修掉：')
print('  1. 悬空 left/rightModuleId —— S4 6 处 / S5 12 处全部清零（加载即崩的真元凶）')
print('  2. samplerx8 MUTE 0.0 -> 1.0 —— 之前 8+4+4 个槽全哑，永远不出声')
print('  3. samplerx8 参数一律写满 24 个（VOL 0-7 / PAN 8-15 / MUTE 16-23）')
print('新文件名带版本号后缀，旧文件原样保留。')
