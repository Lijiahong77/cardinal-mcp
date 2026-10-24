"""songroll: 读写 SongRoll 的段落表 —— 像人在 SongRoll 面板上改段那样改

用户需求：「Song 模式」——把一首曲子排成若干段（主歌/副歌/间奏），
每段指定播哪个 pattern、重复几遍。李用大白话说，我改段落表。

## 数据结构（对齐引擎 dataToJson，见 plugins/rcm-modules/src/SongRoll/SongRollData.cpp）

    data.songRoll.sections[i].channels[c] = {pattern, repeats, repeat_mode, clock_div}
    data.running        布尔：SongRoll 走带是否运行
    data.currentSection 整数：当前段号（编辑器跟随它）

    · 通道数 = 8（SONGROLL_CHANNELS，与 MiniArranger 的 4+4 轨对应）
    · pattern 1..64（**1-based**）：PATTERN# 输出电压 =(pattern-1+48)/12，
      PianoRoll 的 PATTERN_IN 收成索引 pattern-1（0..63）——两边差 1，别混
    · repeat_mode：0=FREE（不限）1=REPEATS（至少）2=LIMIT（至多）
    · clock_div：0=关，1..64

## 铁律（同 seq.py）

1. **写入前必须自检**：段数、通道数、每个字段的范围——不越界、不静默
2. **不静默失败**：改不动就说清为什么，别假装成功
3. **写盘保持原格式**：原文件是 tar.zst 归档就还写归档（`/load` 只吃 tar.zst）
4. **诚实标注来源**：读的是磁盘文件；Cardinal 开着且你手改未保存时看不到

## 生效方式（文件路线，同 seq.py）

改完写盘。若 Cardinal 开着，内存里的机架不会自动变——要么让李 Ctrl+S 反向
覆盖（危险），要么用 `load_after=True` 触发重载（会中断音频）。
热改（不重载、保留 undo 栈）需要 C++ 侧 `/module-data` 端点，尚未实现。
"""

from __future__ import annotations

import os
import shutil
from typing import Any

import patchio

PATCH_DIR = os.environ.get("CARDINAL_PATCH_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "patches"
)

#: 通道数（引擎 SONGROLL_CHANNELS）
CHANNELS = 8
#: 段数上限（防手滑；引擎本身不限）
MAX_SECTIONS = 64
#: pattern 号范围（1-based）
PATTERN_MIN, PATTERN_MAX = 1, 64
#: repeats 范围 —— 引擎不限（process 只做 max(1, repeats)），但 UI 控件 clamp 到 64
#: （面板上改不动超过 64 的值，数据里可以更大；这里给宽松上限防手滑）
REPEATS_MIN, REPEATS_MAX = 1, 4096
#: clock_div 范围（0=关）
CLOCK_DIV_MIN, CLOCK_DIV_MAX = 0, 64

#: repeat_mode 取值 → 人话
MODE_NAMES = {0: "不限", 1: "至少", 2: "至多"}


def _resolve(name: str) -> str | None:
    """机架名 → 绝对路径（允许省略 .vcv）"""
    if not name:
        return None
    if os.path.isfile(name):
        return name
    p = os.path.join(PATCH_DIR, name)
    for cand in (p, p + ".vcv" if not name.endswith(".vcv") else p):
        if os.path.isfile(cand):
            return cand
    return None


def _find_songroll(patch: dict[str, Any]) -> list[dict[str, Any]]:
    """机架里所有 SongRoll 模块"""
    out = []
    for m in patch.get("modules") or []:
        if m.get("model") == "rcm-songroll":
            out.append(m)
    return out


def _default_channel(pattern: int = 1) -> dict[str, Any]:
    return {"pattern": pattern, "repeats": 1, "repeat_mode": 1, "clock_div": 1}


def _default_sections(n: int = 1) -> list[dict[str, Any]]:
    return [
        {"channels": [_default_channel(c + 1) for c in range(CHANNELS)]}
        for _ in range(n)
    ]


def _get_sections(mod: dict[str, Any]) -> list[dict[str, Any]]:
    """取模块的段落表；没有就返回默认 1 段 8 通道"""
    data = mod.get("data") or {}
    sr = data.get("songRoll") or {}
    secs = sr.get("sections")
    if not isinstance(secs, list) or not secs:
        return _default_sections()
    return secs


