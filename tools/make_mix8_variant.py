# -*- coding: utf-8 -*-
"""把 S4 / S5 里的 Fundamental/Mixer 换成 BogaudioModules/Bogaudio-Mix8。

★ 为什么换（李 17:48 原话：「你现在这个样子，我都没法自由控制音量」）
  `Fundamental/Mixer` 只有 param0 = 总音量一个旋钮，**每路通道没有推子**。
  `Bogaudio-Mix8` 每路都有：LEVEL 推子 / PAN 声像 / MUTE(带 Solo) 按钮，
  外加 Master level / mute / dim —— 这才是能混音的混音器。

★ 全部规格**源码核实**（不靠记忆，不靠猜）────────────────────
  plugins/BogaudioModules/src/Mix8.hpp
  · NUM_PARAMS = 27；每路三连 param：LEVEL=3i / MUTE=3i+1 / PAN=3i+2（i=0..7）
    末尾 MIX_PARAM=24, MIX_MUTE_PARAM=25, MIX_DIM_PARAM=26
  · ⚠️ **输入不是连续的 IN0-7**，每路三连：
    CV=3i / PAN=3i+1 / IN=3i+2（i=0..7），末尾 MIX_CV_INPUT=24
    ⇒ 通道1 音频 = **IN2**、通道2 = **IN5**、通道3 = **IN8** ……
  · 输出：OUT0 = Left，OUT1 = Right（**立体声**）
  · LEVEL 量纲：`configParam(LEVEL, 0.0, 1.0, levelDefault)`，显示 dB。
    dB 范围 = MixerChannel::minDecibels(-60) ~ maxDecibels(+6)（mixer.cpp:4-5）
    ⇒ levelDefault = |−60|/(6−(−60)) = 0.9090909…
    写入用**归一化值**：想给 0dB 就写 0.9090909（因为 0dB 在 -60~+6 里的归一位置）。
  · PAN 归一化 -1..1，默认 0（居中）；MUTE 是 configSwitch 0..3
    {Unmuted=0, Muted=1, Soloed=2} ★ **0 才是开**，写 1 会静音！
  · `data` 有键 `poly_channel_offset`（整数），保守写 -1（单声道取电压和）。

★ 立体声带来的接线变化（这是换机架最容易漏的一处）
  原 `Mixer` 单声道 OUT0 → 现在 MIX8 的 **OUT0(L) 和 OUT1(R) 都要接**，
  否则只有左耳响。HostAudio2 正好有 2 个输入（IN0=左 IN1=右，HostAudio.cpp:47），
  直接对上，比原来多一根线。

★ 只换 Mixer：位置、其余模块、接线去向、音量策略全部保持不变。
"""
import copy
import os
import sys

sys.path.insert(0, r'D:\Cardinal\tools')
import patchio

SRC = {
    'demo_S4_sampling__v1739': r'D:\Cardinal\patches\demo_S4_sampling__v1739.vcv',
    'demo_S5_fullkit__v1739': r'D:\Cardinal\patches\demo_S5_fullkit__v1739.vcv',
}
BASE = r'D:\Cardinal\patches\mini_arranger_expanded.vcv'
V = __import__('datetime').datetime.now().strftime('%H%M')

# ---- 取一个「能正常打开的 Bogaudio-Mix8」当模板，保证 version 字段类型正确 ----
_tpl = None
for f in [BASE, r'D:\Cardinal\patches\Final Patch Work.vcv'] + \
         [os.path.join(r'D:\Cardinal\refs\examples', n)
          for n in (os.listdir(r'D:\Cardinal\refs\examples') if os.path.isdir(r'D:\Cardinal\refs\examples') else [])]:
    try:
        p = patchio.read_patch(f)
    except Exception:
        continue
    for m in p.get('modules', []):
        if m.get('model') == 'Bogaudio-Mix8':
            _tpl = copy.deepcopy(m)
            print('模板来源:', os.path.basename(f))
            break
    if _tpl:
        break
if _tpl is None:
    print('!! 本机没有 Bogaudio-Mix8 样板，version 字段只能手写（风险自担）')
    _tpl = {'plugin': 'BogaudioModules', 'model': 'Bogaudio-Mix8',
            'version': '2.0', 'params': [], 'data': {}}

# dB→归一化（范围 -60 ~ +6）
DB_MIN, DB_MAX = -60.0, 6.0


def db_to_norm(db):
    return max(0.0, min(1.0, (db - DB_MIN) / (DB_MAX - DB_MIN)))


UNIT = db_to_norm(0.0)          # 0 dB = 1.0 增益
CH_IN = [3 * i + 2 for i in range(8)]     # 通道 i 的音频输入端口号


