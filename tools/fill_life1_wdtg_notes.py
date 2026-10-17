# -*- coding: utf-8 -*-
"""
Life1 WDTG 机架的**音符内容**（堆层渐入 + 去量化呼吸 + 留白）。

依据文档：
  第 65 行 原声基底「去量化处理，保留杂音与呼吸感」
  第 68 行「反律动设计，故意打乱预期或在进鼓处留白，以缺失感传达张力」
  第 51 行 非线性蒙太奇「跳跃式组合、硬切、故障跳转」
  第 128 行 Life 1 = 爵士 × 合成器 × 弗拉门戈风吉他
  第 125 行 Dark Magic「扭曲呼吸+ 磨砂嗡鸣先压上来，再切温暖电钢和弦」

李的拍板：堆层渐入（大提琴铺底 → 电钢进入 → 后半段吉他加轮）

★ 每小节音符数必须严格 =16（beats×16），休止符写占位 note，不能省
★ 力度（velocity）= 渐入曲线，这是「堆层渐入」的主要手段
★ 音区分工：三个乐器各占一段，不重叠
"""
import sys, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
import patchio

ROOT = 'D:/Cardinal'
# 🔴 与生成器一致：写稳定文件名
F = ROOT + '/patches/quadeca_life1_wdtg.vcv'

BEATS = 16
MEASURES = 8          # 8 小节
LANG = 1              # 全机架统一语言（生命 1 号）

# ============================================================
# 和声骨架：一个 8 小节的循环（爵士 ii-V-I 的循环感）
#   根音按半音（MIDI）：Dm9 → G13 → Cmaj9 → Am11 → Dm9 → G13 → Em7 → Am11
#   写作「根音 + 和弦音级差」
# ============================================================
CHORDS = [
    # (根音, [和弦音级相对半音], 名字)
    (50, [0, 3, 7, 10, 14], 'Dm9'),      # D A C E G
    (43, [0, 4, 7, 11, 14], 'G13'),     # G B D F E(爵士属七带)
    (48, [0, 4, 7, 11, 14], 'Cmaj9'),   # C E G B D
    (45, [0, 3, 7, 10, 14], 'Am11'),    # A C E G B
    (50, [0, 3, 7, 10, 14], 'Dm9'),
    (43, [0, 4, 7, 11, 14], 'G13'),
    (40, [0, 3, 7, 10, 14], 'Em7'),     # E G B D F
    (45, [0, 3, 7, 10, 14], 'Am11'),
]

def blank():
    """休止占位音符（pitch=0, active=False）—— 一格都不能少"""
    return {'pitch': 0, 'velocity': 0.0, 'duration': None,
            'active': False, 'start': None, 'end': None}

def note(pitch, vel):
    return {'pitch': pitch, 'velocity': round(vel, 3), 'duration': None,
            'active': True, 'start': None, 'end': None}

# ============================================================
# 声部一：**大提琴** —— 全程铺底，但用**力度起伏**呼吸，不是死音墙
#   音区 D2-A3 (38-57)，大提琴真实音域
#   文档第65行「保留呼吸感」⇒ 每小节开头最强、尾巴渐弱
# ============================================================
def cello_measure(mi):
    root, ivs, _ = CHORDS[mi]
    # 只取根音 + 第五音，做长音；八度在高一点保持大提琴音域
    notes = []
    # 第 1 小节稍强（"扭曲呼吸+磨砂嗡鸣先压上来"）
    base_v = 0.42 if mi == 0 else 0.30
    for beat in range(BEATS):
        # 呼吸曲线：每 4 格一个起伏（对应 1/4 拍感）
        ph = (beat % 4) / 4.0
        vel = base_v * (1.0 - 0.45 * ph)
        if beat % 4 == 0:
            # 根音在强拍
            notes.append(note(root, vel))
        elif beat % 8 == 4:
            # 反拍给第五音，制造错位（第68行"反律动"）
            notes.append(note(root + 7, vel * 0.85))
        elif beat in (6, 14):
            # 第 68 行：进拍处留白 ⇒ 第 6/14 格空
            notes.append(blank())
        else:
            notes.append(blank())
    return notes

# ============================================================
# 声部二：**温暖电钢** —— **堆层渐入的核心**
#   「先压上来（大提琴），再切（电钢进来）」⇒ 前 3 小节不出，第 3 小节尾进
#   音区 C3-C5 (48-72)，避开大提琴
#   爵士和弦音（用 ivs 的全部），但**切成断奏琶音**，不铺满
# ============================================================
EP_START = 3          # 第 4 小节（0起）进 = 3 小节后切进来

