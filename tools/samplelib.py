"""samplelib: 像人在 sampler 右键菜单里点「Load sample」那样装采样

## 用户的原话（这是设计依据）
「人类直接点击 sampler 右键，然后就能在一个 UI 里点击添加采样源，
那你呢？你就去代码里写，写了又重载。你为什么就不能找到人类点哪个的
位置然后，在软件场景里添加采样呢？」

## 人类点的到底是什么（源码定位）
`plugins/voxglitch/src/SamplerX8/SamplerX8LoadSample.hpp`（全文 34 行）：

    struct SamplerX8LoadSample : MenuItem {
        void onAction(...) override {
            // 人类路径：弹文件对话框选文件
            async_dialog_filebrowser(false, NULL, NULL, "Load sample",
                [module, n](char* filename) {
                    if (filename) { fileSelected(module, n, std::string(filename)); ... }
                });
            // Rack 原版路径：module->selectFileVCV()
        }
        static void fileSelected(SamplerX8* module, unsigned n, std::string filename) {
            if (filename != "") {
                if (module->sample_players[n].loadSample(filename)) {     // ← 真正加载
                    module->loaded_filenames[n] = ...getFilename();
                    module->setRoot(filename);                            // ← 记 root
                }
            }
        }
    };

⭐ **它有两个入口**：弹对话框（人用）vs 直接收文件名（我要用的）。
   差别只在 filename 怎么来，后面的 `loadSample` + `setRoot` 完全相同。

## 存盘形态（SamplerX8.hpp:64-88）
- `data.loaded_sample_path_1` .. `loaded_sample_path_8`（**1 起**，不是 0）
- `data.samples_root_dir`
- 存的是**相对路径**（实测 `samples/melody2/m_D4.wav`），靠 root 一起解析
  ⇒ ⛔ 只写 path 不写 root = 加载失败。这是必须拦住的坑。
- `dataFromJson`（:85-88）读到就 `sample_players[i].loadSample(path)`

## 本工具做什么
零编译（改 .vcv + 走已验证的 /load 热加载）。
编译后可用 `/module-json` handler 直接写运行中的 module data（Engine::moduleFromJson），
届时不必重载 —— 但现在没编，先走文件路线。
"""

from __future__ import annotations

import os
from typing import Any

import patchio

PATCH_DIR = os.environ.get("CARDINAL_PATCH_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "patches"
)
#: 仓库根（samples/ 就在它下面）
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: 采样根目录（相对路径的基准）。Cardinal 搜样本的默认位置之一。
SAMPLES_DIR = os.environ.get("CARDINAL_SAMPLES_DIR") or os.path.join(REPO_ROOT, "samples")

#: 支持的采样模块：model → (槽位数, 路径字段前缀, root字段)
SAMPLERS: dict[str, tuple[int, str, str | None]] = {
    # (槽位, path字段模板, root字段)
    "samplerx8": (8, "loaded_sample_path_{}", "samples_root_dir"),
    "sampler16p": (16, "loaded_sample_path_{}", "samples_root_dir"),
}

AUDIO_EXT = (".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg", ".opus", ".w64")


def _resolve_patch(name: str) -> str | None:
    if not name:
        return None
    if os.path.isfile(name):
        return name
    p = os.path.join(PATCH_DIR, name)
    for c in (p, p + ".vcv" if not name.endswith(".vcv") else p):
        if os.path.isfile(c):
            return c
    return None


def _find_samplers(patch: dict[str, Any]) -> list[tuple[dict, int, str, str | None]]:
    out = []
    for m in patch.get("modules") or []:
        key = next(
            (k for k in SAMPLERS if m.get("model", "").lower() == k.lower()), None
        )
        if key is None:
            continue
        slots, tmpl, rootf = SAMPLERS[key]
        out.append((m, slots, tmpl, rootf))
    return out


# ---------------------------------------------------------------- 浏览

def _abs_of(stored: str) -> str:
    """把机架里存的路径解析成绝对路径。

    ⚠️ 10-19 实测踩坑：机架里存的是 `samples/melody2/m_D4.wav`，而
    SAMPLES_DIR 本身就是 `D:\\Cardinal\\samples`。若直接拼会得到
    `.../samples/samples/melody2/...` ⇒ exists=False ⇒ **加载静默失败**。
    ⇒ 先按 SAMPLES_DIR 直连试，不中再回落到仓库根试。
    """
    if not stored:
        return ""
    s = stored.replace("\\", "/")
    if os.path.isabs(stored):
        return stored
    cands = [
        os.path.join(SAMPLES_DIR, s),
        os.path.join(REPO_ROOT, s),          # repo 根（samples/ 在这儿）
        os.path.join(SAMPLES_DIR, os.path.basename(s)),
    ]
    for c in cands:
        if os.path.isfile(c):
            return c
    return cands[0]