def mix8(new_id, x, y, level_db=0.0):
    """8 通道混音器：每路 LEVEL 推子 + PAN + MUTE(0=开)，末尾 Master。"""
    m = copy.deepcopy(_tpl)
    for k in ('leftModuleId', 'rightModuleId'):
        m.pop(k, None)
    m['id'] = new_id
    m['pos'] = [x, y]
    params = {}
    for i in range(8):
        params[3 * i + 0] = UNIT            # LEVEL 推子
        params[3 * i + 1] = 0.0             # MUTE = Unmuted（★0 才是开）
        params[3 * i + 2] = 0.0             # PAN 居中
    params[24] = UNIT                        # MIX_PARAM  Master level
    params[25] = 0.0                         # MIX_MUTE   = Unmuted
    params[26] = 0.0                         # MIX_DIM    = Disabled
    m['params'] = [{'value': float(v), 'id': int(k)} for k, v in sorted(params.items())]
    data = m.get('data')
    data = dict(data) if isinstance(data, dict) else {}
    data['poly_channel_offset'] = -1
    m['data'] = data
    assert level_db is not None
    return m


def key_of(m):
    pl = m['plugin'] if isinstance(m['plugin'], str) else m['plugin'].get('slug')
    return '%s/%s' % (pl, m['model'])


