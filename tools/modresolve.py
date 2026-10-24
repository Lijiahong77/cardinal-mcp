"""modresolve: 口语化模块名 → 候选型号 / 唯一命中（「按名字加模块」的解析层）

人要的不是 slug 对照表。「加个 VCV 的 VCF」「Bogaudio VCO」这种口语 query
进来，这里负责收敛成**可以直接喂给 add_module 的精确 slug**。

三段式（2026-10-24 李拍板的组合方案：唯一命中直加，多个列候选）：

1. **解析**：分词（含中文词表翻译）→ 识别品牌词 → 归一到 plugin slug。
   为什么要品牌归一：manifest 里 brand 叫 **VCV** 的模块，plugin slug 是
   **Fundamental**（实测 26 个 VCV-brand 模块的 plugin 全是 Fundamental）。
   「VCV」从 brand 认、「Fundamental」从 plugin 认，识别后统一按 plugin
   过滤 —— add_module 要的正是 plugin 字段，brand/plugin 的混淆从源头消失。
2. **收敛**：有品牌词 → 品牌/plugin 池内检索（通常个位数）；无品牌词 → 全库。
   品牌词必须从内容词里**摘掉**：modbrowser._score 对多词取 max，品牌词
   （0.45 分）会被 tag 命中（1.2 分）淹没 —— 实测「Bogaudio VCO」直接喂
   search 返回 157 个且正确的排 20 名开外，摘除后收敛到 2 个。
3. **判定**：池内 score>0 的模块**恰好 1 个** → unique（可直加，零猜测）；
   多个 → ambiguous（列候选让李 pick）；0 个 → no_match（如实说+建议）。

无状态：resolve 不缓存任何东西，pick=N 时用同一 query 重新 resolve 再取
第 N 个（manifest 不会在两次调用间变）。

数据源与运行引擎同源：Cardinal 安装目录自带的 PluginManifests（modbrowser
已加载，1407 模块 / 85 品牌 / 104 标签）。
"""

from __future__ import annotations

from typing import Any

import modbrowser


# ---------------------------------------------------------------- 品牌归一表

#: {小写品牌名或 plugin 名: {plugin slug, ...}}，从 manifest 惰性生成。
#: 一个词可能映射到多个 plugin（罕见：品牌名与别的 plugin slug 撞车），取并集。
_BRAND_MAP: dict[str, set[str]] | None = None

#: 停用词：英文虚词 + 中文口语零头。「not a module」这类输入若不过滤，
#: "module" 会靠描述词频在上千个模块里刷出假命中（实测 1363 个）。
_STOPWORDS = {
    "a", "an", "the", "of", "for", "with", "and", "or", "not", "no",
    "module", "modules", "add", "please", "want", "some",
    "加", "个", "的", "一", "来",
}


def _brand_map() -> dict[str, set[str]]:
    global _BRAND_MAP
    if _BRAND_MAP is not None:
        return _BRAND_MAP
    lib = modbrowser.LIB.load()
    m: dict[str, set[str]] = {}
    for mod in lib.modules:
        p = mod["plugin"]
        for key in (mod["brand"], p):
            if key:
                m.setdefault(key.lower(), set()).add(p)
    _BRAND_MAP = m
    return m


# ---------------------------------------------------------------- 主入口