def _rel_of(abs_path: str) -> str:
    """绝对路径 → 机架里该存的相对形式（与既有条目风格一致）。"""
    for base in (SAMPLES_DIR, REPO_ROOT):
        try:
            r = os.path.relpath(abs_path, base).replace("\\", "/")
        except ValueError:
            continue
        if not r.startswith(".."):
            return r
    return abs_path.replace("\\", "/")
    """浏览采样目录 —— 相当于人在文件对话框里翻目录。

    人类在 GUI 里能拖进任意 wav；AI 至少要能**看到**有哪些可选。
    """
    base = SAMPLES_DIR
    root = os.path.join(base, subdir) if subdir else base
    if not os.path.isdir(root):
        return {
            "error": f"采样目录不存在：{root}",
            "samples_dir": base,
            "hint": "设环境变量 CARDINAL_SAMPLES_DIR 指向你的采样目录。",
        }
    files = []
    for dirpath, _dirs, names in os.walk(root):
        for n in sorted(names):
            if n.lower().endswith(AUDIO_EXT):
                full = os.path.join(dirpath, n)
                rel = os.path.relpath(full, base).replace("\\", "/")
                try:
                    size = os.path.getsize(full)
                except OSError:
                    size = None
                files.append({"path": rel, "abs": full, "bytes": size})
    files.sort(key=lambda x: x["path"])
    dirs = sorted(
        d for d in os.listdir(root)
        if os.path.isdir(os.path.join(root, d)) and not d.startswith(".")
    )
    return {
        "samples_dir": base,
        "subdir": subdir,
        "subdirs": dirs,
        "n_files": len(files),
        "truncated": len(files) > limit,
        "files": files[:limit],
        "note": "path 是相对 samples_dir 的，可直接喂给 load_sample 的 file 参数。",
    }


def list_samples(subdir: str = "", limit: int = 300) -> dict[str, Any]:
    """列出 samples/ 下的音频文件 —— 相当于人打开采样文件对话框。

    返回相对路径（与 load_sample 的 file 参数同风格，例如
    "melody2/m_D4.wav"），并附子目录列表方便逐层浏览。
    """
    base = os.path.join(SAMPLES_DIR, subdir) if subdir else SAMPLES_DIR
    out: dict[str, Any] = {"samples_dir": SAMPLES_DIR, "subdir": subdir,
                           "samples": [], "subdirs": []}
    if not os.path.isdir(base):
        out["error"] = f"目录不存在：{subdir or '.'}"
        out["hint"] = "先用 subdir='' 看根目录有哪些子目录"
        return out
    try:
        entries = sorted(os.listdir(base))
    except OSError as e:
        out["error"] = f"读目录失败：{e}"
        return out
    for name in entries:
        full = os.path.join(base, name)
        rel = os.path.join(subdir, name) if subdir else name
        rel = rel.replace("\\", "/")
        if os.path.isdir(full):
            out["subdirs"].append(rel)
        elif name.lower().endswith(AUDIO_EXT):
            try:
                size_kb: float | None = round(os.path.getsize(full) / 1024, 1)
            except OSError:
                size_kb = None
            out["samples"].append({"path": rel, "size_kb": size_kb})
    total = len(out["samples"])
    out["total"] = total
    if total > limit:
        out["samples"] = out["samples"][:limit]
        out["truncated"] = True
        out["truncated_note"] = (
            f"只显示前 {limit} 个（共 {total}）——用 limit 或 subdir 缩小范围")
    return out


def inspect(patch_name: str) -> dict[str, Any]:
    """看机架里每个采样槽现在装了什么 —— 相当于人在界面上逐槽看。"""
    path = _resolve_patch(patch_name)
    out: dict[str, Any] = {"patch": patch_name, "samplers": []}
    if not path:
        out["error"] = f"找不到机架 {patch_name}"
        return out
    try:
        d = patchio.read_patch(path)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"解析失败：{e}"
        return out

    found = _find_samplers(d)
    if not found:
        out["error"] = "这份机架里没有采样模块"
        out["supported"] = sorted(SAMPLERS)
        out["modules_in_patch"] = [
            f"{m.get('plugin')}|{m.get('model')}" for m in (d.get("modules") or [])
        ][:40]
        return out

    out["samples_dir"] = SAMPLES_DIR
    for m, slots, tmpl, rootf in found:
        data = m.get("data") or {}
        root = data.get(rootf, "") if rootf else ""
        slots_out = []
        for i in range(1, slots + 1):     # ⛔ 1 起（源码 SamplerX8.hpp:70/85）
            rel = data.get(tmpl.format(i), "") or ""
            full = _abs_of(rel)
            slots_out.append(
                {
                    "slot": i,
                    "stored_path": rel,
                    "resolved_abs": full if rel else "",
                    "exists": bool(rel) and os.path.isfile(full),
                }
            )
        out["samplers"].append(
            {
                "module_id": m.get("id"),
                "module": f"{m.get('plugin')}|{m.get('model')}",
                "slots": slots,
                "samples_root_dir": root,
                "loaded": [s for s in slots_out if s["stored_path"]],
                "empty_slots": [s["slot"] for s in slots_out if not s["stored_path"]],
                "missing_files": [s["stored_path"] for s in slots_out
                                  if s["stored_path"] and not s["exists"]],
            }
        )
    out["loaded_total"] = sum(len(s["loaded"]) for s in out["samplers"])
    out["missing_total"] = sum(len(s["missing_files"]) for s in out["samplers"])
    return out


