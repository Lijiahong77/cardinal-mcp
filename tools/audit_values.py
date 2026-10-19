# -*- coding: utf-8 -*-
r"""audit_values.py —— 🔴 数值护栏审计器（**感知边界**，不是接口越界）

★ 为什么要有这个（2026-10-19，依据 `后期工程指南.md`）
  指南把历史翻车归为「参数幻觉：VCO 频率被写成 20,000 Hz，不可闻」。
  在 Cardinal 里复现这个假设时**发现指南的前提不成立**，本脚本的判据据此重写：

  ┌─ 实测结论（6 份李确认能出声的机架）────────────────────────────┐
  │ Fundamental/VCO      Frequency   -45.9 … +20.8   = **半音**      │
  │ Fundamental/VCF      Cutoff       0.42 … 0.67   = **归一化**    │
  │ Fundamental/ADSR     Attack        0.006 … 0.70  = **归一化**    │
  │ Valley/Plateau       Decay         0.121 / 0.62  = **归一化**    │
  │ Clocked.Master clock  96/100/120/145            = **绝对 BPM**  │
  └─────────────────────────────────────────────────────────────────┘
  ⇒ Cardinal 的旋钮**绝大多数存归一化值，不存 Hz/ms**。
    写 20000 进去不是「不可闻」，而是**被 clamp 或直接崩**
    （与 MEMORY「Clocked 写 0.463 会崩」是同一类量纲错误）。
  ⇒ 所以「VCO 20–4000 Hz」这种绝对范围表**在这里会产生成片误报**。
    一个天天误报的审计器 = 没有审计器。本脚本因此按量纲分两套判据：
      · 绝对量纲（目前只有 Clocked.BPM）→ 判真实感知范围
      · 归一化旋钮 → 只判 0..1 与语义合理区间
      · **MIDI 音符** → 这是唯一真·绝对音高，感知边界表在这里完全适用

★ 与 audit_ports.py 的分工（两个都必须过，少一个就放过永哑机架）：
    audit_ports.py  → 接口越界：口编号超出模块真实口数（会**崩**）
    audit_values.py → 数值越界：数值超出可感知/可写入范围（**哑**或**崩**）

★ 三层判据：
    L1  硬否决：MIDI 音符 < 24（频率 < 20 Hz，人耳下限）
    L2a 绝对量纲参数的真实感知范围（当前只有 BPM）
    L2b 归一化参数的 0..1 与语义合理区间
    L3  与 paramlib 从**源码**解析出的 min/max 交叉核对，抓量纲写错
    L1 命中 ⇒ 退出码 1（该打回）；L2/L3 ⇒ 仅告警

用法:
    python audit_values.py <file.vcv> [更多文件...]
    python audit_values.py --all          # 审计 patches/ 下所有 .vcv
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patchio  # noqa: E402

try:
    import paramlib  # 可选：拿不到源码字典就退化成只跑 L1/L2
except Exception:  # pragma: no cover
    paramlib = None


# ─────────────────────────────────────────────────────────────
# ★★★ 量纲铁律（10-19 实测得出，**推翻指南里的原始假设**）★★★
#
# 指南 §3 假设「VCO 频率参数 = 20–4000 Hz，越界即打回」。
# 在 Cardinal 里**这个假设是错的** —— 实测 6 份李确认能出声的机架：
#
#   模块                实际存的值                       真实量纲
#   ────────────────────────────────────────────────────────────────
#   Fundamental/VCO     -45.9 … +20.8                    **半音（音高偏移）**
#   Fundamental/VCF      0.42 … 0.67                      **归一化 0..1**
#   Fundamental/ADSR    0.006 … 0.70                     **归一化 0..1**
#   Valley/Plateau      0.121 / 0.62                     **归一化 0..1**
#   Clocked.Master clock 96 / 100 / 120 / 145            **绝对 BPM** ✅唯一例外
#
# ⇒ **绝大多数模块根本不存 Hz/ms**。写 20000 进去不是「不可闻」，
#   而是**被 clamp 或直接崩**（与 MEMORY 里「Clocked 写 0.463 会崩」同类）。
# ⇒ 所以本审计器的策略是：
#     · 绝对量纲参数（目前只有 Clocked.BPM）→ 用真实 Hz/ms 范围判
#     · 归一化参数 → 只能判 0..1 越界 + 语义合理性，**不能**把归一化值
#       当 Hz 去套感知边界表（那会产生成片误报，审计器直接失去可信度）
#     · MIDI 音符 → 这是**真·绝对音高**，感知边界表在这里完全适用
#
# ⚠️ 换新模块时先跑 `tools/_value_scale.py` 确认量纲，再往 SCALE 里登记。
# ─────────────────────────────────────────────────────────────

# 量纲表：(插件, 模型, 参数名) -> "abs:<单位>" | "norm"
# ★ 参数名用**完全相等**匹配（不是子串）—— 子串会把
#   "Frequency" 匹配上 "Frequency modulation"、
#   "Pulse width" 匹配上 "Pulse width modulation"，判据全串位。
# 默认 "norm"，只有实证为绝对量的才写 "abs"。
PARAM_SCALE = {
    ("ImpromptuModular", "Clocked", "Master clock"): "abs:BPM",
    # 🔴 Bogaudio-VCO.Frequency：**八度**，不是 Hz，尽管 paramlib 标着 " Hz"。
    #   源码 VCOFrequencyParamQuantity（vco_base.cpp:12）+ FrequencyParamQuantity
    #   （param_quantities.cpp:56）：`displayHz = 2^(value + offset) * 440`
    #   offset = -7 当 Slow mode 打开（vco_base.hpp:54 `slowModeOffset = -7.0f`）
    #   ⇒ 换算：value 0 = 440Hz；value -3 = 55Hz；value 6 = 28160Hz
    #   ⚠️ 实证 life1：Bogaudio-VCO Frequency=6.0 + Slow=1.0 ⇒ 2^(6-7)*440
    #      = **220 Hz (A3)**，正是电钢该有的音高。**不看 Slow 就误判成 28kHz。**
    ("Bogaudio", "Bogaudio-VCO", "Frequency"): "oct:Bogaudio-VCO",
}
DEFAULT_SCALE = "norm"

# ─────────────────────────────────────────────────────────────
# L2：范围表**按量纲分两套**，绝不混用
#   NORM_RANGES：归一化 0..1 参数（绝大多数）—— 只判 0..1 越界
#   ABS_RANGES ：绝对量纲参数（目前只有 BPM）—— 判真实感知范围
#
# ★ 参数名一律用**完全相等**匹配（实测踩坑：子串匹配导致
#   "frequency" 规则套到 "Frequency modulation" 上，一个参数报两条）
# ─────────────────────────────────────────────────────────────

# 归一化参数的**语义合理区间**。
# lo/hi 取自「李确认过能出声」的机架实测值再放宽一档，不是拍脑袋。
NORM_RANGES = [
    # (插件 or None, 模型 or None, 参数名[精确], lo, hi, 说明)
    (None, "VCO", "Frequency", -72.0, 72.0,
     "音高偏移半音数（1V/oct 体系）；±72 = 六个八度"),
    (None, "VCO", "Frequency modulation", 0.0, 1.0, "FM 深度"),
    (None, "VCO", "Pulse width", 0.01, 0.99, "脉宽"),
    (None, "VCF", "Cutoff frequency", 0.0, 1.0,
     "归一化截止频率；<0.1 几乎全滤，>0.95 等于没滤"),
    (None, "VCF", "Resonance", 0.0, 1.0, "谐振"),
    (None, "VCF", "Drive", -1.0, 1.0, "驱动"),
    (None, "ADSR", "Attack", 0.0, 1.0,
     "归一化起音；=0 即刻爆音（削波风险）"),
    (None, "ADSR", "Decay", 0.0, 1.0, "归一化衰减"),
    (None, "ADSR", "Sustain", 0.0, 1.0, "归一化延音"),
    (None, "ADSR", "Release", 0.0, 1.0, "归一化释音"),
    (None, "Plateau", "Decay", 0.0, 1.0, "归一化混响时间"),
    (None, "Plateau", "Size", 0.0, 1.0, "混响尺寸"),
    (None, "Plateau", "Wet level", 0.0, 1.0, "湿声比"),
    (None, "Plateau", "Dry level", 0.0, 1.0, "干声比"),
    (None, "MixMasterJr", "level", 0.0, 1.0, "通道电平"),
    (None, "MixMasterJr", "pan", 0.0, 1.0, "声像"),
    (None, "Mixer", "Level", 0.0, 1.0, "通道电平"),
    (None, "HostAudio2", "Level", 0.0, 1.0, "输出电平（1.0 = 0dB 附近）"),
]

# 绝对量纲参数的真实感知范围
ABS_RANGES = [
    # (插件, 模型, 参数名, lo, hi, 单位, 说明)
    ("ImpromptuModular", "Clocked", "Master clock", 20.0, 300.0, "BPM",
     "绝对 BPM。★ 写 0.463（归一化值）会崩 —— 这是量纲错误不是速度错误"),
    # Bogaudio-VCO 的 Frequency 单独在 L2c 里按「八度 + Slow 偏移」处理，
    # 因为它的实际 Hz 依赖同一模块的 Slow mode 开关，静态换算必须联读。
]

# L2c：八度量纲参数 —— 存的是八度，但要换算成 Hz 才能套感知边界
#  (插件, 模型, 参数名, 同模块内「Slow mode 按钮」的 param_id, 单位说明)
OCTAVE_PARAMS = [
    ("Bogaudio", "Bogaudio-VCO", "Frequency", 2, "Bogaudio-VCO"),
]
# 八度 → Hz 的合法区间（-3..6 是源码 configParam 的范围）
OCT_LO_HZ, OCT_HI_HZ = 20.0, 12000.0

# ─────────────────────────────────────────────────────────────
# 感知边界（MIDI 音符是**唯一真·绝对音高**，这里完全适用）
# ─────────────────────────────────────────────────────────────
HEARING_MIN_HZ = 20.0          # 人耳绝对下限
MIDI_FLOOR = 24                 # C-1；低于此 ⇒ 频率 < 20 Hz
MIDI_CEIL = 108                 # C-8

# 参数名里含这些词 ⇒ 是按钮/开关/模式选择，**不做数值范围审计**
# （实测：`Bpm mode prev/next` 被 "bpm" 规则误判成 BPM 值）
BUTTON_WORDS = ("mode", "prev", "next", "run", "reset", "enable", "disable",
                "gate", "trigger", "button", "switch", "toggle", "mute", "solo",
                "phase", "div", "mul", "link", "record", "rec ", "play")

# 采样播放类：音高已烘焙进采样，patch 里没有音高参数
SAMPLE_PLAYERS = ("samplerx8", "audiofile", "sampleplayer", "wstd-player")

# MIDI 音符类模块（**唯一真·绝对音高**，感知边界表在这里适用）
MIDI_NOTE_MODELS = ("pianoroll", "hostmidi", "miniarranger", "sequencer")


def nm(m):
    """'plugin/model' 字符串；plugin 可能是 dict（Cardinal 存盘后的形态）。"""
    p = m.get("plugin")
    slug = p if isinstance(p, str) else (p or {}).get("slug", "")
    return "%s/%s" % (slug, m.get("model", ""))


def iter_params(params):
    """把 module.params 归一成 (param_id, value) 迭代器。

    ★ Cardinal 的 .vcv 里 params 有**两种形态**（10-19 实测）：
        手写 JSON  : [{"id": 0, "value": 96.0}, ...]        ← 列表
        Cardinal 存盘: 有时写成 {"0": 96.0, ...} 或 [{"id":..}] 视版本而定
      写死一种就会在另一种机架上抛 `'list' object has no attribute 'items'`。
    """
    if params is None:
        return
    if isinstance(params, dict):
        for k, v in params.items():
            try:
                yield int(k), v
            except (TypeError, ValueError):
                continue
        return
    if isinstance(params, list):
        for i, item in enumerate(params):
            if isinstance(item, dict):
                pid = item.get("id", i)
                val = item.get("value")
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                pid, val = item[0], item[1]
            else:
                pid, val = i, item
            try:
                yield int(pid), val
            except (TypeError, ValueError):
                continue


def pname(paramlib, plugin, model, pid):
    if paramlib is None:
        return None
    try:
        return paramlib.name_of(plugin, model, pid)
    except Exception:
        return None


def _match(plug, mdl, key, plugin, model, pname_lower):
    """规则匹配：插件/模型子串 + **参数名精确相等**。

    ★ 为什么必须精确相等而不是子串（10-19 实测踩坑）：
      子串匹配下 `"frequency"` 会套到 `Frequency modulation` 上、
      `"pulse width"` 会套到 `Pulse width modulation` 上，
      一个参数报出两条互不相干的判据 ⇒ 判据失效。
      唯一例外：MixMasterJr 的名字带轨号前缀（`-01-: level`），
      所以额外允许「以 `: key` 结尾」。
    """
    if plug is not None and plug.lower() not in plugin.lower():
        return False
    if mdl is not None and mdl.lower() not in model.lower():
        return False
    # ★ key 也要 lower()：表里写的是 paramlib 的原始大小写（`Master clock`），
    #   而传进来的是已小写的名字。不统一 ⇒ 规则**永远不命中**（实测踩过，
    #   症状是「BPM 规则配了但一条都不报」）。
    k = key.lower()
    return pname_lower == k or pname_lower.endswith(": " + k)


def find_norm_rules(plugin, model, pname_lower):
    if any(w in pname_lower for w in BUTTON_WORDS):
        return []
    return [(lo, hi, note)
            for plug, mdl, key, lo, hi, note in NORM_RANGES
            if _match(plug, mdl, key, plugin, model, pname_lower)]


def find_abs_rules(plugin, model, pname_lower):
    if any(w in pname_lower for w in BUTTON_WORDS):
        return []
    return [(lo, hi, unit, note)
            for plug, mdl, key, lo, hi, unit, note in ABS_RANGES
            if _match(plug, mdl, key, plugin, model, pname_lower)]


def param_scale(plugin, model, pname_lower):
    """返回该参数的量纲类型：'abs:BPM' / 'norm'。

    ★ 用与 _match 相同的精确匹配，否则 "Master clock" 的 abs 判定
      会漏掉（实测：Clocked 的 BPM 规则一度完全不生效）。"""
    for (plug, mdl, key), scale in PARAM_SCALE.items():
        if _match(plug, mdl, key, plugin, model, pname_lower):
            return scale
    return DEFAULT_SCALE


def is_bypass_zero(name_lower, info):
    """判断 `值=0` 是否属于「关掉这个功能」的合法旁通值。

    ★ 实测（10-19）：`MixMasterJr '-01-: HPF cutoff' = 0` 看着越界
      （源码 min=13 max=1000），但 0 在滤波类参数里是**旁通 = 不滤波**，
      是完全合法的写法。把它当越界报 ⇒ 审计器天天误报 ⇒ 没人再看它。
      ⇒ 判据：min > 0 且值为 0，且参数名含滤波/同步类词 ⇒ 视为旁通，放行。
    """
    if info is None:
        return False
    lo = info.get("min")
    if not isinstance(lo, (int, float)) or lo <= 0:
        return False
    bypass_words = ("cutoff", "hpf", "lpf", "filter", "freq", "hz",
                    "delay", "time", "ms ", "s ", "pitch", "bpm", "rate")
    return any(w in name_lower for w in bypass_words)


def audit(path, verbose=True):
    d = patchio.read_patch(path)
    mods = d.get("modules", [])
    lines = []
    hard = 0   # L1 命中数（必须打回）
    soft = 0   # L2/L3 命中数（告警）

    for m in mods:
        model = m.get("model", "")
        ml = model.lower()
        plugin = m.get("plugin")
        plugin = plugin if isinstance(plugin, str) else (plugin or {}).get("slug", "")
        mid = m.get("id")

        # ---- L1：MIDI 音符低于人耳下限 ----
        if any(k in ml for k in MIDI_NOTE_MODELS):
            notes = _collect_notes(m.get("data"))
            for n in notes:
                hz = 440.0 * 2 ** ((n - 69) / 12.0)
                if n < MIDI_FLOOR:
                    lines.append(
                        "  [L1] ✗ %s 音符 MIDI %d = %.1f Hz —— 低于人耳下限 20 Hz（不可闻）"
                        % (model, n, hz))
                    hard += 1
                elif n > MIDI_CEIL:
                    lines.append(
                        "  [L1] ✗ %s 音符 MIDI %d = %.1f Hz —— 超出 C-8，超出配器音域"
                        % (model, n, hz))
                    hard += 1

        # ---- L2：逐参数按**量纲**对照范围 ----
        is_sample = any(k in ml for k in SAMPLE_PLAYERS)
        for pid, val in iter_params(m.get("params")):
            if not isinstance(val, (int, float)):
                continue
            name = pname(paramlib, plugin, model, int(pid))
            if name is None:
                continue
            nl = name.lower()
            scale = param_scale(plugin, model, nl)

            # L2a：绝对量纲参数 —— 这里才能真正套感知边界
            if scale.startswith("abs"):
                unit = scale.split(":", 1)[1]
                for lo, hi, u2, note in find_abs_rules(plugin, model, nl):
                    tag = "✗" if (val < lo or val > hi) else "·"
                    msg = ("  [L2a] %s %s.%s(%s) = %g %s ∈ %g–%g %s —— %s"
                           % (tag, model, name, pid, val, unit, lo, hi, unit, note))
                    if val < lo or val > hi:
                        lines.append(msg)
                        soft += 1
                    else:
                        lines.append(msg)

            # L2c：八度量纲（Bogaudio-VCO.Frequency）——换算成 Hz 后再判
            if scale.startswith("oct"):
                for plug, mdl, key, slow_id, disp in OCTAVE_PARAMS:
                    if not _match(plug, mdl, key, plugin, model, nl):
                        continue
                    slow = 0.0
                    for sid, sval in iter_params(m.get("params")):
                        if sid == slow_id and isinstance(sval, (int, float)):
                            slow = -7.0 if sval >= 0.5 else 0.0
                    hz = 2 ** (val + slow) * 440.0
                    oor = hz < OCT_LO_HZ or hz > OCT_HI_HZ
                    lines.append(
                        "  [L2c] %s %s.%s(%s) = %g 八度%s -> %.1f Hz"
                        " —— 配器区间 %g–%g Hz"
                        % ("!" if oor else "·", model, name, pid, val,
                           "（Slow 模式，offset -7）" if slow else "", hz,
                           OCT_LO_HZ, OCT_HI_HZ))
                    if oor:
                        soft += 1

            # L2b：归一化参数 —— 只判 0..1 与语义合理区间
            #      ★ 绝不把归一化值当 Hz 套感知边界表（见文件头量纲铁律）
            elif not is_sample:
                for lo, hi, note in find_norm_rules(plugin, model, nl):
                    oor = val < lo - 1e-6 or val > hi + 1e-6
                    lines.append(
                        "  [L2b] %s %s.%s(%s) = %g (归一化) ∈ %g–%g —— %s"
                        % ("!" if oor else "·", model, name, pid, val, lo, hi, note))
                    if oor:
                        soft += 1

            # L3：与源码解析出的 min/max 交叉核对
            if paramlib is not None:
                try:
                    info = paramlib.describe(plugin, model, int(pid))
                except Exception:
                    info = None
                if isinstance(info, dict) and not info.get("enum"):
                    lo2, hi2 = info.get("min"), info.get("max")
                    out = (isinstance(lo2, (int, float))
                           and isinstance(hi2, (int, float))
                           and (val < lo2 - 1e-6 or val > hi2 + 1e-6))
                    if out and is_bypass_zero(nl, info) and val == 0:
                        lines.append(
                            "  [L3] · %s.%s(%s) = 0 —— 视为旁通（该功能关闭），合法"
                            % (model, name, pid))
                        out = False
                    if out:
                        lines.append(
                            "  [L3] ! %s.%s(%s) = %g —— 超出源码解析范围 %g–%g"
                            "（量纲写错？若来自克隆模板则是**模板遗留**，非本次生成）"
                            % (model, name, pid, val, lo2, hi2))
                        soft += 1

    title = os.path.basename(path)
    print("===== %s =====" % title)
    print("  模块 %d 个" % len(mods))
    if paramlib is None:
        print("  [warn] paramlib 不可用 ⇒ L3 交叉核对未执行")
    if lines:
        for l in lines:
            print(l)
    else:
        print("  ✅ 无数值越界（L1/L2/L3 全过）")
    print("  → L1 硬否决 %d 项 / L2-L3 告警 %d 项" % (hard, soft))
    print()
    return hard, soft


def _collect_notes(data):
    """从 module.data 里挖出 MIDI 音符号列表（去重、已剔除休止符）。

    覆盖已知的几种形态：
      pianoroll : data.patterns[].measures[].notes[].pitch
      其它       : data.notes / data.pattern 里带 'pitch'/'note' 的 dict

    ★★ 休止符必须剔除（10-19 实测踩坑）：
      pianoroll 里每个小节**严格 = beats×16** 个 note，
      休止写成 `{'pitch': 0, 'velocity': 0.0, 'active': False}` 占位。
      只看 pitch 会把 16 个休止符全当成「MIDI 0 = 8.2 Hz 不可闻」，
      把一份**已验收有声**的机架报成 41 条硬否决 ⇒ 审计器直接失去可信度。
      ⇒ 判据 = `active is False` 或 `velocity <= 0` ⇒ 休止，跳过。
    """
    out = set()
    if not isinstance(data, dict):
        return sorted(out)

    def walk(node, depth=0):
        if depth > 8 or not isinstance(node, (dict, list)):
            return
        if isinstance(node, list):
            for x in node:
                walk(x, depth + 1)
            return
        for k, v in node.items():
            kl = k.lower()
            if kl in ("pitch", "note", "midi_note") and isinstance(v, (int, float)):
                # 1V/oct 折算的音高（浮点、小数）不是 MIDI 音符号，跳过
                if not (0 <= v <= 127 and float(v).is_integer()):
                    continue
                # ★ 休止符占位：active=False 或 velocity=0 ⇒ 不是真音符
                active = node.get("active")
                vel = node.get("velocity", node.get("vel"))
                if active is False:
                    continue
                if isinstance(vel, (int, float)) and vel <= 0:
                    continue
                out.add(int(v))
            else:
                walk(v, depth + 1)

    walk(data)
    return sorted(out)


def main(argv):
    if not argv:
        print(__doc__)
        return 0
    base = r"D:\Cardinal\patches"
    if argv[0] == "--all":
        paths = sorted(
            os.path.join(base, f) for f in os.listdir(base)
            if f.endswith(".vcv") and not f.startswith("_")
        )
    else:
        paths = [os.path.abspath(a) for a in argv]

    total_hard = total_soft = 0
    for p in paths:
        try:
            h, s = audit(p)
        except Exception as e:
            print("===== %s =====\n  [FAIL] 读取失败: %s\n" % (os.path.basename(p), e))
            h, s = 1, 0
        total_hard += h
        total_soft += s
    print("总计：L1 硬否决 %d 项，L2/L3 告警 %d 项" % (total_hard, total_soft))
    return 1 if total_hard else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
