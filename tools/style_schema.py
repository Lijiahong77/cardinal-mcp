# -*- coding: utf-8 -*-
"""
style_schema.py — 风格 schema 化（批次 A11，源自 YuE2 借鉴计划①）。

目的：把「一种风格怎么搭」从散文变成**可编辑、可存 JSON、在工具间流转**的数据。
给李做「XX 风格」时：先 draft_from_patch 起草或手写一份 style JSON → 李点头
→ recipe/生成器按它消费。

schema 七字段（详见 docs/STYLE-SCHEMA.md）：
  name       风格名（人类可读）
  reference  样板 .vcv 文件名（平铺在 patches/ 下，无目录层级）
  bpm        {min, max, actual?}  actual = Clocked param0 实测（绝对 BPM）
  layers     [{role, job, modules[]}] —— 分层职责：哪层担当鼓/贝斯/和声/旋律
  reverb     {model, size, decay} —— 混响尺寸与衰减
  filter     {job, openness} —— 滤波开合倾向
  choices    [{module, why}] —— 参考模块选型及理由

API：
  validate(style)         → {ok, errors, warnings}
  draft_from_patch(name)  从已验收机架自动起草（实测字段回填，判断留给人）
  CLI: python style_schema.py draft <patch> | validate <style.json>
"""
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patchio  # noqa: E402
import seq as _seq  # noqa: E402  (用它的 _resolve 找机架路径)
import topology  # noqa: E402  (模块角色识别)

PATCH_DIR = r"D:\Cardinal\patches"

VALID_ROLES = ("drums", "bass", "harmony", "melody", "texture", "pad")


def _resolve(name: str) -> str | None:
    if not name:
        return None
    if os.path.isfile(name):
        return name
    p = os.path.join(PATCH_DIR, name)
    for cand in (p, p + ".vcv"):
        if os.path.isfile(cand):
            return cand
    return None


def validate(style: dict[str, Any]) -> dict[str, Any]:
    """校验一份 style dict → {ok, errors, warnings}。"""
    errors: list[str] = []
    warns: list[str] = []
    if not isinstance(style, dict):
        return {"ok": False, "errors": ["style 必须是 JSON object"], "warnings": []}

    if not isinstance(style.get("name"), str) or not style.get("name"):
        errors.append("name 必须是非空字符串")

    bpm = style.get("bpm")
    if not isinstance(bpm, dict):
        errors.append("bpm 需要 {min, max}（actual 可选，由 draft 回填）")
    else:
        lo, hi = bpm.get("min"), bpm.get("max")
        if not (isinstance(lo, (int, float)) and lo >= 40):
            errors.append("bpm.min 应是 >=40 的数")
        if not (isinstance(hi, (int, float)) and hi <= 240 and hi >= (lo or 0)):
            errors.append("bpm.max 应 <=240 且 >= min")

    layers = style.get("layers")
    if not isinstance(layers, list) or not layers:
        errors.append("layers 必须是非空数组（每层 {role, job, modules[]}）")
    else:
        for i, lay in enumerate(layers):
            if not isinstance(lay, dict):
                errors.append(f"layers[{i}] 必须是 object")
                continue
            if not lay.get("modules"):
                errors.append(f"layers[{i}] 缺 modules（哪几个模块担当这层）")
            if not lay.get("job"):
                errors.append(f"layers[{i}] 缺 job（这层干什么——分层职责是核心字段）")
            if lay.get("role") not in ("drums", "bass", "harmony",
                                       "melody", "texture", "pad"):
                errors.append(
                    f"layers[{i}].role='{lay.get('role')}' 不在固定词表"
                    "(drums/bass/harmony/melody/texture/pad)")

    rev = style.get("reverb")
    if rev is not None:
        if not isinstance(rev, dict) or not rev.get("model"):
            errors.append("reverb 若给出需含 model（size/decay 可后补）")
    filt = style.get("filter")
    if filt is not None:
        if not isinstance(filt, dict) or "job" not in filt:
            errors.append("filter 若给出需含 job（一句话）与 openness 0..1")
        elif not (isinstance(filt.get("openness"), (int, float))
                  and 0.0 <= filt["openness"] <= 1.0):
            errors.append("filter.openness 应是 0..1 的数")

    if not style.get("choices"):
        warns.append("没有 choices（参考模块选型+理由）——下次复刻只能从头猜选型")

    return {"ok": not errors, "errors": errors, "warnings": warns}


def draft_from_patch(patch_name: str) -> dict[str, Any]:
    """从已验收机架自动起草 style 草稿。

    自动回填（实测，不改）：reference / bpm.actual（Clocked param0 绝对 BPM）/
    module_roles 清单。留给人判断：name / 层职责 / bpm 区间 / reverb 数值 /
    choices 理由 —— schema 只装确认过的决策，不猜。
    """
    path = _resolve(patch_name)
    if not path:
        return {"error": f"找不到机架 {patch_name}"}
    d = patchio.read_patch(path)

    r = topology.analyze(patch_name)
    mods = r.get("modules") or []

    bpm_actual = None
    for m in d.get("modules", []):
        if m.get("model") == "Clocked":
            p0 = (m.get("params") or [{}])[0]
            v = p0.get("value")
            if isinstance(v, (int, float)):
                bpm_actual = round(float(v), 2)
            break

    style: dict[str, Any] = {
        "name": None,
        "reference": os.path.basename(str(path)),
        "bpm": {"min": None, "max": None, "actual": bpm_actual},
        "layers": [],
        "reverb": None,
        "filter": None,
        "choices": [],
        "module_roles": {m["model"]: m.get("role") for m in mods},
        "sequencer_count": sum(1 for m in mods if m.get("role") == "sequencer"),
        "_draft_note": (
            "自动回填草稿：bpm.actual 与模块角色是实测值。"
            "name / bpm.min-max / layers[].job / reverb / choices 需人来定——"
            "分层职责（哪层担当鼓/贝斯/和声/旋律）是本 schema 的核心字段，"
            "机器不替人拍板。"
        ),
    }
    return style


def load_style(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "draft":
        st = draft_from_patch(argv[1])
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0
    if len(argv) >= 3 and argv[0] == "validate":
        st = load_style(argv[1])
        r = validate(st)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r["ok"] else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