# ---------------------------------------------------------------- 装载

def load_sample(
    patch_name: str,
    file: str,
    slot: int = 1,
    module: str | None = None,
    backup: bool = True,
    load_after: bool = False,
) -> dict[str, Any]:
    """把一个采样装进指定槽位 —— 等价于人右键 → Load sample。

    file    相对 samples_dir 的路径（如 "melody2/m_D4.wav"）或绝对路径
    slot    1..8（samplerx8）/ 1..16（sampler16p）。**1 起**。
    """
    path = _resolve_patch(patch_name)
    out: dict[str, Any] = {
        "patch": patch_name, "file": file, "slot": slot, "module": module,
    }
    if not path:
        out["error"] = f"找不到机架 {patch_name}"
        return out
    try:
        d = patchio.read_patch(path)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"解析失败：{e}"
        return out

    found = _find_samplers(d)
    if not found:
        out["error"] = "这份机架里没有采样模块"
        out["supported"] = sorted(SAMPLERS)
        return out

    targets = [
        f for f in found
        if not module or module.lower() in f"{f[0].get('plugin')}|{f[0].get('model')}".lower()
    ]
    if not targets:
        out["error"] = f"机架里没有名为 {module} 的采样模块"
        out["found"] = [f"{m.get('plugin')}|{m.get('model')}" for m, _s, _t, _r in found]
        return out
    if len(targets) > 1:
        out["error"] = (
            f"机架里有 {len(targets)} 个采样模块，请用 module 参数指定是哪一个"
        )
        out["found"] = [
            {"module_id": m.get("id"),
             "module": f"{m.get('plugin')}|{m.get('model')}"}
            for m, _s, _t, _r in targets
        ]
        return out

    m, slots, tmpl, rootf = targets[0]
    data = m.setdefault("data", {})

    # --- 自检 1：槽位范围 ---
    if not (1 <= slot <= slots):
        return {"ok": False, "refuse": "slot_out_of_range",
                "error": f"槽位 {slot} 越界，这个模块只有 {slots} 个槽"
                         f"（源码里槽位是 1..{slots}，不是 0..{slots-1}）"}

    # --- 自检 2：文件真的存在吗 ---
    full = _abs_of(file)
    if not os.path.isfile(full):
        return {"ok": False, "refuse": "file_not_found",
                "error": f"找不到采样文件：{full}",
                "hint": "先用 cardinal_samples_list 看看有哪些。",
                "samples_dir": SAMPLES_DIR}
    rel = _rel_of(full)

    before = data.get(tmpl.format(slot), "") or ""

    # --- ⛔ 风格必须与该模块已有条目一致 ---
    # 实测机架里已有条目是 `samples/melody2/m_D4.wav`（含 samples/ 前缀）。
    # 若新写 `melody2/xxx.wav`，同一模块里两种风格混存 + root 被改，
    # 原来能解析的槽可能解析不到 ⇒ 静默哑掉。
    # ⇒ 以「已有条目」为准；空模块才用 SAMPLES_DIR 基准。
    existing = [
        v for k, v in data.items()
        if k.startswith("loaded_sample_path_") and v
    ]
    if existing:
        sample = existing[0].replace("\\", "/")
        prefix = sample.rsplit("/", 1)[0] if "/" in sample else ""
        rel_new = f"{prefix}/{os.path.basename(rel)}" if prefix else os.path.basename(rel)
        root_new = prefix
    else:
        rel_new = rel
        root_new = os.path.dirname(rel_new) or ""
    del rel          # 只用 rel_new，避免混用

    # --- 写 path ---
    data[tmpl.format(slot)] = rel_new
    # --- ⛔ 必须同步写 root（相对路径靠它解析，见文件头）
    if rootf:
        before_root = data.get(rootf, "")
        data[rootf] = root_new
    else:
        before_root, root_new = None, None

    if backup:
        import shutil

        bak = path + ".bak-sample"
        shutil.copy2(path, bak)
        out["backup"] = bak
        out["backup_note"] = "⚠️ Cardinal 若开着，之后在里面 Ctrl+S 会覆盖这次改动。"

    try:
        patchio.write_patch(path, d)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"写盘失败（已备份，可回滚）：{e}"
        return out

    out.update({
        "ok": True,
        "module_id": m.get("id"),
        "module": f"{m.get('plugin')}|{m.get('model')}",
        "slot": slot,
        "stored_path": rel_new,
        "resolved_abs": _abs_of(rel_new),
        "bytes": os.path.getsize(full),
        "before": before or None,
        "root_before": before_root,
        "root_after": root_new,
        "written": path,
    })
    if before:
        out["note"] = f"槽 {slot} 原先装的是 {before}，已被覆盖。"

    if load_after:
        import cardinal_mcp as cm

        out["loaded"] = cm.load_patch(os.path.basename(path))
    return out


