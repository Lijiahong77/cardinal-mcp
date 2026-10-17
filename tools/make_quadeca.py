# -*- coding: utf-8 -*-
"""
make_quadeca.py — 以 Quadeca 三个时期的风格为参照，生成三张 Cardinal 机架。

设计原则（本项目铁律）：
  * 一律从**已验收机架克隆**：mini_arranger_audition.vcv（编排器+试听口+键盘直通）
    与 Final Patch Work.vcv（ShapeMaster + SurgeXTFXDistortion，李调好的参数原样搬）。
  * 端口编号全部查表/源码核实，不猜（见 cardinal-patch-authoring/references/PORTS.md
    与 AudibleInstruments/voxglitch/Bogaudio 源码）。
  * 排班：行0/行1，x 单调递增，列间距 = 宽 + 2；全部过 layout_patch.analyze 门禁。
  * 顶层 version=2.4.1（与 Cardinal 本机存档一致），模块 version=2.0。
  * zoom=0.75 沿用李的视图；gridOffset=[0,0] 让内容从左上开始。
"""
import copy
import json
import os
import sys

sys.path.insert(0, r"D:\Cardinal\tools")
import patchio  # noqa: E402

BASE = r"D:\Cardinal\patches\mini_arranger_audition.vcv"
FPW = r"D:\Cardinal\patches\Final Patch Work.vcv"
OUTDIR = r"D:\Cardinal\patches"
GAP = 2

SRC_AUD = patchio.read_patch(BASE)
SRC_FPW = patchio.read_patch(FPW)

# ---------------------------------------------------------------- helpers
_cable_id = [900000000]


def cable(out_m, out_p, in_m, in_p, color=None):
    _cable_id[0] += 1
    c = {
        "id": _cable_id[0],
        "outputModuleId": out_m,
        "outputId": out_p,
        "inputModuleId": in_m,
        "inputId": in_p,
    }
    if color:
        c["color"] = color
    return c


def mod(plugin, model, mid, pos, params=None, data=None, version="2.0"):
    m = {"id": mid, "plugin": plugin, "model": model, "version": version,
         "params": [], "data": {}, "pos": pos}
    if params is not None:
        m["params"] = [{"id": i, "value": float(v)} for i, v in enumerate(params)]
    if data is not None:
        m["data"] = data
    return m


def clone(src, model, mid, pos, params=None, data_patch=None, keep_data=True):
    """从已验收机架 deepcopy 一个模块，只改 id/pos，可选覆盖 params / 增量改 data。"""
    m = copy.deepcopy(next(x for x in src["modules"] if x["model"] == model))
    m["id"] = mid
    m["pos"] = list(pos)
    if params is not None:
        m["params"] = [{"id": i, "value": float(v)} for i, v in enumerate(params)]
    if data_patch is not None:
        if not keep_data:
            m["data"] = dict(data_patch)
        else:
            m["data"].update(data_patch)
    return m


def note(step, pitch, length=1, vel=0.5):
    return {"step": step, "length": length, "pitch": pitch, "velocity": vel}


def track(label, notes, mute=False, measures=4):
    return {"label": label, "mute": mute, "measures": measures, "notes": notes}


class Row:
    """行排班器：x 单调递增，间距 = 宽 + GAP。"""

    def __init__(self, row):
        self.row = row
        self.x = 0.0

    def place(self, width):
        pos = [self.x, self.row]
        self.x += width + GAP
        return pos


def save(name, modules, cables, etext_id, etext, zoom=0.75):
    d = {
        "version": "2.4.1",
        "path": os.path.join(OUTDIR, name + ".vcv"),
        "zoom": zoom,
        "gridOffset": [0.0, 0.0],
        "modules": modules,
        "cables": cables,
    }
    # TextEditor 说明牌
    te = next(m for m in modules if m["id"] == etext_id)
    te["data"] = {"filepath": "", "lang": "None", "etext": etext, "width": 26}
    path = os.path.join(OUTDIR, name + ".vcv")
    patchio.write_patch(path, d)
    return path