def _validate_sections(sections: Any) -> tuple[bool, str]:
    """自检整张段落表。返回 (ok, 错误说明)"""
    if not isinstance(sections, list) or not sections:
        return False, "sections 必须是非空数组"
    if len(sections) > MAX_SECTIONS:
        return False, f"段数 {len(sections)} 超过上限 {MAX_SECTIONS}"
    for i, sec in enumerate(sections):
        if not isinstance(sec, dict):
            return False, f"第 {i+1} 段不是对象"
        chs = sec.get("channels")
        if not isinstance(chs, list):
            return False, f"第 {i+1} 段缺 channels 数组"
        if len(chs) != CHANNELS:
            return False, f"第 {i+1} 段有 {len(chs)} 个通道，应为 {CHANNELS}"
        for c, ch in enumerate(chs):
            if not isinstance(ch, dict):
                return False, f"第 {i+1} 段通道 {c+1} 不是对象"
            p = ch.get("pattern", 1)
            r = ch.get("repeats", 1)
            m = ch.get("repeat_mode", 1)
            cd = ch.get("clock_div", 1)
            if not isinstance(p, int) or not (PATTERN_MIN <= p <= PATTERN_MAX):
                return False, (f"第 {i+1} 段通道 {c+1} pattern={p!r} 越界"
                               f"（应为 {PATTERN_MIN}..{PATTERN_MAX}，1-based）")
            if not isinstance(r, int) or not (REPEATS_MIN <= r <= REPEATS_MAX):
                return False, (f"第 {i+1} 段通道 {c+1} repeats={r!r} 越界"
                               f"（应为 {REPEATS_MIN}..{REPEATS_MAX}；"
                               f"注意面板控件只支持到 64）")
            if not isinstance(m, int) or not (0 <= m <= 2):
                return False, (f"第 {i+1} 段通道 {c+1} repeat_mode={m!r} 越界"
                               f"（0=不限 1=至少 2=至多）")
            if not isinstance(cd, int) or not (CLOCK_DIV_MIN <= cd <= CLOCK_DIV_MAX):
                return False, (f"第 {i+1} 段通道 {c+1} clock_div={cd!r} 越界"
                               f"（应为 {CLOCK_DIV_MIN}..{CLOCK_DIV_MAX}，0=关）")
    return True, ""


def describe(sections: list[dict[str, Any]]) -> str:
    """人话摘要——给李看的，不是给机器看的"""
    if not sections:
        return "（空段落表）"
    lines = [f"{len(sections)} 段 × {CHANNELS} 通道"]
    for i, sec in enumerate(sections):
        chs = sec.get("channels") or []
        parts = []
        for c, ch in enumerate(chs):
            p = ch.get("pattern", 1)
            r = ch.get("repeats", 1)
            m = ch.get("repeat_mode", 1)
            cd = ch.get("clock_div", 1)
            if m == 0:
                seg = f"{p}×不限"
            else:
                seg = f"{p}×{r}({MODE_NAMES.get(m, '?')})"
            if cd > 1:
                seg += f"/{cd}"
            parts.append(f"ch{c+1}:{seg}")
        lines.append(f"  段{i+1}: " + "  ".join(parts))
    return "\n".join(lines)


def _read_patch(path: str) -> tuple[dict[str, Any] | None, str]:
    try:
        return patchio.read_patch(path), ""
    except Exception as e:  # noqa: BLE001
        return None, f"解析失败：{e}"


def _write_patch_preserving_format(path: str, d: dict[str, Any]) -> str:
    """写盘并保持原文件格式（tar.zst 归档就还写归档——/load 只吃 tar.zst）"""
    with open(path, "rb") as f:
        was_archive = patchio.is_archive(f.read())
    patchio.write_patch(path, d, as_archive=was_archive)
    return path


def _select_module(patch: dict[str, Any], module: str | None) -> tuple[dict | None, str]:
    mods = _find_songroll(patch)
    if not mods:
        return None, "这份机架里没有 SongRoll 模块（model=rcm-songroll）"
    if module:
        for m in mods:
            if module.lower() in m.get("model", "").lower() or \
               module.lower() in f"{m.get('plugin')}|{m.get('model')}".lower():
                return m, ""
        return None, (f"机架里有 {len(mods)} 个 SongRoll，但没有名为 {module!r} 的"
                      f"（本工具按 model 名匹配，用 'songroll' 即可）")
    return mods[0], ""


# ================================================================ 读取

