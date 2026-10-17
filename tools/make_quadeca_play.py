# -*- coding: utf-8 -*-
"""make_quadeca_play.py —— 「你能弹」的那张 patch。

李 10-17 要求：
  · 我能弹出他那种风格的音 → 键盘进来，和声/音色按 Quadeca 风格配好
  · 包括我的鼓机，那么多参数你全部给我利用上
  · 不要编曲器（Starsea）框住

所以这张 = HostMIDI + 三层音色（和弦垫/低音/主音）+ WSTD 全套鼓机（每块 32 参数全用）
         + 鼓机音序器（自动铺底鼓，让你专心弹）+ 混音 + 混响。

端口全部实测自本机已验收机架（见 _probe_kb.py）：
  HostMIDI  OUT0=PITCH  OUT1=GATE  OUT2=VELOCITY     data.channels 决定复音数
  WSTD 鼓    触发 IN(16+i)   音频 OUT(i)   采样 param(i)   速度 param(16+i)
  Sequencer  IN0=CLOCK  IN1=TRACK_SELECT  OUT0-7=8 轨触发
  Gnome      OUT6 → Sequencer.IN0（自走时钟，params: BPM/WIDTH/RUN/SWING）
"""
import copy
import sys

sys.path.insert(0, r"D:\Cardinal\tools")
import patchio

SRC = r"D:\Cardinal\patches\Final Patch Work.vcv"      # Gnome + Sequencer 在这
SRC_DRUM = r"D:\Cardinal\patches\helm_full.vcv"      # 五种鼓机都在这（已验收）
SRC_KB = r"D:\Cardinal\patches\mini_arranger_expanded.vcv"   # HostMIDI 链在这
SRC_MIX = r"D:\Cardinal\patches\demo_S4_sampling.vcv"        # Mixer 在这
# ★ 带版本号 ⇒ 每次生成新文件名，**绝不覆盖李手工挪好的布局**（李 12:27 硬要求）
import datetime as _dt
OUT = r"D:\Cardinal\patches\quadeca_play__v%s.vcv" % _dt.datetime.now().strftime("%H%M")

# 各模型真实 param 数（实测）
# ⚠️ 实测值（2026-10-17 扫本机全部机架得出，与我原先的记忆不符）：
#   OpenHiHat = **50** 个 param（不是 32）；Sequencer = **151** 个（不是 37）
PARAM_COUNT = {"HostMIDI": 0, "ADSR": 9, "VCO": 8, "VCA-1": 2,
               "Mixer": 1, "BassDrum9": 32, "SnareDrumN": 32,
               "ClosedHiHat": 32, "OpenHiHat": 50, "Tomi": 32,
               "Sequencer": 151, "Gnome": 4, "TextEditor": 0,
               "HostAudio2": 1}


def src_all():
    return (patchio.read_patch(SRC), patchio.read_patch(SRC_KB),
            patchio.read_patch(SRC_MIX), patchio.read_patch(SRC_DRUM))


def find(patch, model, plugin=None):
    for m in patch["modules"]:
        if m["model"] == model and (plugin is None or m["plugin"] == plugin):
            return m
    raise KeyError("%s / %s" % (plugin, model))


# ---------------------------------------------------------------- 鼓机配方
# 每个鼓 32 个 param = param(0..15) 选采样 + param(16+i) 播放速度（声部 i）
# 「全部用上」= 32 个全部显式写值，两声部都指定采样与速度。
def drum_params(voice0, speed0, voice1, speed1, total):
    """32/50 个 param 的通用写法：param(i)=采样选择，param(16+i)=播放速度。
    OpenHiHat 是 50 个（多一组控制），所以按 total 裁剪，绝不写越界 id。"""
    p = {}
    half = total // 2
    for i in range(half):
        p[i] = voice0 if i % 2 == 0 else voice1     # 两个声部交替用不同采样
    for i in range(total - half):
        p[half + i] = speed0 if i % 2 == 0 else speed1
    return p


DRUMS = [
    # model,        声部0采样 声部1采样  声部0速度 声部1速度  用途
    ("BassDrum9",   dict(v0=0,  v1=7,  s0=1.0,  s1=0.94)),   # 909 底鼓：正拍 + 变体
    ("SnareDrumN",  dict(v0=0,  v1=3,  s0=1.0,  s1=1.06)),   # 军鼓：正拍 + 稍长尾
    ("ClosedHiHat", dict(v0=0,  v1=5,  s0=1.0,  s1=0.92)),   # 闭镲：密集 16 分
    ("OpenHiHat",   dict(v0=0,  v1=2,  s0=1.0,  s1=1.0)),    # 开镲：反拍点缀
    ("Tomi",        dict(v0=0,  v1=4,  s0=1.0,  s1=0.88)),   # 桶鼓：填句
]