def resolve(query: str, limit: int = 25) -> dict[str, Any]:
    """把口语 query 收敛成候选列表。

    返回：
      status      "unique" | "ambiguous" | "no_match"
      candidates  [{index, plugin, brand, model, name, tags, manualUrl,
                    match_score, matched_terms}, ...]（最多 limit 条）
      matched     池内 score>0 的**全量**数（判定 unique 用这个，不受 limit 截断）
      has_more    matched > len(candidates) 时为 True
      brand_resolved  {输入词: [plugin slug]} 品牌归一明细（给李看透明账）
      expanded_terms / zh_translations / untranslated_zh  词表翻译明细
      hint        0 命中时的行动建议
    """
    out: dict[str, Any] = {
        "query": query,
        "status": "no_match",
        "candidates": [],
        "matched": 0,
        "brand_resolved": {},
        "expanded_terms": [],
    }
    lib = modbrowser.LIB.load()
    if lib.error and not lib.modules:
        out["library_error"] = lib.error
        out["hint"] = ("模块库读不到（PluginManifests）。确认 Cardinal 安装路径，"
                       "或设 CARDINAL_MANIFEST_DIR。")
        return out

    # ① 分词 + 中文词表翻译（前缀匹配已修：滤波器→滤波→filter）
    terms, zh_map, zh_unmapped = modbrowser._expand(query)
    out["expanded_terms"] = terms
    if zh_map:
        out["zh_translations"] = zh_map
    if zh_unmapped:
        out["untranslated_zh"] = zh_unmapped

    # ② 品牌识别：命中品牌表的词 → 归一 plugin 集合，并从内容词中摘除
    bmap = _brand_map()
    plugins: set[str] = set()
    brand_resolved: dict[str, list[str]] = {}
    content: list[str] = []
    for t in terms:
        if t in bmap:
            ps = sorted(bmap[t])
            brand_resolved[t] = ps
            plugins.update(ps)
        else:
            content.append(t)
    out["brand_resolved"] = brand_resolved

    # ②b 停用词过滤：纯虚词输入（"not a module"）不得靠 desc 词频刷出
    # 假命中；剔完后只剩品牌词时仍列品牌全量候选（人就是想看这家全部）
    meaningful = [t for t in content if t not in _STOPWORDS]
    if not meaningful and not plugins:
        out["status"] = "no_match"
        out["hint"] = (f"「{query}」里没有可用的检索词（虚词或词表外的中文）。"
                       "用「品牌名 + 类型词」，如 'VCV VCF' / 'Bogaudio VCO'。")
        return out

    # ③ 池过滤：有品牌词进品牌池，否则全库
    if plugins:
        pool = [m for m in lib.modules if m["plugin"] in plugins]
    else:
        pool = lib.modules

    # ④ 池内打分（复用 modbrowser 的权重：tag 1.2 > name 1.0 > …）
    scored: list[tuple[float, list[str], dict[str, Any]]] = []
    for m in pool:
        sc, hits = modbrowser._score(m, meaningful)
        if sc > 0:
            scored.append((sc, hits, m))
    # 同 modbrowser 的排序：分数 → 命中词数 → 品牌字母序
    scored.sort(key=lambda x: (-x[0], len(x[1]) * -1, x[2]["brand"].lower()))

    out["matched"] = len(scored)
    picked = scored[: max(1, limit)]
    out["has_more"] = len(scored) > len(picked)
    out["candidates"] = [
        {
            "index": i + 1,
            "plugin": m["plugin"],
            "brand": m["brand"],
            "model": m["model"],
            "name": m["name"],
            "tags": m["tags"],
            "manualUrl": m["manualUrl"],
            "match_score": round(sc, 3),
            "matched_terms": hits,
        }
        for i, (sc, hits, m) in enumerate(picked)
    ]

    if not scored:
        out["status"] = "no_match"
        hint = f"「{query}」没命中。"
        if brand_resolved:
            hint += f"已识别品牌 {list(brand_resolved)}（plugin={sorted(plugins)}），但其模块里没有匹配的。"
        if zh_unmapped:
            hint += f"「{'」「'.join(zh_unmapped)}」不在中文词表里。"
        hint += "试试：加品牌词（如 'VCV VCF'）、换英文词（warm/pad/dark）、或只用品牌名+类型词。"
        out["hint"] = hint
    elif len(scored) == 1:
        out["status"] = "unique"
    else:
        out["status"] = "ambiguous"
        out["hint"] = (f"{len(scored)} 个候选（显示前 {len(picked)}）：挑一个序号，"
                       "用 pick=N 再调一次即落地。加品牌词或更具体的类型词可进一步收敛。")
    return out


# ---------------------------------------------------------------- CLI
# 人类终端直查：python tools/modresolve.py "VCV VCF"

def _cli() -> None:
    import argparse
    import json as _json

    ap = argparse.ArgumentParser(
        description="口语模块名 → 候选型号（唯一命中可直加）")
    ap.add_argument("query")
    ap.add_argument("--limit", type=int, default=25)
    a = ap.parse_args()
    print(_json.dumps(resolve(a.query, a.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__" and len(__import__("sys").argv) > 1:
    _cli()