def read_sections(patch_name: str, module: str | None = None) -> dict[str, Any]:
    """读出段落表（人话摘要 + 原始 JSON）"""
    path = _resolve(patch_name)
    out: dict[str, Any] = {"ok": False, "patch": patch_name, "module": module}
    if not path:
        out["error"] = f"找不到机架 {patch_name}"
        out["patch_dir"] = PATCH_DIR
        return out

    d, err = _read_patch(path)
    if d is None:
        out["error"] = err
        return out

    m, err = _select_module(d, module)
    if m is None:
        out["error"] = err
        return out

    sections = _get_sections(m)
    data = m.get("data") or {}
    out.update({
        "ok": True,
        "source": "vcv_file",
        "module": f"{m.get('plugin')}|{m.get('model')}",
        "module_id": m.get("id"),
        "section_count": len(sections),
        "running": (data.get("running")),
        "current_section": data.get("currentSection"),
        "sections": sections,
        "summary": describe(sections),
        "note": ("读的是磁盘文件。Cardinal 开着且你手改过未保存的话看不到 —— "
                 "保存后，或编译后用 /module-json 读运行中状态。"),
    })
    return out


# ================================================================ 写入

def _commit(patch_name: str, d: dict[str, Any], path: str,
            backup: bool, load_after: bool) -> dict[str, Any]:
    """备份 → 写盘 → （可选）重载。返回写盘结果字典。"""
    out: dict[str, Any] = {}
    if backup:
        bak = path + ".bak-songroll"
        shutil.copy2(path, bak)
        out["backup"] = bak
        out["backup_note"] = "⚠️ Cardinal 若开着，之后在它里 Ctrl+S 会覆盖这次改动。"

    try:
        _write_patch_preserving_format(path, d)
    except Exception as e:  # noqa: BLE001
        out["ok"] = False
        out["error"] = f"写盘失败（已备份，可回滚）：{e}"
        return out

    out["ok"] = True
    out["written"] = path
    out["note"] = ("文件已改。若 Cardinal 开着，要看到效果需重新加载"
                   "（load_patch 会中断音频，先确认）。")
    if load_after:
        import cardinal_mcp as cm
        out["loaded"] = cm.load_patch(os.path.basename(path))
    return out


def write_sections(patch_name: str, module: str | None, sections: list[dict[str, Any]],
                   backup: bool = True, load_after: bool = False) -> dict[str, Any]:
    """整表写入段落表（自检不过就不写）"""
    path = _resolve(patch_name)
    out: dict[str, Any] = {"ok": False, "patch": patch_name, "module": module}
    if not path:
        out["error"] = f"找不到机架 {patch_name}"
        return out

    ok, why = _validate_sections(sections)
    if not ok:
        out["error"] = f"段落表自检没过：{why}"
        out["hint"] = ("每段必须有 8 个通道，每个通道四个字段："
                       "pattern 1..64 / repeats 1..64 / repeat_mode 0..2 / clock_div 0..64")
        return out

    d, err = _read_patch(path)
    if d is None:
        out["error"] = err
        return out

    m, err = _select_module(d, module)
    if m is None:
        out["error"] = err
        return out

    m.setdefault("data", {})
    m["data"].setdefault("songRoll", {})
    m["data"]["songRoll"]["sections"] = sections

    res = _commit(patch_name, d, path, backup, load_after)
    out.update(res)
    if res.get("ok"):
        out["summary"] = describe(sections)
    return out