# 鼓机音序器图案：17 图案 × 16 步 × 8 轨
# Quadeca 的鼓感 = 「稳」+「抽」：底鼓四踩是骨架，镲在反拍制造不安，
# 军鼓落在 5、13 步（不是标准 4、12），这是他的典型打法。
def drum_pattern():
    """17 图案 × 16 步 × 8 轨。16 步 = 4 拍，每 4 步一小节。"""
    tracks = [[[False] * 8 for _ in range(16)] for _ in range(17)]
    pat = tracks[0]

    def put(step, track):
        if 0 <= step < 16:          # 16 步 = 一圈的步数，越界直接忽略
            pat[step][track] = True

    for bar in range(16):
        beat4 = bar // 4          # 第几小节 0-3
        on = bar % 4               # 小节内第几拍 0-3
        # 底鼓：每拍一击（四踩），第 3 小节起偶加双击推进
        put(bar, 0)
        if beat4 >= 2 and on in (1, 3):
            put(bar + 1, 0)
        # 军鼓：5 与 13 错位重音（不是标准的 4/12）
        put(5, 1)
        put(13, 1)
        if beat4 == 3:
            put(11, 1)
        # 闭镲：8 分音符；第 4 小节加密到 16 分
        for e in range(0, 16, 2):
            put(e, 2)
        if beat4 == 3:
            for e in range(0, 16):
                put(e, 2)
        # 开镲：反拍
        put(7, 3)
        put(15, 3)
        # 桶鼓：后两小节填句
        if beat4 >= 2:
            put(14, 4)
        if beat4 == 3:
            put(10, 4)
    return tracks