def convert(src_path, out_path, name):
    d = patchio.read_patch(src_path)
    mods, cables = d['modules'], d['cables']
    ids = {m['id']: m for m in mods}

    old_mixers = [m for m in mods if m.get('model') == 'Mixer']
    assert old_mixers, '%s 没找到 Fundamental/Mixer' % name

    # 收集旧接线：按 (输入模块, 输入端口) -> 旧 mixer 输出端口
    cids = max([c['id'] for c in cables] + [0])
    added = 0
    for om in old_mixers:
        mid = om['id']
        x, y = om['pos']
        # 找出所有「以这个 mixer 为输出」的线
        outs = [c for c in cables if c['outputModuleId'] == mid]
        # 找出所有「以这个 mixer 为输入」的线 —— 需要改写它们的 inputId
        ins = [c for c in cables if c['inputModuleId'] == mid]
        if not outs:
            # 没有任何输出 = 死模块，直接删
            cables = [c for c in cables if c['outputModuleId'] != mid]
            mods.remove(om)
            print('  %s: Mixer id=%d 无输出，删除' % (name, mid))
            continue

        new = mix8(mid, x, y)                 # **同 id 同位置**，替换而非新增
        mods[mods.index(om)] = new

        # 出线：Mixer.OUT0(单声道) → MIX8.OUT0(L) 与 MIX8.OUT1(R)
        # ★ 原来的 L 线就地改成 L，另加一根 R 线。
        #   若下游模块是 HostAudio2，R 必须接它的 IN1 —— 它有 2 个输入（IN0 左 / IN1 右），
        #   只接 IN0 就等于右声道丢失（这正是原来单声道的毛病）。
        new_ids = []
        folded = 0
        for c in outs:
            assert c['outputId'] == 0, 'Mixer 输出口应只有 0，实得 %d' % c['outputId']
            c['outputId'] = 0                 # L（就地保留）
            new_ids.append(c)
            cids += 1
            r2 = copy.deepcopy(c)
            r2['id'] = cids
            r2['outputId'] = 1                # R
            im = ids.get(c['inputModuleId'])
            imn = im.get('model') if im else None
            if imn == 'HostAudio2':
                # HostAudio2 有 2 输入：IN0=左 IN1=右 —— 正好对上，立体声直达
                r2['inputId'] = 1
            elif imn in ('VCF', 'VCA-1', 'Mixer'):
                # 这些是**单声道**模块（VCF 音频只有 IN3、VCA-1 只有 IN1）。
                # 两根线都接同一个输入口会被 Rack 视作「同口多线」，
                # 后一根会把前一根的连接挤掉（实测 S5 曾出现三根 R 线全挤 IN3）。
                # 正确做法：只留 L 那根，立体声在这一级折叠成单声道。
                folded += 1
                continue
            else:
                r2['inputId'] = c['inputId']
            cables.append(r2)
            new_ids.append(r2)
            added += 1
        if folded:
            print('  %s: MIX8 id=%d 下游为单声道模块，%d 路右声道在此折叠（不接）'
                  % (name, mid, folded))
        # 入线：Mixer.IN0-5（连续编号）→ MIX8 通道 1..6 的音频口 3i+2
        # 入线：Mixer.IN0-5（连续）→ MIX8 通道 1..6 的音频口（3i+2）
        for c in ins:
            n = c['inputId']
            assert 0 <= n < 8, 'Mixer IN%d 越界' % n
            c['inputId'] = CH_IN[n]
        print('  %s: Mixer id=%d → MIX8（位置 %s 不变，入线 %d 改写，出线 %d→%d 根）'
              % (name, mid, (x, y), len(ins), len(outs), len(outs) + 1 - folded))

    # ---- 审计 ----
    # ★ 注意：源文件可能已被 Cardinal 存盘覆盖过（version 被规范化、data 变 None、
    #   并带回**合法的** left/rightModuleId 排序链）。这些都不是缺陷：
    #   排序链指向真实存在的模块 = 正常；data=None 也是 Cardinal 自己的写法。
    #   只清「真悬空」—— 指向不存在模块的指针，那才是加载即崩的真元凶。
    ids = {m['id']: m for m in mods}
    for m in mods:
        for k in ('leftModuleId', 'rightModuleId'):
            v = m.get(k)
            if v is not None and v not in ids:
                del m[k]
                print('  %s: 清掉 %s 的悬空 %s=%s' % (name, key_of(m), k, v))
        if not isinstance(m.get('version'), str):
            errs.append('%s version 非字符串' % key_of(m))
    errs = []
    for m in mods:
        for k in ('leftModuleId', 'rightModuleId'):
            if m.get(k) is not None and m[k] not in ids:
                errs.append('%s 悬空 %s=%s' % (key_of(m), k, m[k]))
        if not isinstance(m.get('version'), str):
            errs.append('%s version 非字符串' % key_of(m))
    m8 = {m['id']: m for m in mods if m.get('model') == 'Bogaudio-Mix8'}
    for mid, m in m8.items():
        if len(m['params']) != 27:
            errs.append('MIX8 id=%s param 数 %d，应 27' % (mid, len(m['params'])))
        pv = {p['id']: p['value'] for p in m['params']}
        for i in range(8):
            if pv.get(3 * i + 1) != 0.0:
                errs.append('MIX8 id=%s 通道%d MUTE=%s，应 0（=Unmuted）' % (mid, i + 1, pv.get(3 * i + 1)))
        if pv.get(25) != 0.0:
            errs.append('MIX8 id=%s Master MUTE=%s，应 0' % (mid, pv.get(25)))
    for c in cables:
        if c['outputModuleId'] not in ids:
            errs.append('悬空输出模块 %s' % c['outputModuleId'])
        if c['inputModuleId'] not in ids:
            errs.append('悬空输入模块 %s' % c['inputModuleId'])
        om = ids.get(c['outputModuleId'])
        if om is not None and om.get('model') == 'Bogaudio-Mix8' and c['outputId'] > 1:
            errs.append('MIX8 OUT%d 不存在' % c['outputId'])
        im = ids.get(c['inputModuleId'])
        if im is not None and im.get('model') == 'Bogaudio-Mix8':
            n = c['inputId']
            if n != 24 and not any(n == CH_IN[i] for i in range(8)):
                errs.append('MIX8 IN%d 不是音频/CV 端口' % n)
    # ★ HostAudio2 的两根输入（IN0=左 IN1=右）都必须有 MIX8 接上，
    #   否则会只剩单声道（HostAudio.cpp:47 numInputs=2）
    for m in mods:
        if m.get('model') == 'HostAudio2':
            got = {c['inputId'] for c in cables
                   if c['inputModuleId'] == m['id']
                   and ids[c['outputModuleId']].get('model') == 'Bogaudio-Mix8'}
            if got and got != {0, 1}:
                errs.append('HostAudio2 id=%s 只接到 MIX8 的 %s，应同时接 IN0(IN0=左) 与 IN1(R)'
                            % (m['id'], sorted(got)))
    assert not errs, '%s 审计失败:\n  ' % name + '\n  '.join(errs)

    patch = dict(d)
    patch['modules'] = mods
    patch['cables'] = cables
    patch['path'] = out_path
    patchio.write_patch(out_path, patch, as_archive=True)

    back = patchio.read_patch(out_path)
    # 回读只查「真悬空」—— 指向不存在模块的指针。指向真实模块的是合法排序链。
    bids = {m['id'] for m in back['modules']}
    dang = [(m['id'], k, m[k]) for m in back['modules']
            for k in ('leftModuleId', 'rightModuleId')
            if m.get(k) is not None and m[k] not in bids]
    assert not dang, '回读发现悬空指针 %s' % dang
    n_mix8 = sum(1 for m in back['modules'] if m['model'] == 'Bogaudio-Mix8')
    print('  → 写出 %-40s 模块%2d 线%2d  MIX8×%d（新增 %d 根右声道线）'
          % (os.path.basename(out_path), len(back['modules']), len(back['cables']), n_mix8, added))
    print()


print('=' * 66)
print('S4 —— Fundamental/Mixer → Bogaudio-Mix8（只换混音器，位置不动）')
print('=' * 66)
convert(SRC['demo_S4_sampling__v1739'],
        r'D:\Cardinal\patches\demo_S4_mix8__v%s.vcv' % V, 'S4')

print('=' * 66)
print('S5 —— 同上')
print('=' * 66)
convert(SRC['demo_S5_fullkit__v1739'],
        r'D:\Cardinal\patches\demo_S5_mix8__v%s.vcv' % V, 'S5')

print('★ 每路通道现在都有三件套：LEVEL 推子（-60~+6dB）/ PAN 声像 / MUTE 按钮（带 Solo）')
print('  外加 Master level / mute / dim —— 总线级也能控。')
print('★ 顺手修掉的隐性缺陷：原 Mixer 单声道 OUT0，现在左右声道分开接，')
print('  所以右声道不再丢失（原来单声道进 HostAudio2 只占了 IN0）。')