# ================================================================ PATCH 1
# quadeca_ghostfolk.vcv —《I Didn't Mean To Haunt You》(2022) 鬼魂民谣
#   验证：MiniArranger 8 轨 + 试听口 17/18 首次接线 + 键盘直通 + 物理建模音色
def build_ghostfolk():
    r0, r1 = Row(0), Row(1)
    M, C = [], []

    # ---- row 0: 时钟 / 键盘 / 编排器（+扩展器紧贴）/ Rings 链
    clock = clone(SRC_AUD, "Clocked", 8100000000000001, r0.place(20),
                  params=[75.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                          0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    midi = clone(SRC_AUD, "HostMIDI", 8100000000000002, r0.place(9))  # channels=1

    # T1 尼龙弦分解（A 小调 -> F），T2 钢琴长音，T3 鬼魂 drone，T4 留白
    t1 = [note(0, 45, vel=0.55), note(2, 52, vel=0.45), note(4, 57, vel=0.60),
          note(6, 60, vel=0.40), note(8, 64, vel=0.65), note(10, 60, vel=0.45),
          note(12, 57, vel=0.50), note(14, 52, vel=0.40),
          note(16, 41, vel=0.55), note(18, 48, vel=0.45), note(20, 53, vel=0.60),
          note(22, 57, vel=0.40), note(24, 60, vel=0.65), note(26, 57, vel=0.45),
          note(28, 53, vel=0.50), note(30, 48, vel=0.40)]
    t2 = [note(0, 69, length=8, vel=0.50), note(8, 72, length=6, vel=0.45),
          note(16, 65, length=8, vel=0.50), note(24, 69, length=6, vel=0.45)]
    t3 = [note(0, 33, length=16, vel=0.40)]
    e1 = [note(0, 33, length=6, vel=0.60), note(8, 36, length=6, vel=0.50),
          note(16, 29, length=6, vel=0.60), note(24, 29, length=6, vel=0.50)]
    arr_data = {
        "arranger": {
            "editTrack": 1, "stepsPerQuarter": 4.0,
            "tracks": [track("Track 1", t1), track("Track 2", t2),
                       track("Track 3", t3), track("Track 4", [])],
        }
    }
    exp_data = {
        "arranger": {
            "editTrack": 0, "stepsPerQuarter": 4.0,
            "tracks": [track("E1", e1), track("E2", []), track("E3", []),
                       track("E4", [])],
        }
    }
    arr = clone(SRC_AUD, "Starsea-MiniArranger", 8100000000000003, r0.place(40),
                data_patch=arr_data)
    exp = clone(SRC_AUD, "Starsea-MiniArrangerExpander", 8100000000000004,
                r0.place(24), data_patch=exp_data)

    rings = mod("AudibleInstruments", "Rings", 8100000000000005, r0.place(14),
                params=[0, 2, 30.0, 0.5, 0.6, 0.4, 0.5, 0, 0, 0, 0, 0])
    vca_r = mod("Fundamental", "VCA-1", 8100000000000006, r0.place(3))
    # 说明牌放行0 末尾：行1 已 142 格（TextEditor 26 格会顶出 1600px 窗口）
    te = mod("Cardinal", "TextEditor", 8100000000000020, r0.place(26))
    M += [clock, midi, arr, exp, rings, vca_r, te]

    # ---- row 1: Elements 链 / 试听链 / E1 链 / Mixer / Plateau / 输出 / 说明
    elements = mod("AudibleInstruments", "Elements", 8100000000000007, r1.place(34),
                   params=[0.6, 0.0, 0.0, 0.7, 0.0, 0.0, 0.0, 0.5, 0.6, 0.5,
                           0.55, 0.5, 0.5, 0.5, 0.5, 0.5, 0.3,
                           0, 0, 0, 0, 0, 0, 0, 0, 0, 0.0])
    vca_e = mod("Fundamental", "VCA-1", 8100000000000008, r1.place(3))
    vco_a = mod("Fundamental", "VCO", 8100000000000009, r1.place(9))
    vcf_a = mod("Fundamental", "VCF", 8100000000000010, r1.place(7),
                params=[0.35, 0.0, 0.30, 0.60, 0.30, 0.30, 0.0])
    adsr_a = mod("Fundamental", "ADSR", 8100000000000011, r1.place(9),
                 params=[0.40, 0.60, 0.40, 0.90, 0, 0, 0, 0, 0])
    vca_a = mod("Fundamental", "VCA-1", 8100000000000012, r1.place(3))
    vco_b = mod("Fundamental", "VCO", 8100000000000013, r1.place(9))
    vcf_b = mod("Fundamental", "VCF", 8100000000000014, r1.place(7),
                params=[0.30, 0.0, 0.25, 0.55, 0.25, 0.25, 0.0])
    adsr_b = mod("Fundamental", "ADSR", 8100000000000015, r1.place(9),
                 params=[0.10, 0.50, 0.50, 0.70, 0, 0, 0, 0, 0])
    vca_b = mod("Fundamental", "VCA-1", 8100000000000016, r1.place(3))
    mixer = mod("Fundamental", "Mixer", 8100000000000017, r1.place(3),
                params=[0.85, 0, 0, 0, 0, 0])
    plateau = mod("Valley", "Plateau", 8100000000000018, r1.place(12),
                  params=[0.90, 0.45, 0.030, 10.0, 10.0, 0.60, 9.5, 0.72,
                          10.0, 10.0, 0.25, 0.50, 1.20])
    audio = clone(SRC_AUD, "HostAudio2", 8100000000000019, r1.place(8))
    M += [elements, vca_e, vco_a, vcf_a, adsr_a, vca_a, vco_b, vcf_b,
          adsr_b, vca_b, mixer, plateau, audio]

    # ---- 接线
    C.append(cable(clock["id"], 1, arr["id"], 0))            # 时钟 -> 编排器
    C.append(cable(midi["id"], 0, arr["id"], 4))             # 键盘 voct
    C.append(cable(midi["id"], 1, arr["id"], 5))             # 键盘 gate
    C.append(cable(midi["id"], 2, arr["id"], 7))             # 键盘 velocity
    C.append(cable(arr["id"], 5, rings["id"], 6))            # T1 voct -> Rings pitch
    C.append(cable(arr["id"], 6, rings["id"], 5))            # T1 gate -> Rings strum
    C.append(cable(arr["id"], 8, elements["id"], 0))         # T2 voct -> Elements note
    C.append(cable(arr["id"], 9, elements["id"], 2))         # T2 gate -> Elements gate
    C.append(cable(arr["id"], 17, vco_a["id"], 0))           # 试听口 -> VCO A
    C.append(cable(arr["id"], 18, adsr_a["id"], 4))          # 试听 gate -> ADSR A
    C.append(cable(arr["id"], 18, adsr_a["id"], 5))          # 试听 gate -> retrig
    C.append(cable(exp["id"], 0, vco_b["id"], 0))            # E1 voct -> VCO B
    C.append(cable(exp["id"], 1, adsr_b["id"], 4))           # E1 gate -> ADSR B
    C.append(cable(exp["id"], 1, adsr_b["id"], 5))           # E1 gate -> retrig
    C.append(cable(rings["id"], 0, vca_r["id"], 1))          # Rings odd -> VCA
    C.append(cable(vca_r["id"], 0, mixer["id"], 0))
    C.append(cable(elements["id"], 1, vca_e["id"], 1))       # Elements main -> VCA
    C.append(cable(vca_e["id"], 0, mixer["id"], 1))
    C.append(cable(vco_a["id"], 2, vcf_a["id"], 3))          # SAW -> VCF
    C.append(cable(adsr_a["id"], 0, vcf_a["id"], 0))         # 滤波包络
    C.append(cable(adsr_a["id"], 0, vca_a["id"], 0))         # 音量包络
    C.append(cable(vcf_a["id"], 0, vca_a["id"], 1))
    C.append(cable(vca_a["id"], 0, mixer["id"], 2))
    C.append(cable(vco_b["id"], 2, vcf_b["id"], 3))
    C.append(cable(adsr_b["id"], 0, vcf_b["id"], 0))
    C.append(cable(adsr_b["id"], 0, vca_b["id"], 0))
    C.append(cable(vcf_b["id"], 0, vca_b["id"], 1))
    C.append(cable(vca_b["id"], 0, mixer["id"], 3))
    C.append(cable(mixer["id"], 0, plateau["id"], 0))
    C.append(cable(mixer["id"], 0, plateau["id"], 1))
    C.append(cable(plateau["id"], 0, audio["id"], 0))
    C.append(cable(plateau["id"], 1, audio["id"], 1))

    etext = """QUADECA "GHOST FOLK"  (IDMTHY, 2022)
====================================
Nylon-string guitar + ghost piano at
75 BPM. MiniArranger 8 tracks drive two
physical-modeling voices; AUDITION
ports (17/18) feed a 3rd chain so ONE
VCO plays ANY track (turn TRACK).

ROW 0  Clocked | HostMIDI | MiniArranger
       | Expander | Rings | VCA
ROW 1  Elements | VCO chain (AUDITION)
       | VCO chain (Expander E1)
       | Mixer | Plateau | HostAudio2

HOW TO PLAY
- TRACK 1 + play keys = nylon guitar
- TRACK 2 + play keys = ghost piano
- TRACK 3/4 + keys = audition VCO
- Expander E1 = bass line, always on
- RUN = arranger plays the pattern

TUNING
- Rings  FREQUENCY / STRUCTURE /
  BRIGHTNESS = string character
- Elements STRIKE / MALLET / DAMPING
  - Plateau DECAY 0.72 = afterlife hall
  (WET 0.45 = how deep the ghost is)
"""
    # zoom 0.68: row0 now spans 148 cells -> 148*15*0.68 = 1510px < 1600px window
    return save("quadeca_ghostfolk", M, C, te["id"], etext, zoom=0.68)


# ================================================================ PATCH 2
# quadeca_scrapyard.vcv —《Scrapyard》(2024) 废料场故障
#   验证：SamplerX8 8 槽触发 + Clouds 颗粒再合成 + 反律动编排 + 键盘直通敲采样
def build_scrapyard():
    r0, r1 = Row(0), Row(1)
    M, C = [], []

    clock = clone(SRC_AUD, "Clocked", 8200000000000001, r0.place(20),
                  params=[92.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                          0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    midi = clone(SRC_AUD, "HostMIDI", 8200000000000002, r0.place(9))

    # 反律动鼓组：该静的地方静音，该密的地方错位
    t1 = [note(0, 36, vel=0.95), note(3, 36, vel=0.60), note(6, 36, vel=0.90),
          note(10, 36, vel=0.55), note(13, 36, vel=0.70)]
    t2 = [note(4, 38, vel=0.85), note(12, 38, vel=0.90), note(14, 38, vel=0.40)]
    t3 = [note(2, 42, vel=0.50), note(3, 42, vel=0.60), note(6, 42, vel=0.45),
          note(7, 42, vel=0.55), note(8, 42, vel=0.50), note(11, 42, vel=0.60),
          note(13, 42, vel=0.50), note(14, 42, vel=0.65), note(15, 42, vel=0.40)]
    t4 = [note(12, 39, vel=0.80)]
    e1 = [note(0, 33, length=3, vel=0.90), note(6, 33, length=2, vel=0.70),
          note(10, 33, length=3, vel=0.85)]
    e2 = [note(4, 60, length=2, vel=0.60), note(11, 62, length=1, vel=0.50),
          note(14, 64, length=2, vel=0.55)]
    e3 = [note(6, 57, length=2, vel=0.70), note(13, 60, length=2, vel=0.65)]
    e4 = [note(8, 29, length=3, vel=0.85), note(12, 29, length=2, vel=0.70)]
    arr_data = {"arranger": {"editTrack": 1, "stepsPerQuarter": 4.0,
                             "tracks": [track("Track 1", t1), track("Track 2", t2),
                                        track("Track 3", t3), track("Track 4", t4)]}}
    exp_data = {"arranger": {"editTrack": 0, "stepsPerQuarter": 4.0,
                             "tracks": [track("E1", e1), track("E2", e2),
                                        track("E3", e3), track("E4", e4)]}}
    arr = clone(SRC_AUD, "Starsea-MiniArranger", 8200000000000003, r0.place(40),
                data_patch=arr_data)
    exp = clone(SRC_AUD, "Starsea-MiniArrangerExpander", 8200000000000004,
                r0.place(24), data_patch=exp_data)

    # 8 槽：kick / snare / closed hat / clap / bassA1 / pluckC4 / stabAm / bassF1
    sdata = {f"loaded_sample_path_{i+1}": p for i, p in enumerate([
        r"D:\Cardinal\samples\kick.wav", r"D:\Cardinal\samples\snare.wav",
        r"D:\Cardinal\samples\hihat_closed.wav", r"D:\Cardinal\samples\clap.wav",
        r"D:\Cardinal\samples\bass_A1.wav", r"D:\Cardinal\samples\pluck_C4.wav",
        r"D:\Cardinal\samples\stab_Am.wav", r"D:\Cardinal\samples\bass_F1.wav"])}
    sx8 = mod("voxglitch", "samplerx8", 8200000000000005, r0.place(28),
              params=[1.0, 0.90, 0.70, 0.80, 0.90, 0.80, 0.70, 0.90], data=sdata)
    M += [clock, midi, arr, exp, sx8]

    # row 1: Clouds 颗粒层（吃槽7 stab 单输出）/ VCF / Mixer / Plateau / 输出 / 说明
    clouds = mod("AudibleInstruments", "Clouds", 8200000000000006, r1.place(18),
                 params=[0.0, 0.0, 0.0,          # FREEZE / MODE=granular / LOAD
                         0.35, 0.40, 0.00,       # POSITION / SIZE / PITCH
                         0.60, 0.55, 0.50,       # IN_GAIN / DENSITY / TEXTURE
                         1.00, 0.70, 0.35, 0.20])  # BLEND / SPREAD / FB / REVERB
    vcf = mod("Fundamental", "VCF", 8200000000000007, r1.place(7),
              params=[0.45, 0.0, 0.25, 0.0, 0.20, 0.0, 0.0])
    mixer = mod("Fundamental", "Mixer", 8200000000000008, r1.place(3),
                params=[0.90, 0, 0, 0, 0, 0])
    plateau = mod("Valley", "Plateau", 8200000000000009, r1.place(12),
                  params=[0.90, 0.35, 0.025, 10.0, 10.0, 0.55, 9.0, 0.62,
                          10.0, 10.0, 0.30, 0.50, 1.00])
    audio = clone(SRC_AUD, "HostAudio2", 8200000000000010, r1.place(8))
    te = mod("Cardinal", "TextEditor", 8200000000000011, r1.place(26))
    M += [clouds, vcf, mixer, plateau, audio, te]

    # ---- 接线：8 轨 gate -> 8 个采样槽触发
    C.append(cable(clock["id"], 1, arr["id"], 0))
    C.append(cable(midi["id"], 0, arr["id"], 4))
    C.append(cable(midi["id"], 1, arr["id"], 5))
    C.append(cable(midi["id"], 2, arr["id"], 7))
    for src, dst, slot in [(arr, sx8, 0), (arr, sx8, 1), (arr, sx8, 2),
                           (arr, sx8, 3)]:
        gate_out = 6 + slot * 3           # T1..T4 gate
        C.append(cable(src["id"], gate_out, dst["id"], slot))
    for i in range(4):                    # E1..E4 gate
        C.append(cable(exp["id"], 1 + i * 3, sx8["id"], 4 + i))
    # E3（stab 轨）同时喂 Clouds：voct->PITCH, gate->TRIG, 槽7左输出->IN_L
    C.append(cable(exp["id"], 6, clouds["id"], 4))     # E3 voct -> grain pitch
    C.append(cable(exp["id"], 7, clouds["id"], 1))     # E3 gate -> grain trig
    C.append(cable(sx8["id"], 6, clouds["id"], 6))     # slot7 L -> Clouds IN_L
    C.append(cable(sx8["id"], 16, vcf["id"], 3))       # 混音 -> VCF
    C.append(cable(vcf["id"], 0, mixer["id"], 0))
    C.append(cable(clouds["id"], 0, mixer["id"], 1))
    C.append(cable(clouds["id"], 1, mixer["id"], 2))
    C.append(cable(mixer["id"], 0, plateau["id"], 0))
    C.append(cable(mixer["id"], 0, plateau["id"], 1))
    C.append(cable(plateau["id"], 0, audio["id"], 0))
    C.append(cable(plateau["id"], 1, audio["id"], 1))

    etext = """QUADECA "SCRAPYARD"  (2024)
============================
Anti-groove drum collage from 8 wav
slots. Beats sit OFF the grid: rests
where hits are expected. Clouds
granulates slot 7 (stab) live, pitched
by expander track E3.

ROW 0  Clocked | HostMIDI | MiniArranger
       | Expander | SamplerX8
ROW 1  Clouds | VCF | Mixer | Plateau
       | HostAudio2

SLOTS 1 kick 2 snare 3 closed hat
      4 clap 5 bass A1 6 pluck C4
      7 stab Am 8 bass F1

HOW TO PLAY
- RUN = the collage plays itself
- Keys = live overdub on edit track
  (edit 1..4 = drums, expander
  tracks = bass/pluck/stab)
- TRACK on expander edits E1..E4

TUNING
- SamplerX8 slot VOLUME knobs = mix
- Clouds DENSITY/TEXTURE/BLEND =
  how far the scrap gets shredded
  (BLEND 1.0 = pure grains)
"""
    return save("quadeca_scrapyard", M, C, te["id"], etext)


# ================================================================ PATCH 3
# quadeca_life1.vcv —《Life 1》(2026) 数字焦虑
#   验证：复音键盘链 + Unison 6 声部 supersaw + ShapeMaster 混响自动化
#         + SurgeFX Overdrive 失真 + FMOp 电钢对比层
def build_life1():
    r0, r1 = Row(0), Row(1)
    M, C = [], []

    midi = clone(SRC_AUD, "HostMIDI", 8300000000000001, r0.place(9),
                 data_patch={"channels": 8})            # 复音 8 声部
    unison = mod("Bogaudio", "Bogaudio-Unison", 8300000000000002, r0.place(3),
                 params=[6.0, 15.0])                    # 6 声部 / 15 cents
    vco = mod("Fundamental", "VCO", 8300000000000003, r0.place(9))
    vcf = mod("Fundamental", "VCF", 8300000000000004, r0.place(7),
              params=[0.30, 0.0, 0.35, 0.60, 0.40, 0.50, 0.0])
    adsr = mod("Fundamental", "ADSR", 8300000000000005, r0.place(9),
               params=[0.01, 0.50, 0.25, 0.70, 0, 0, 0, 0, 0])
    vca1 = mod("Fundamental", "VCA-1", 8300000000000006, r0.place(3))
    sum_ = mod("Fundamental", "Sum", 8300000000000007, r0.place(3), params=[0.5])
    fmop = mod("Bogaudio", "Bogaudio-FMOp", 8300000000000008, r0.place(10),
               params=[0.50, 0.00, 0.01, 0.35, 0.15, 0.50,
                       0.45, 0.15, 0.60, 1.00, 0.00, 0.00])
    vca2 = mod("Fundamental", "VCA-1", 8300000000000009, r0.place(3))
    dist = clone(SRC_FPW, "SurgeXTFXDistortion", 8300000000000010,
                 r0.place(12))                          # Overdrive 预设原样
    mixer = mod("Fundamental", "Mixer", 8300000000000011, r0.place(3),
                params=[0.90, 0, 0, 0, 0, 0])
    plateau = mod("Valley", "Plateau", 8300000000000012, r0.place(12),
                  params=[0.85, 0.30, 0.020, 10.0, 10.0, 0.55, 9.0, 0.62,
                          10.0, 10.0, 0.30, 0.50, 1.00])
    audio = clone(SRC_AUD, "HostAudio2", 8300000000000013, r0.place(8))
    M += [midi, unison, vco, vcf, adsr, vca1, sum_, fmop, vca2, dist, mixer,
          plateau, audio]

    # row 1: ShapeMaster（李调好的自动化曲线原样搬）+ 说明
    shape = clone(SRC_FPW, "ShapeMaster", 8300000000000014, r1.place(38))
    te = mod("Cardinal", "TextEditor", 8300000000000015, r1.place(26))
    M += [shape, te]

    # ---- 接线
    C.append(cable(midi["id"], 0, unison["id"], 1))     # pitch -> unison
    C.append(cable(midi["id"], 1, unison["id"], 2))     # gate  -> unison
    C.append(cable(midi["id"], 0, fmop["id"], 4))       # pitch -> FMOp
    C.append(cable(midi["id"], 1, fmop["id"], 5))       # gate  -> FMOp
    C.append(cable(midi["id"], 2, vcf["id"], 1))        # velocity -> resonance CV
    C.append(cable(midi["id"], 6, adsr["id"], 5))       # retrig
    C.append(cable(unison["id"], 0, vco["id"], 0))      # detuned stack -> VCO
    C.append(cable(unison["id"], 1, adsr["id"], 4))     # stack gate -> ADSR
    C.append(cable(vco["id"], 2, vcf["id"], 3))         # SAW -> VCF
    C.append(cable(adsr["id"], 0, vcf["id"], 0))        # 滤波包络
    C.append(cable(adsr["id"], 0, vca1["id"], 0))       # 音量包络
    C.append(cable(adsr["id"], 0, shape["id"], 17))     # 按键重同步自动化
    C.append(cable(vcf["id"], 0, vca1["id"], 1))
    C.append(cable(vca1["id"], 0, sum_["id"], 0))
    C.append(cable(sum_["id"], 0, dist["id"], 0))       # saw stack -> overdrive L
    C.append(cable(fmop["id"], 0, vca2["id"], 1))       # e-piano -> VCA
    C.append(cable(vca2["id"], 0, dist["id"], 1))       # e-piano -> overdrive R
    C.append(cable(dist["id"], 0, mixer["id"], 0))
    C.append(cable(dist["id"], 1, mixer["id"], 1))
    C.append(cable(shape["id"], 9, plateau["id"], 3))   # ch2 CV -> reverb wet CV
    C.append(cable(mixer["id"], 0, plateau["id"], 0))
    C.append(cable(mixer["id"], 0, plateau["id"], 1))
    C.append(cable(plateau["id"], 0, audio["id"], 0))
    C.append(cable(plateau["id"], 1, audio["id"], 1))

    etext = """QUADECA "LIFE 1"  (2026)
========================
Hyperpop saw stack x6 detuned, FM
e-piano counter-layer, Overdrive,
and a ShapeMaster curve sweeping the
reverb wet. Press a key = the curve
re-triggers from the top.

ROW 0  HostMIDI | Unison | VCO | VCF
       | ADSR | VCA | Sum | FMOp | VCA
       | Distortion | Mixer | Plateau
       | HostAudio2
ROW 1  ShapeMaster | TextEditor

HOW TO PLAY
- Keys = 6-voice detuned saw stack
- Hit harder = more filter resonance
  (velocity -> VCF reso CV)
- FMOp e-piano rides along; its VCA
  knob = e-piano level vs saw
- Watch the Plateau WET knob move by
  itself: that is ShapeMaster ch2

TUNING
- Unison CHANNELS 6 / DETUNE 15c
- Distortion DRIVE 0.74 (Overdrive)
- ShapeMaster ch2 speed on its
  FREQ knob; ADSR retriggers it
"""
    return save("quadeca_life1", M, C, te["id"], etext)


if __name__ == "__main__":
    for fn in (build_ghostfolk, build_scrapyard, build_life1):
        p = fn()
        d = patchio.read_patch(p)
        print(f"{os.path.basename(p):<28} modules={len(d['modules']):<3} "
              f"cables={len(d['cables']):<3} bytes={os.path.getsize(p)}")