# ---------------------------------------------------------------- 主构建
def build():
    clock_src, kb_src, mix_src, drum_src = src_all()

    # ---- 时钟与鼓机音序器 ----
    gnome = copy.deepcopy(find(clock_src, "Gnome"))
    gnome["id"] = 9500000000000001
    gnome["pos"] = [0, 0]
    # Gnome params：完全照抄源机架实测值，不再猜语义。
    # 实测（Final Patch Work / Velour 两处一致）：param0=绝对BPM, param1=0.35(width),
    # param2=0.0, param3=0.0 ← 运行状态靠 data={"running": true}，不是 param
    gnome["params"] = [{"id": 0, "value": 92.0},    # BPM —— Quadeca 常在 85~105
                       {"id": 1, "value": 0.35},    # width（源机架实测值）
                       {"id": 2, "value": 0.0},     # 源机架为 0，不猜
                       {"id": 3, "value": 0.0}]     # 同上
    gnome["data"] = gnome.get("data")        # 原样保留
    # ★★ 李 12:39：「不要直接开播，让我按一个按键再开播」。
    #   Gnome 的运行状态同样在 data.running（实测：不是 param）。
    #   设为 False ⇒ 加载后鼓机不自动滚，李点一下 Gnome 面板的 RUN 才从头走。
    #   ⚠️ 这张机架键盘是直通的（李弹键就有声），只有鼓的自走受影响，
    #      所以停下来只是「鼓没响」，不妨碍他试键盘。
    if isinstance(gnome.get("data"), dict):
        gnome["data"]["running"] = False
    else:
        gnome["data"] = {"running": False}

    seq = copy.deepcopy(find(clock_src, "Sequencer"))
    seq["id"] = 9500000000000002
    seq["pos"] = [20, 0]
    seq["params"] = [q for q in seq.get("params", []) if q["id"] < 151]
    # Sequencer 是唯一必须改 data 的模块（音符表在 data.tracks）。
    # 结构照抄源机架原值，只改 tracks / running / cycling。
    d = dict(seq.get("data") or {})
    src_tracks = d.get("tracks")
    assert src_tracks is not None, "源 Sequencer 没有 data.tracks，无法照抄结构"
    d["tracks"] = drum_pattern()      # 17x16x8，与源同结构
    # ★ 配合 Gnome 一起停下（李 12:39：不要自动开播）
    d["running"] = False
    d["cycling"] = True
    seq["data"] = d

    modules = [gnome, seq]
    cables = []
    cid = [9500000000001000]

    def cab(a, ao, b, bi, color=""):
        cid[0] += 1
        cables.append({"id": cid[0], "outputModuleId": a, "outputId": ao,
                       "inputModuleId": b, "inputId": bi, "color": color})

    cab(gnome["id"], 6, seq["id"], 0)     # 实测接线：Gnome OUT6 → Sequencer IN0

    # ---- 五块鼓机，每块 32 参数全用 ----
    x = 44
    drum_vca_ids = []
    for i, (model, cfg) in enumerate(DRUMS):
        dm = copy.deepcopy(find(drum_src, model))
        dm["id"] = 9500000000000100 + i * 10
        dm["pos"] = [x + i * 14, 0]
        pm = drum_params(cfg["v0"], cfg["s0"], cfg["v1"], cfg["s1"],
                        PARAM_COUNT[model])
        dm["params"] = [{"id": k, "value": float(v)}
                        for k, v in sorted(pm.items())]
        # ⚠️ data 必须原样保留（源机架里就是 None）——
        #    改成 {} 会让模块反序列化失败 ⇒ 加载即崩（2026-10-17 实测）
        dm["data"] = dm.get("data")
        modules.append(dm)
        # Sequencer 8 轨 → 前 5 块鼓的第 0 声部触发口 IN16（实测公式）
        cab(seq["id"], i, dm["id"], 16)
        drum_vca_ids.append((i, dm["id"]))

    out = {"version": "2.4.1", "zoom": 0.6, "gridOffset": [0, 0],
           "modules": modules, "cables": cables}

    # ---- 键盘入口：HostMIDI，复音 8（不设就只有单音）----
    hm = copy.deepcopy(find(kb_src, "HostMIDI"))
    hm["id"] = 9500000000000003
    hm["pos"] = [0, 1]
    # HostMIDI.data 是有明确定义的 dict，这里改字段是安全的（源机架也是 dict）
    hmd = dict(hm.get("data") or {})
    hmd.update({"channels": 8,      # ★ 关键：8 复音，和弦才出得来（PORTS.md §4）
                "inputChannel": 0,  # OMNI：SMK25 通道不统一（PORTS.md §6）
                "smooth": True})
    hm["data"] = hmd
    modules.append(hm)

    # ---- 三层可弹音色：低音 / 和声垫 / 主音 ----
    # 端口（实测）：VCO 音高=IN0；Rings 音高=IN6；ADSR 门=IN4 retrig=IN5；
    #              ADSR OUT0 → VCA IN0(音量)；音频 → VCA IN1
    kb_voices = [
        # (module, params, adsr, level, pan, 说明)
        ("VCO",   {0: 0.0, 1: 1.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.5, 6: 0.0, 7: 0.0},
         {0: 0.004, 1: 0.3, 2: 0.2, 3: 0.2}, 0.7, 0.0, "bass"),
        ("VCO",   {0: 2.0, 1: 1.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.5, 6: 0.0, 7: 0.0},
         {0: 0.45, 1: 0.5, 2: 0.65, 3: 0.85}, 0.4, 0.25, "pad"),
        ("Rings", {0: 0.0, 1: 0.0, 2: 30.0, 3: 0.5, 4: 0.5, 5: 0.6, 6: 0.45,
                   7: 0.0, 8: 0.0, 9: 0.0, 10: 0.2293335497379303, 11: 0.0},
         {0: 0.003, 1: 0.6, 2: 0.05, 3: 0.7}, 0.6, -0.2, "lead"),
    ]
    vca_ids = []
    base_id = 9500000000000300
    for i, (model, pm, am, level, pan, tag) in enumerate(kb_voices):
        if model == "VCO":
            voice = copy.deepcopy(find(kb_src, "VCO"))
        else:
            # Rings 不在已验收机架里 ⇒ 从官方自走模板克隆（字段真实）
            tpl = patchio.read_patch(
                r"C:\Program Files\Cardinal-win64-26.02\Cardinal.lv2"
                r"\resources\patches\examples\falkTX_-_Mini-Arp-Seq.vcv")
            voice = copy.deepcopy(find(tpl, "Rings"))
        voice["id"] = base_id + i * 10
        voice["pos"] = [22 + i * 20, 1]
        voice["params"] = [{"id": k, "value": float(v)}
                           for k, v in sorted(pm.items())]
        voice["data"] = voice.get("data")      # 原样保留，不改结构

        adsr = copy.deepcopy(find(kb_src, "ADSR"))
        adsr["id"] = base_id + i * 10 + 1
        adsr["pos"] = [22 + i * 20 + 9, 1]
        # ADSR 实测 9 个 param（0=Attack 1=Decay 2=Sustain 3=Release，
        # 4..8 未用）。写满 9 个，未用项照抄 0.0。
        ap = {k: float(v) for k, v in am.items()}
        for k in range(9):
            ap.setdefault(k, 0.0)
        adsr["params"] = [{"id": k, "value": ap[k]} for k in range(9)]

        vca = copy.deepcopy(find(kb_src, "VCA-1"))
        vca["id"] = base_id + i * 10 + 2
        vca["pos"] = [22 + i * 20 + 13, 1]
        vca["params"] = [{"id": 0, "value": level}, {"id": 1, "value": pan}]

        modules += [voice, adsr, vca]

        cab(hm["id"], 0, voice["id"], 0 if model == "VCO" else 6)  # OUT0=PITCH
        cab(hm["id"], 1, adsr["id"], 4)     # OUT1=GATE  → ADSR IN4
        cab(hm["id"], 6, adsr["id"], 5)     # OUT6=RETRIG → ADSR IN5（实测口径，别用 OUT1）
        cab(adsr["id"], 0, vca["id"], 0)    # 包络 → 音量
        cab(voice["id"], 0, vca["id"], 1)   # 音频
        vca_ids.append(vca["id"])

    # ---- 混音 ----
    # ★ Mixer 只有 6 路输入(IN0-5) 且**只有 OUT0 一个输出口**
    #   （PORTS.md L194 + 13 份成功机架反推；越界 = 加载即崩）
    #   本机架音源共 7 路（鼓 4 + 键盘 3），单个 Mixer 装不下 ⇒ 两个 Mixer 级联：
    #     Mixer A：鼓 IN0-3 + 键盘 lead/pad IN4-5   → A.OUT0 → B.IN1
    #     Mixer B：键盘 bass IN0                     → B.OUT0 → HostAudio2.IN0
    mx = copy.deepcopy(find(mix_src, "Mixer"))
    mx["id"] = 9500000000000900
    mx["pos"] = [82, 1]
    mx["params"] = [{"id": 0, "value": 0.85}]
    mx["data"] = mx.get("data")        # 原样保留
    modules.append(mx)

    mx2 = copy.deepcopy(find(mix_src, "Mixer"))
    mx2["id"] = 9500000000000902
    mx2["pos"] = [82, 3]
    mx2["params"] = [{"id": 0, "value": 0.85}]
    mx2["data"] = mx2.get("data")
    modules.append(mx2)

    ha = copy.deepcopy(find(kb_src, "HostAudio2"))
    ha["id"] = 9500000000000901
    ha["pos"] = [88, 1]
    ha["data"] = dict(ha.get("data") or {"dcFilter": True})
    modules.append(ha)

    # 鼓的音频 OUT0 → Mixer A 的 IN0-3；键盘 lead/pad → IN4-5；键盘 bass → Mixer B 的 IN0
    for i, (_idx, did) in enumerate(drum_vca_ids):
        cab(did, 0, mx["id"], i)                 # 鼓 4 路 → IN0-3
    for i, vid in enumerate(vca_ids[:2]):        # lead / pad
        cab(vid, 0, mx["id"], 4 + i)             # → IN4, IN5
    cab(vca_ids[2], 0, mx2["id"], 0)             # bass → Mixer B.IN0
    cab(mx["id"], 0, mx2["id"], 1)               # A.OUT0（唯一输出）→ B.IN1
    cab(mx2["id"], 0, ha["id"], 0)               # B.OUT0 → HostAudio2.IN0

    return out, drum_vca_ids, clock_src