def edit(patch_name: str, module: str | None, op: str,
         section: int | None = None, channel: int | None = None,
         pattern: int | None = None, repeats: int | None = None,
         mode: int | None = None, clock_div: int | None = None,
         index: int | None = None, after: int | None = None,
         src: int | None = None, dst: int | None = None,
         running: bool | None = None,
         backup: bool = True, load_after: bool = False) -> dict[str, Any]:
    """高层操作——李用大白话说，我改段落表。

    op 取值：
      add_section      加一段（after=插在哪一段之后；不给=末尾；默认复制末段内容）
      remove_section   删一段（index）
      duplicate_section 复制一段（index）
      move_section     挪一段（src → dst）
      set_channel      改某段某通道（section + channel + pattern/repeats/mode/clock_div）
      set_running      设走带开关（running=True/False）
    """
    path = _resolve(patch_name)
    out: dict[str, Any] = {"ok": False, "patch": patch_name, "module": module, "op": op}
    if not path:
        out["error"] = f"找不到机架 {patch_name}"
        return out

    d, err = _read_patch(path)
    if d is None:
        out["error"] = err
        return out

    m, err = _select_module(d, module)
    if m is None:
        out["error"] = err
        return out

    sections = _get_sections(m)
    n = len(sections)

    def bad(msg: str) -> dict[str, Any]:
        out["error"] = msg
        return out

    if op == "add_section":
        at = n if after is None else after + 1
        if not (0 <= at <= n):
            return bad(f"after={after} 越界（现有 {n} 段）")
        if n + 1 > MAX_SECTIONS:
            return bad(f"段数会到 {n+1}，超过上限 {MAX_SECTIONS}")
        template = sections[at - 1] if at > 0 else (sections[-1] if sections else None)
        newsec = {"channels": [dict(ch) for ch in (template or {}).get("channels", [])]} \
            if template else _default_sections(1)[0]
        if len(newsec.get("channels", [])) != CHANNELS:
            newsec = _default_sections(1)[0]
        sections.insert(at, newsec)
        out["detail"] = f"在第 {at+1} 段位置插入了新段（共 {len(sections)} 段）"

    elif op == "remove_section":
        if index is None or not (0 <= index < n):
            return bad(f"index={index} 越界（现有 {n} 段，0-based）")
        removed = sections.pop(index)
        out["detail"] = (f"删掉第 {index+1} 段（pattern "
                         f"{[c.get('pattern') for c in removed.get('channels', [])]}），"
                         f"剩 {len(sections)} 段")

    elif op == "duplicate_section":
        if index is None or not (0 <= index < n):
            return bad(f"index={index} 越界（现有 {n} 段，0-based）")
        copy = {"channels": [dict(ch) for ch in sections[index].get("channels", [])]}
        sections.insert(index + 1, copy)
        out["detail"] = f"复制了第 {index+1} 段，插在它后面（共 {len(sections)} 段）"

    elif op == "move_section":
        if src is None or dst is None:
            return bad("move_section 需要 src 和 dst（0-based 段号）")
        if not (0 <= src < n) or not (0 <= dst < n):
            return bad(f"src={src} / dst={dst} 越界（现有 {n} 段，0-based）")
        sec = sections.pop(src)
        sections.insert(dst, sec)
        out["detail"] = f"第 {src+1} 段挪到第 {dst+1} 段位置"

    elif op == "set_channel":
        if section is None or channel is None:
            return bad("set_channel 需要 section（段号 0-based）和 channel（1..8）")
        if not (0 <= section < n):
            return bad(f"section={section} 越界（现有 {n} 段，0-based）")
        if not (1 <= channel <= CHANNELS):
            return bad(f"channel={channel} 越界（1..{CHANNELS}）")
        ch = sections[section]["channels"][channel - 1]
        changes = []
        if pattern is not None:
            if not (PATTERN_MIN <= pattern <= PATTERN_MAX):
                return bad(f"pattern={pattern} 越界（{PATTERN_MIN}..{PATTERN_MAX}）")
            changes.append(f"pattern {ch.get('pattern')}→{pattern}")
            ch["pattern"] = pattern
        if repeats is not None:
            if not (REPEATS_MIN <= repeats <= REPEATS_MAX):
                return bad(f"repeats={repeats} 越界（{REPEATS_MIN}..{REPEATS_MAX}）")
            changes.append(f"repeats {ch.get('repeats')}→{repeats}")
            ch["repeats"] = repeats
        if mode is not None:
            if not (0 <= mode <= 2):
                return bad(f"mode={mode} 越界（0=不限 1=至少 2=至多）")
            changes.append(f"mode {ch.get('repeat_mode')}→{mode}({MODE_NAMES.get(mode,'?')})")
            ch["repeat_mode"] = mode
        if clock_div is not None:
            if not (CLOCK_DIV_MIN <= clock_div <= CLOCK_DIV_MAX):
                return bad(f"clock_div={clock_div} 越界（{CLOCK_DIV_MIN}..{CLOCK_DIV_MAX}）")
            changes.append(f"clock_div {ch.get('clock_div')}→{clock_div}")
            ch["clock_div"] = clock_div
        if not changes:
            return bad("set_channel 至少要给一个字段：pattern / repeats / mode / clock_div")
        out["detail"] = (f"第 {section+1} 段通道 {channel}: " + "、".join(changes))

    elif op == "set_running":
        m.setdefault("data", {})
        old = m["data"].get("running")
        m["data"]["running"] = bool(running)
        out["detail"] = f"running {old} → {bool(running)}"

    else:
        return bad(f"不认识的 op={op!r}。可用：add_section / remove_section / "
                   "duplicate_section / move_section / set_channel / set_running")

    # 写回 + 自检
    ok, why = _validate_sections(sections)
    if not ok:
        return bad(f"改完自检没过（没写盘）：{why}")

    m.setdefault("data", {})
    m["data"].setdefault("songRoll", {})
    m["data"]["songRoll"]["sections"] = sections

    res = _commit(patch_name, d, path, backup, load_after)
    out.update(res)
    if res.get("ok"):
        out["summary"] = describe(sections)
    return out
