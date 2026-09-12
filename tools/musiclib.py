"""musiclib：节奏型 / 和弦进行 / 音色配方 三合一知识库 + 落地工具。

和 paramlib 的分工
------------------
- paramlib 回答「第 7 号旋钮是什么」——从源码抓来的客观事实。
- musiclib 回答「温暖的感觉该怎么拧」——配方和素材，会随口味改。

三层数据
--------
1. drum_patterns   16 分音符网格，用 'x'(强) 'o'(中) '.'(无) 表示，一行一小节。
2. progressions    和弦进行，用级数表示（I/ii/vi...），可移调到任意调。
3. recipes         音色配方：模块 + 参数名 + 建议值 + 为什么这么拧。
                  参数写的是**名字**不是编号，靠 paramlib 翻译成编号，
                  这样即使模块升级换了编号，配方也不会失效。

用法
----
    python musiclib.py styles                       # 列节奏型
    python musiclib.py drums lofi_hiphop            # 看节奏型网格
    python musiclib.py chords pop_1564 D minor      # 看和弦进行（D 小调）
    python musiclib.py recipes                      # 列音色配方
    python musiclib.py recipe warm_pad               # 看配方细节
    python musiclib.py apply "D:/Cardinal/patches/helm_keys.vcv" warm_pad
                                                     # 把配方写进机架
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "music")
OUT_FILE = os.path.join(OUT_DIR, "knowledge.json")

sys.path.insert(0, HERE)


# ================================================================ 节奏型
# 16 分音符网格：每小节 16 格。x=重音 o=轻音 .=不发声
# 可以多行表示多小节，用 | 分隔便于阅读（解析时会去掉）

DRUM_PATTERNS = {
    "four_on_floor": {
        "name": "四四拍 / House",
        "bpm": [118, 128],
        "mood": "稳、能跳、万能",
        "desc": "底鼓每拍一下（four on the floor），反拍开镲是 house 的灵魂。",
        "kick": "x...x...x...x...",
        "snare": "....x.......x...",
        "hat": "..o...o...o...o.",
    },
    "rock_basic": {
        "name": "摇滚基本型",
        "bpm": [100, 140],
        "mood": "直接、有推动力",
        "desc": "底鼓 1、3 拍，军鼓 2、4 拍。最经典的鼓点。",
        "kick": "x.......x.......",
        "snare": "....x.......x...",
        "hat": "x.o.x.o.x.o.x.o.",
    },
    "lofi_hiphop": {
        "name": "Lo-fi Hip Hop",
        "bpm": [70, 92],
        "mood": "懒散、怀旧、适合学习背景",
        "desc": "底鼓偏后（第 1 拍和第 2.5 拍），军鼓在第 3 拍，整体有摇摆感。",
        "kick": "x.....o.x.......",
        "snare": "........x.......",
        "hat": "o.o.o.o.o.o.o.o.",
    },
    "trap": {
        "name": "Trap",
        "bpm": [130, 150],
        "mood": "压迫、现代",
        "desc": "808 底鼓 + 密集的滚奏 hi-hat。军鼓在第 3 拍。",
        "kick": "x.....o...x.....",
        "snare": "........x.......",
        "hat": "xoxxooxxoxxoxoxx",
    },
    "breakbeat": {
        "name": "Breakbeat",
        "bpm": [160, 175],
        "mood": "碎、有劲、dnb 味",
        "desc": "把底鼓和军鼓打散，制造「断拍」的紧张感。",
        "kick": "x.....x...x.....",
        "snare": "....x..x..x.x...",
        "hat": "o.o.o.o.o.o.o.o.",
    },
    "ballad": {
        "name": "慢歌 / 叙事",
        "bpm": [60, 80],
        "mood": "舒缓、留白",
        "desc": "稀疏的底鼓和军鼓，给旋律和人声让位置。",
        "kick": "x.......o.......",
        "snare": "....x.......x...",
        "hat": "..o...o...o...o.",
    },
    "bossa": {
        "name": "Bossa Nova",
        "bpm": [90, 110],
        "mood": "轻松、有呼吸",
        "desc": "两个小节的呼应型，底鼓和军鼓交错咬合。",
        "kick": "x..o..x...x..o..",
        "snare": "..o..x..o..x..o.",
        "hat": "o.o.o.o.o.o.o.o.",
    },
    "halftime": {
        "name": "半速 / 后摇氛围",
        "bpm": [60, 75],
        "mood": "沉重、辽阔",
        "desc": "军鼓落在第 3 拍、感觉像慢了一半，适合铺长的段落。",
        "kick": "x.......x.......",
        "snare": "........x.......",
        "hat": "o...o...o...o...",
    },
    "none": {
        "name": "不要鼓",
        "bpm": [0, 0],
        "mood": "纯氛围",
        "desc": "留空，只保留和声与音色。",
        "kick": "." * 16, "snare": "." * 16, "hat": "." * 16,
    },
}


# ================================================================ 和弦进行
# degrees 用级数；大小写区分大小三和弦；数字后缀表示七和弦（如 ii7、V7）

PROGRESSIONS = {
    "pop_1564": {
        "name": "流行万能 (I–V–vi–IV)",
        "degrees": ["I", "V", "vi", "IV"],
        "mood": "明亮、通用、几乎不会错",
        "style": ["pop", "ballad"],
        "desc": "被用烂但真的好用。适合做副歌。",
    },
    "pop_6415": {
        "name": "小调感流行 (vi–IV–I–V)",
        "degrees": ["vi", "IV", "I", "V"],
        "mood": "uplifting 里带一点忧郁",
        "style": ["pop", "edm"],
        "desc": "从六级起手，情绪更「抓」。EDM 副歌常客。",
    },
    "canon": {
        "name": "卡农进行 (I–V–vi–iii–IV–I–IV–V)",
        "degrees": ["I", "V", "vi", "iii", "IV", "I", "IV", "V"],
        "mood": "叙事、有推进感",
        "style": ["pop", "ballad"],
        "desc": "八小节完整版，低音线是级进下行，很好配旋律。",
    },
    "jazz_251": {
        "name": "爵士 ii–V–I",
        "degrees": ["ii7", "V7", "Imaj7"],
        "mood": "温暖、有解决感",
        "style": ["jazz", "lofi"],
        "desc": "功能和声的核心句式。加个 vi7 就成 loop。",
    },
    "lofi_2516": {
        "name": "Lo-fi 循环 (ii7–V7–Imaj7–vi7)",
        "degrees": ["ii7", "V7", "Imaj7", "vi7"],
        "mood": "松弛、怀旧、能无限循环",
        "style": ["lofi", "jazz"],
        "desc": "七和弦让色彩变软，适合配 lo-fi 鼓。",
    },
    "minor_epic": {
        "name": "史诗小调 (i–VI–III–VII)",
        "degrees": ["i", "VI", "III", "VII"],
        "mood": "壮阔、有电影感",
        "style": ["epic", "edm"],
        "desc": "小调里最「燃」的进行，配大混响很有效。",
    },
    "andalusian": {
        "name": "安达卢西亚 (i–VII–VI–V)",
        "degrees": ["i", "VII", "VI", "V"],
        "mood": "异域、宿命感",
        "style": ["flamenco", "epic"],
        "desc": "西班牙弗拉门戈的经典下行。最后一个 V 是大三，很有张力。",
    },
    "blues_12": {
        "name": "12 小节布鲁斯",
        "degrees": ["I7", "I7", "I7", "I7", "IV7", "IV7", "I7", "I7",
                    "V7", "IV7", "I7", "V7"],
        "mood": "根源、会自己走起来",
        "style": ["blues", "rock"],
        "desc": "标准 12 小节，全是属七和弦。",
    },
    "ambient_drone": {
        "name": "氛围长音 (i 挂留)",
        "degrees": ["i", "i", "VI", "VI"],
        "mood": "静止、冥想",
        "style": ["ambient", "drone"],
        "desc": "每个和弦停很久，靠音色变化而不是和声变化推动。",
    },
    "bedroom_4536": {
        "name": "卧室流行 (IV–V–iii–vi)",
        "degrees": ["IV", "V", "iii", "vi"],
        "mood": "青春、日系",
        "style": ["pop"],
        "desc": "日系/动漫歌曲高频进行。",
    },
}


# ================================================================ 音色配方
# 参数写名字（靠 paramlib 翻译成编号）。value 是模块内部刻度值不是百分比。

RECIPES = {
    "warm_pad": {
        "name": "温暖铺底 Pad",
        "target": ["VCO", "VCF", "ADSR", "Plateau"],
        "mood": "柔和、有空间、不抢戏",
        "desc": "起音慢、释放长、滤波略暗，混响给足。适合垫在旋律下面。",
        "settings": [
            {"module": "ADSR", "param": "Attack", "value": 0.45, "why": "起音慢，声音是「浮上来」而不是「砸下来」"},
            {"module": "ADSR", "param": "Decay", "value": 0.6, "why": "缓降"},
            {"module": "ADSR", "param": "Sustain", "value": 0.8, "why": "按住时保持饱满"},
            {"module": "ADSR", "param": "Release", "value": 0.75, "why": "松手后留一条尾巴"},
            {"module": "VCF", "param": "Cutoff frequency", "value": 6.0, "why": "比中心高一点，滤掉刺耳的高频但保留空气感"},
            {"module": "VCF", "param": "Resonance", "value": 0.12, "why": "一点点共振让声音有「肉」"},
            {"module": "VCO", "param": "Frequency modulation", "value": 0.05, "why": "轻微力度响应，保留动态"},
            {"module": "Plateau", "param": "Wet level", "value": 0.45, "why": "混响给足，制造空间"},
            {"module": "Plateau", "param": "Size", "value": 0.75, "why": "大空间"},
            {"module": "Plateau", "param": "Decay", "value": 0.8, "why": "混响尾巴长"},
        ],
    },
    "bright_pluck": {
        "name": "明亮拨弦 Pluck",
        "target": ["VCO", "VCF", "ADSR", "Plateau"],
        "mood": "清脆、有颗粒感",
        "desc": "短促的起音 + 快速衰减，滤波开亮。适合旋律和琶音。",
        "settings": [
            {"module": "ADSR", "param": "Attack", "value": 0.02, "why": "几乎瞬间起音，才有「拨」的感觉"},
            {"module": "ADSR", "param": "Decay", "value": 0.22, "why": "快速衰减是拨弦的关键"},
            {"module": "ADSR", "param": "Sustain", "value": 0.0, "why": "不保持，让它自然消失"},
            {"module": "ADSR", "param": "Release", "value": 0.2, "why": "短尾巴"},
            {"module": "VCF", "param": "Cutoff frequency", "value": 18.0, "why": "开亮，保留泛音"},
            {"module": "VCF", "param": "Resonance", "value": 0.2, "why": "轻微共振增加「叮」的质感"},
            {"module": "Plateau", "param": "Wet level", "value": 0.28, "why": "少量混响，不要太湿"},
        ],
    },
    "lofi_keys": {
        "name": "Lo-fi 键盘",
        "target": ["VCO", "VCF", "ADSR", "Plateau"],
        "mood": "闷、旧、像卡带",
        "desc": "滤波压暗 + 起音略慢，配合 lo-fi 鼓非常合适。",
        "settings": [
            {"module": "ADSR", "param": "Attack", "value": 0.08, "why": "轻微延迟的起音"},
            {"module": "ADSR", "param": "Decay", "value": 0.5, "why": "中等衰减"},
            {"module": "ADSR", "param": "Sustain", "value": 0.45, "why": "保持一点，让和弦连起来"},
            {"module": "ADSR", "param": "Release", "value": 0.4, "why": "自然收尾"},
            {"module": "VCF", "param": "Cutoff frequency", "value": -6.0, "why": "压低截止，去掉亮的高频"},
            {"module": "VCF", "param": "Resonance", "value": 0.05, "why": "几乎不共振，越平越旧"},
            {"module": "VCF", "param": "Drive", "value": 0.2, "why": "轻微过载模拟磁带饱和"},
            {"module": "Plateau", "param": "Wet level", "value": 0.3, "why": "一点混响"},
            {"module": "Plateau", "param": "Size", "value": 0.4, "why": "小房间，不是大厅"},
        ],
    },
    "dark_bass": {
        "name": "暗色贝斯",
        "target": ["VCO", "VCF", "ADSR"],
        "mood": "低、厚、托底",
        "desc": "滤波压到很低 + 快速起音，低频结实不糊。",
        "settings": [
            {"module": "ADSR", "param": "Attack", "value": 0.01, "why": "贝斯要立刻出来"},
            {"module": "ADSR", "param": "Decay", "value": 0.3, "why": "短衰减"},
            {"module": "ADSR", "param": "Sustain", "value": 0.85, "why": "保持住低频"},
            {"module": "ADSR", "param": "Release", "value": 0.12, "why": "干脆收尾，不拖泥带水"},
            {"module": "VCF", "param": "Cutoff frequency", "value": -30.0, "why": "压到很低，只留基频"},
            {"module": "VCF", "param": "Resonance", "value": 0.18, "why": "一点共振让低频更「立」"},
        ],
    },
    "bell": {
        "name": "铃铛 / 钟",
        "target": ["VCO", "VCF", "ADSR", "Plateau"],
        "mood": "清、远、有回响",
        "desc": "极短起音 + 长衰减，配合大混响。适合点缀。",
        "settings": [
            {"module": "ADSR", "param": "Attack", "value": 0.01, "why": "瞬时起音"},
            {"module": "ADSR", "param": "Decay", "value": 0.7, "why": "长的衰减产生「余音」"},
            {"module": "ADSR", "param": "Sustain", "value": 0.0, "why": "完全不保持"},
            {"module": "ADSR", "param": "Release", "value": 0.5, "why": "长释放"},
            {"module": "VCF", "param": "Cutoff frequency", "value": 24.0, "why": "开亮"},
            {"module": "Plateau", "param": "Wet level", "value": 0.5, "why": "大混响"},
            {"module": "Plateau", "param": "Size", "value": 0.9, "why": "大厅"},
            {"module": "Plateau", "param": "Decay", "value": 0.85, "why": "很长的尾巴"},
        ],
    },
    "lead_saw": {
        "name": "主奏锯齿",
        "target": ["VCO", "VCF", "ADSR", "Plateau"],
        "mood": "有力、穿透",
        "desc": "中等起音 + 高保持，滤波开亮带共振。适合当主旋律。",
        "settings": [
            {"module": "ADSR", "param": "Attack", "value": 0.06, "why": "稍微留一点起音，不至于太生硬"},
            {"module": "ADSR", "param": "Decay", "value": 0.4, "why": "中等"},
            {"module": "ADSR", "param": "Sustain", "value": 0.75, "why": "保持住，长音不断"},
            {"module": "ADSR", "param": "Release", "value": 0.3, "why": "中等尾巴"},
            {"module": "VCF", "param": "Cutoff frequency", "value": 14.0, "why": "偏亮，能穿过混音"},
            {"module": "VCF", "param": "Resonance", "value": 0.3, "why": "共振让音色更有「性格」"},
            {"module": "Plateau", "param": "Wet level", "value": 0.22, "why": "少量混响，保持清晰"},
        ],
    },
    "lofi_kick": {
        "name": "柔化底鼓",
        "target": ["BassDrum9"],
        "mood": "闷、不刺耳",
        "desc": "把底鼓速度放慢一点、选一个柔和的采样，音量别太大。",
        "settings": [
            {"module": "BassDrum9", "param": "Sample", "value": 0.0, "index": 0, "why": "换一个采样（0–15 逐个试）"},
            {"module": "BassDrum9", "param": "Playback Speed", "value": 0.85, "index": 0, "why": "放慢一点，听起来更「旧」"},
        ],
        "note": "Sample 参数有多个槽位（0 和 1 各对应一个鼓声），index 指定改第几个。",
    },
    "halftime_kit": {
        "name": "半速鼓组",
        "target": ["Clocked", "BassDrum9", "ClosedHiHat", "CR78"],
        "mood": "沉、慢、氛围",
        "desc": "把时钟 BPM 降到 70 附近，底鼓和军鼓拉稀。",
        "settings": [
            {"module": "Clocked", "param": "Master clock", "value": 72.0, "why": "整体放慢"},
            {"module": "Clocked", "param": "Clk 1 ratio", "value": -1.0, "why": "镲放慢一档，变成四分音符"},
            {"module": "Clocked", "param": "Clk 2 ratio", "value": -3.0, "why": "复合鼓放慢，只在小节头出现"},
        ],
    },
}


# ================================================================ MIDI 音高

NOTE_BASE = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
             "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}

# 级数 -> 半音偏移。大小调各一套，别用「大调整体下移」那种偷懒算法，
# 那样会算错 III/VI/VII 的根音（D 小调的 i 会被算成 F）。
MAJOR_SCALE = {"I": 0, "II": 2, "III": 4, "IV": 5, "V": 7, "VI": 9, "VII": 11}
MINOR_SCALE = {"I": 0, "II": 2, "III": 3, "IV": 5, "V": 7, "VI": 8, "VII": 10}

CHORD_INTERVALS = {
    "": [0, 4, 7],          # 大三
    "m": [0, 3, 7],         # 小三
    "7": [0, 4, 7, 10],     # 属七（大小七）
    "maj7": [0, 4, 7, 11],  # 大七
    "m7": [0, 3, 7, 10],    # 小七
}


def parse_key(text):
    """'D minor' / 'F# major' / 'Bb' -> (根音半音, 是否小调)"""
    text = (text or "").strip()
    m = re.match(r"^([A-Ga-g][#b]?)\s*([a-zA-Z]*)", text)
    if not m:
        return 2, False
    root = m.group(1)[0].upper() + m.group(1)[1:]
    mode = m.group(2).lower()
    minor = mode.startswith("m") and not mode.startswith("maj")
    return NOTE_BASE.get(root, 0), minor


def degree_to_chord(degree, root_pc, minor_key):
    """把级数（如 vi7、Imaj7）转成和弦结构。

    级数的大小写决定三和弦性质：大写=大三，小写=小三。
    `ii7` 因此是小七（Dm7），`V7` 是属七（G7）——两者后缀都是 7，靠大小写区分。
    """
    m = re.match(r"^([ivIV]+)(.*)$", degree)
    if not m:
        return None
    roman, suffix = m.group(1), m.group(2)
    scale = MINOR_SCALE if minor_key else MAJOR_SCALE
    key = roman.upper()
    if key not in scale:
        return None

    is_minor_triad = roman.islower()
    if suffix == "maj7":
        quality = "maj7"
    elif suffix == "m7":
        quality = "m7"
    elif suffix == "7":
        quality = "m7" if is_minor_triad else "7"
    else:
        quality = "m" if is_minor_triad else ""

    return {"degree": degree, "root": (root_pc + scale[key]) % 12,
            "quality": quality, "intervals": CHORD_INTERVALS[quality]}


def chord_notes(chord, octave=4):
    """把和弦转成 MIDI 音高列表。中央 C = 60。"""
    base = 12 * (octave + 1) + chord["root"]
    return [base + i for i in chord["intervals"]]


def voice_lead(prev, notes, anchor=None):
    """声部连接：整体移八度，让和弦落在最靠近上一个和弦的音域。

    不做转位（根音仍在最低），只挪八度——这样既衔接顺畅，
    又不会把和弦的低音根音弄丢。

    anchor 是整段的基准中心音高。没有它的话，每次都选「离上一个最近」的八度
    会系统性往下漂（实测 D 小调 i-VI-III-VII 会一路降到 C3）。
    """
    if not prev:
        return list(notes)
    center = sum(prev) / len(prev)
    best = None
    best_d = None
    for shift in (0, -12, 12, -24, 24):
        cand = [n + shift for n in notes]
        cc = sum(cand) / len(cand)
        if anchor is not None and abs(cc - anchor) > 9:
            continue
        d = abs(cc - center)
        if best_d is None or d < best_d:
            best, best_d = cand, d
    return best if best is not None else list(notes)


# ================================================================ 查询接口

def drum_pattern(style):
    p = DRUM_PATTERNS.get(style)
    if not p:
        return None
    out = dict(p)
    out["style"] = style
    out["bars"] = {k: [v[i:i + 16] for i in range(0, len(v), 16)]
                   for k, v in p.items() if k in ("kick", "snare", "hat")}
    return out


def progression(name, key="C major"):
    p = PROGRESSIONS.get(name)
    if not p:
        return None
    root_pc, minor_key = parse_key(key)
    chords = []
    prev = None
    anchor = None
    for d in p["degrees"]:
        c = degree_to_chord(d, root_pc, minor_key)
        if not c:
            continue
        raw = chord_notes(c)
        if anchor is None:
            anchor = sum(raw) / len(raw)
        c["notes"] = voice_lead(prev, raw, anchor)
        c["notes_plain"] = raw
        prev = c["notes"]
        chords.append(c)
    return {"name": p["name"], "mood": p["mood"], "desc": p["desc"],
            "key": key, "degrees": p["degrees"], "chords": chords}


def recipe(name):
    r = RECIPES.get(name)
    if not r:
        return None
    out = dict(r)
    out["name_key"] = name
    return out


def suggest(text):
    """自然语言 -> 候选配方/节奏型。返回 [(类型, key, 名称, 匹配理由)]"""
    t = (text or "").lower()
    hits = []
    for k, r in RECIPES.items():
        score = 0
        if k.replace("_", "") in t.replace("_", "").replace(" ", ""):
            score += 3
        for w in re.split(r"[\s,，/]+", t):
            if not w:
                continue
            if w in r["name"].lower() or w in r.get("mood", "").lower() or w in r.get("desc", "").lower():
                score += 1
        if score:
            hits.append((score, "recipe", k, r["name"], r.get("mood", "")))
    for k, p in DRUM_PATTERNS.items():
        score = 0
        for w in re.split(r"[\s,，/]+", t):
            if not w:
                continue
            if w in p["name"].lower() or w in p.get("mood", "").lower():
                score += 1
        if score:
            hits.append((score, "drums", k, p["name"], p.get("mood", "")))
    for k, p in PROGRESSIONS.items():
        score = 0
        for w in re.split(r"[\s,，/]+", t):
            if not w:
                continue
            if w in p["name"].lower() or w in p.get("mood", "").lower():
                score += 1
        if score:
            hits.append((score, "chords", k, p["name"], p.get("mood", "")))
    hits.sort(key=lambda x: -x[0])
    return hits[:8]


# ================================================================ 落到机架

def apply_recipe(patch_path, name, dry_run=False):
    """把配方写进 .vcv 文件。

    参数名 -> 编号 的翻译交给 paramlib；找不到的参数会明确报出来而不是静默跳过。
    """
    import patchio
    import paramlib as pl

    r = recipe(name)
    if not r:
        return {"error": "没有这个配方: {}".format(name)}
    if not os.path.exists(patch_path):
        return {"error": "找不到机架文件: {}".format(patch_path)}

    patch = patchio.read_patch(patch_path)
    by_model = {}
    for m in patch.get("modules", []):
        by_model.setdefault(m["model"], []).append(m)

    applied, skipped = [], []
    for s in r["settings"]:
        model = s["module"]
        mods = by_model.get(model)
        if not mods:
            skipped.append({"module": model, "param": s["param"],
                            "why": "机架里没有 {} 模块".format(model)})
            continue
        mod = mods[0]
        plugin = mod["plugin"]
        entry = pl.lookup(plugin, model)
        if not entry:
            skipped.append({"module": model, "param": s["param"], "why": "字典里没有这个模块"})
            continue

        want = s["param"].lower()
        # 同名参数可能有多个槽位（如鼓的 Sample），用 index 选第几个
        cands = []
        for pid, p in entry["params"].items():
            if (p.get("name") or "").lower() == want:
                cands.append(int(pid))
        if not cands:
            for pid, p in entry["params"].items():
                if want in (p.get("name") or "").lower():
                    cands.append(int(pid))
        if not cands:
            skipped.append({"module": model, "param": s["param"],
                            "why": "该模块里没有这个参数名"})
            continue
        cands.sort()
        idx = s.get("index", 0)
        if idx >= len(cands):
            skipped.append({"module": model, "param": s["param"],
                            "why": "只有 {} 个同名槽位，要不到第 {}".format(len(cands), idx)})
            continue
        pid = cands[idx]

        params = mod.setdefault("params", [])
        found = False
        for q in params:
            if q.get("id") == pid:
                q["value"] = float(s["value"])
                found = True
                break
        if not found:
            params.append({"id": pid, "value": float(s["value"])})
        applied.append({"module": model, "param": s["param"], "param_id": pid,
                        "value": s["value"], "why": s.get("why", "")})

    if not dry_run and applied:
        patchio.write_patch(patch_path, patch)
    return {"recipe": r["name"], "file": os.path.basename(patch_path),
            "applied": applied, "skipped": skipped, "written": bool(applied and not dry_run)}


def dump():
    os.makedirs(OUT_DIR, exist_ok=True)
    data = {"drum_patterns": DRUM_PATTERNS, "progressions": PROGRESSIONS,
            "recipes": RECIPES}
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return OUT_FILE


# ================================================================ CLI

def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 0
    cmd = argv[1]

    if cmd == "styles":
        for k, p in DRUM_PATTERNS.items():
            print("  {:<16} {:<18} BPM {}-{}  {}".format(
                k, p["name"], p["bpm"][0], p["bpm"][1], p["mood"]))
    elif cmd == "drums":
        p = drum_pattern(argv[2]) if len(argv) > 2 else None
        if not p:
            print("没有这个节奏型")
            return 1
        print("{}  (BPM {}-{})".format(p["name"], p["bpm"][0], p["bpm"][1]))
        print(p["desc"])
        for row in ("kick", "snare", "hat"):
            print("  {:<6} |{}|".format(row, p[row]))
        print("        x=重音 o=轻音 .=空（每格是 16 分音符）")
    elif cmd == "chords":
        if len(argv) < 3:
            for k, p in PROGRESSIONS.items():
                print("  {:<16} {:<32} {}".format(k, p["name"], p["mood"]))
            return 0
        key = " ".join(argv[3:]) if len(argv) > 3 else "C major"
        pr = progression(argv[2], key)
        if not pr:
            print("没有这个进行")
            return 1
        print("{}  [{}]".format(pr["name"], pr["key"]))
        print(pr["desc"])
        for c in pr["chords"]:
            print("  {:<4} {:<6} MIDI {}".format(c["degree"], c["quality"] or "major", c["notes"]))
    elif cmd == "recipes":
        for k, r in RECIPES.items():
            print("  {:<16} {:<18} {}".format(k, r["name"], r["mood"]))
    elif cmd == "recipe":
        r = recipe(argv[2]) if len(argv) > 2 else None
        if not r:
            print("没有这个配方")
            return 1
        print("{}  ({})".format(r["name"], r["mood"]))
        print(r["desc"])
        for s in r["settings"]:
            print("  {:<14} {:<22} = {:<8} {}".format(
                s["module"], s["param"], s["value"], s.get("why", "")))
    elif cmd == "apply":
        if len(argv) < 4:
            print("用法: apply <机架.vcv> <配方名>")
            return 1
        res = apply_recipe(argv[2], argv[3])
        if res.get("error"):
            print("错误:", res["error"])
            return 1
        print("{} -> {}".format(res["recipe"], res["file"]))
        for a in res["applied"]:
            print("  改 {:<4} {} (参数 {}) = {}".format(
                a["module"], a["param"], a["param_id"], a["value"]))
        for s in res["skipped"]:
            print("  跳过 {:<4} {} —— {}".format(s["module"], s["param"], s["why"]))
    elif cmd == "suggest":
        for score, kind, k, nm, mood in suggest(" ".join(argv[2:])):
            print("  [{:<6}] {:<16} {:<20} {}".format(kind, k, nm, mood))
    elif cmd == "dump":
        print("已写出:", dump())
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