def ep_measure(mi):
    if mi < EP_START:
        return [blank() for _ in range(BEATS)]      # 严格留白
    root, ivs, _ = CHORDS[mi]
    # 渐入：进入头两小节从 0.15 涨到 0.38
    t = min(1.0, (mi - EP_START + 1) / 2.0)
    base_v = 0.15 + 0.23 * t
    notes = []
    # 爵士断奏：每 8 格一组 4 连音，第 3 个音后留白（第68行 留白）
    pattern = [0, 1, 2, 3]   # 音级索引
    for beat in range(BEATS):
        if beat % 8 in (0, 1, 2, 3):
            k = pattern[beat % 8]
            # 🔴 音区分工：大提琴 40-50 / 吉他 57-69 / 电钢 64-84
            # 根音 38-50抬一个八度(+12)= 50-62，再加 ivs(最高+14) => 最高 76。
            # 用 +12 而非 +24：+24 会让电钢最高到 96（超出真实电钢音域）。
            notes.append(note(root + ivs[k % len(ivs)] + 12
                              + (12 if (beat % 8) >= 2 else 0),
                              base_v * (1.0 if k % 2 == 0 else 0.75)))
        else:
            notes.append(blank())       # 留白：不填满
    return notes

# ============================================================
# 声部三：**弗拉门戈风吉他** —— **后半段加轮**（李拍板）
#   「后半段吉他加轮」⇒ 前 6 小节不进，第 7 小节起
#   音区 A3-E5 (57-76)，吉他最高声部，不与电钢/大提琴打架
#   弗拉门戈的「点弦」感⇒ 强弱交替、留白多
# ============================================================
GTR_START = 6

def gtr_measure(mi):
    if mi < GTR_START:
        return [blank() for _ in range(BEATS)]
    root, ivs, _ = CHORDS[mi]
    base_v = 0.40 if mi == GTR_START else 0.50
    notes = []
    # 弗拉门戈轮：反复拨一个根音+八度，力度强弱交替（rasgueado 的简化）
    for beat in range(BEATS):
        # 强拍 & 反拍拨弦，其余留白 ⇒ 密度约 1/2，有呼吸
        if beat % 4 == 0 or beat % 8 == 6:
            # 🔴 音区分工：大提琴 40-50 / 吉他 57-69 / 电钢 64-84
            # 吉他比大提琴高、比电钢低，压在中间，避开两者
            pitch = root + 12 if beat % 4 == 0 else root + 19
            strong = (beat % 4 == 0)
            notes.append(note(pitch, base_v * (1.0 if strong else 0.6)))
        else:
            notes.append(blank())
    return notes

# ============================================================
# 写入
# ============================================================
p = patchio.read_patch(F)
prolls = [m for m in p['modules'] if m['model'] == 'rcm-pianoroll']
assert len(prolls) == 3, '期望 3 个 pianoroll，实际 %d' % len(prolls)

BUILDERS = [cello_measure, ep_measure, gtr_measure]
LABELS = ['大提琴 Elements', '电钢 Bogaudio-VCO+VCF', '吉他 Plaits+Waveshaper']

for m, builder, label in zip(prolls, BUILDERS, LABELS):
    d = m['data']
    # 每小节严格 16 格
    measures = []
    for mi in range(MEASURES):
        cells = builder(mi)
        assert len(cells) == BEATS, '%s 第%d小节 %d 格，应为 %d' % (label, mi, len(cells), BEATS)
        measures.append({'notes': cells})
    pat = d['patterns'][0]
    pat['measures'] = measures
    # 不自动开播
    d['sequenceRunning'] = False
    # 🔴 driverMode 不是「语言模式」，源码 `PianoRollModule.cpp:125/142`：
    # 它只决定 **reset 后要不要立刻走一步**（等外部时钟 vs 用内部时钟）。
    # 保持 false，让时钟完全由外部 Clocked 驱动。
    d['driverMode'] = False
    # 显示范围：让面板能看到本层音区（★ 低于 lowestDisplayNote 会显示到面板外）
    active = [n['pitch'] for mm in measures for n in mm['notes'] if n['active']]
    if active:
        d['lowestDisplayNote'] = min(active) - 3

    tot = len(measures) * BEATS
    act = sum(1 for mm in measures for n in mm['notes'] if n['active'])
    print('%-26s 小节 %d  音符 %3d/%3d (%4.0f%%)  音域 %d~%d显示下限 %d'
          % (label, MEASURES, act, tot, 100.0 * act / tot,
             min(active), max(active), d['lowestDisplayNote']))

patchio.write_patch(F, p)
print()
print('音符已写入 ->', os.path.basename(F))
print()
print('堆层时间轴（力度渐入）：')
print('  小节1-3：大提琴铺底（力度呼吸）   ▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░')
print('  小节4起：+ 电钢断奏切进来 0.15 -> 0.38')
print('  小节7起：+ 吉他加轮 0.40 -> 0.50')