def sanitize(patch, path):
    """保存前清洗。

    ★ 元凶：清掉悬空的 leftModuleId / rightModuleId（Rack 模块排序面包屑链）。
      deepcopy 模板后改 id 而没清它们 → 指向已删除模块 → 加载即崩。
    另：空 color 字段也清掉。
    """
    for c in patch.get("cables", []):
        if "color" in c and (c["color"] == "" or c["color"] is None):
            del c["color"]
    live = set(m["id"] for m in patch.get("modules", []))
    for m in patch.get("modules", []):
        for key in ("leftModuleId", "rightModuleId"):
            if m.get(key) is not None and m[key] not in live:
                del m[key]
    patch["path"] = path
    return patch


def main():
    patch, drums, _ = build()
    sanitize(patch, OUT)
    patchio.write_patch(OUT, patch)

    # --- 自检：param 越界 ---
    ok = True
    for m in patch["modules"]:
        cnt = PARAM_COUNT.get(m["model"])
        if cnt is None:
            continue
        bad = [q["id"] for q in m.get("params", []) if q["id"] >= cnt]
        if bad:
            ok = False
            print("  [X] %s param 越界（真实 %d）：%s" % (m["model"], cnt, bad))
    print("quadeca_play  modules=%d cables=%d drums=%d"
          % (len(patch["modules"]), len(patch["cables"]), len(drums)))
    print("param 越界自检:", "通过" if ok else "有问题")

    # --- 端口越界自检（★ 10-17 加载崩溃的真元凶，比 param 越界更隐蔽）---
    import audit_ports
    bad = audit_ports.audit(OUT, verbose=True)
    print("端口越界自检:", "通过" if not bad
          else "❌ 有 %d 处，必须修完再加载" % len(bad))
    print("->", OUT)


if __name__ == "__main__":
    main()