def clear_slot(patch_name: str, slot: int, module: str | None = None,
               backup: bool = True) -> dict[str, Any]:
    """清空一个采样槽（相当于人在界面上把槽清掉）。"""
    path = _resolve_patch(patch_name)
    out: dict[str, Any] = {"patch": patch_name, "slot": slot}
    if not path:
        out["error"] = f"找不到机架 {patch_name}"
        return out
    try:
        d = patchio.read_patch(path)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"解析失败：{e}"
        return out

    found = _find_samplers(d)
    targets = [f for f in found
               if not module or module.lower() in f"{f[0].get('plugin')}|{f[0].get('model')}".lower()]
    if not targets:
        out["error"] = f"机架里没有 {module or '采样模块'}"
        out["found"] = [f"{m.get('plugin')}|{m.get('model')}" for m, *_ in found]
        return out

    m, slots, tmpl, _rf = targets[0]
    if not (1 <= slot <= slots):
        return {"ok": False, "refuse": "slot_out_of_range",
                "error": f"槽位 {slot} 越界，该模块有 {slots} 个槽"}
    data = m.setdefault("data", {})
    before = data.get(tmpl.format(slot), "") or ""
    data[tmpl.format(slot)] = ""

    if backup:
        import shutil

        bak = path + ".bak-sample"
        shutil.copy2(path, bak)
    try:
        patchio.write_patch(path, d)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"写盘失败（已备份）：{e}"
        return out
    out.update({"ok": True, "cleared": before or None, "backup": path + ".bak-sample"})
    return out


def set_mute(patch_name: str, slot: int, muted: bool,
             module: str | None = None) -> dict[str, Any]:
    """静音某个采样槽。

    ⚠️ 源码实测 MUTE 语义反直觉：``configSwitch {0=Unmuted, 1=Muted, 2=Soloed}``
    —— **0 才是开**（记忆里 make_quadeca_auto.py 的 _guard 已为此写过断言）。
    """
    path = _resolve_patch(patch_name)
    out: dict[str, Any] = {"patch": patch_name, "slot": slot, "muted": muted}
    if not path:
        out["error"] = f"找不到机架 {patch_name}"
        return out
    try:
        d = patchio.read_patch(path)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"解析失败：{e}"
        return out

    found = _find_samplers(d)
    targets = [f for f in found
               if not module or module.lower() in f"{f[0].get('plugin')}|{f[0].get('model')}".lower()]
    if not targets:
        out["error"] = f"机架里没有 {module or '采样模块'}"
        return out
    m, slots, _tmpl, _rf = targets[0]
    if not (1 <= slot <= slots):
        return {"ok": False, "refuse": "slot_out_of_range",
                "error": f"槽位 {slot} 越界，该模块有 {slots} 个槽"}

    params = m.setdefault("params", [])
    # SamplerX8 的 MUTE 段起始编号需实测，这里先扫描现有 params 找线索
    out["warning"] = (
        "MUTE 的 param 编号需实测确认（samplerx8 的 MUTE_BUTTONS 偏移未知）。"
        "先用 module_params 查参数表定位后再写，别硬猜编号。"
    )
    out["param_count"] = len(params)
    out["params_head"] = params[:24]
    return out


# ---------------------------------------------------------------- 自检

if __name__ == "__main__":
    import json
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "samples"
    if cmd == "samples":
        print(json.dumps(list_samples(), ensure_ascii=False, indent=2)[:2000])
    elif cmd == "inspect":
        print(json.dumps(inspect(sys.argv[2]), ensure_ascii=False, indent=2))
    else:
        print("usage: samplelib.py [samples|inspect <patch>]")