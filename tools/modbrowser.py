"""modbrowser: 查本机已装模块库（人类右键菜单的那份数据）

人���在 Cardinal 里右键 → Add module → 弹出的那个模块浏览器，
背后是 Browser.cpp:43 的 `static modelDb` —— 全量模块的 slug/name/desc/tags
建成的内存模糊索引。我们这里复刻它的检索能力，但**直接读本机的
PluginManifests**（Cardinal 安装目录自带，85 个 manifest / 1422 个模块），
不另外爬网、不依赖记忆。

设计原则（对应用户的四条宪法）：
- **不替李做决定**：只列候选 + 每条带 manualURL，李自己点开看、自己挑。
- **不静默失败**：模块库读不到 / 筛选无命中，都要说清是哪一种。
- **量纲/字段必须来自真实文件**，不猜。字段缺失时如实标 missing。

Cardinal 编译生效的是 src/override/ 下的同名文件（src/Makefile:46
RACK_FILES += override/Engine.cpp），但 Browser.cpp 的数据源是 plugin
manifest，与 override 无关，两边一致。
"""

from __future__ import annotations

import functools
import glob
import json
import os
import re
from typing import Any

# ---------------------------------------------------------------- 定位 manifest

#: 已知安装位置。Cardinal 打包成 clap/lv2/vst 三个包，各自带一份 resources/。
_GLOBS = [
    r"C:\Program Files\Cardinal-win64-*/Cardinal.lv2/resources/PluginManifests/*.json",
    r"C:\Program Files\Cardinal-win64-*/Cardinal.clap/resources/PluginManifests/*.json",
    r"C:\Program Files\Cardinal*/**/resources/PluginManifests/*.json",
    r"D:\Cardinal\win64\**/resources/PluginManifests/*.json",
    r"D:\Cardinal\**/resources/PluginManifests/*.json",
]


def _manifest_dir() -> str | None:
    env = os.environ.get("CARDINAL_MANIFEST_DIR")
    if env and os.path.isdir(env):
        return env
    for pat in _GLOBS:
        hits = sorted(glob.glob(pat, recursive=True))
        if hits:
            return os.path.dirname(hits[0])
    return None


class _Lib:
    """全量模块库。惰性加载 + 进程内缓存（模块库不会中途变，除非李装插件）。"""

    def __init__(self) -> None:
        self.dir: str | None = None
        self.modules: list[dict[str, Any]] = []
        self.brands: list[str] = []
        self.tag_set: list[str] = []
        self.loaded = False
        self.error: str | None = None
        self.n_files = 0

    def load(self, force: bool = False) -> "_Lib":
        if self.loaded and not force:
            return self
        self.loaded = True
        d = _manifest_dir()
        self.dir = d
        if not d:
            self.error = (
                "找不到 PluginManifests 目录。可能路径变了，"
                "请设环境变量 CARDINAL_MANIFEST_DIR 指向它。"
            )
            return self

        mods: list[dict[str, Any]] = []
        brands: set[str] = set()
        tags: set[str] = set()
        files = sorted(glob.glob(os.path.join(d, "*.json")))
        self.n_files = len(files)
        broken: list[str] = []

        for fp in files:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:  # noqa: BLE001 - 一个坏文件不该让整个库不可用
                broken.append(f"{os.path.basename(fp)}: {e}")
                continue

            pslug = data.get("slug") or os.path.splitext(os.path.basename(fp))[0]
            pbrand = data.get("brand") or pslug
            pauthor = data.get("author") or ""
            pversion = data.get("version") or ""
            brands.add(pbrand)

            for m in data.get("modules") or []:
                mslug = m.get("slug")
                if not mslug:
                    continue
                mtags = m.get("tags") or []
                tags.update(mtags)
                mods.append(
                    {
                        "plugin": pslug,
                        "brand": pbrand,
                        "author": pauthor,
                        "plugin_version": pversion,
                        "model": mslug,
                        "name": m.get("name") or mslug,
                        "description": (m.get("description") or "").strip(),
                        "tags": mtags,
                        "manualUrl": m.get("manualUrl") or m.get("manualURL") or "",
                        "moduleUrl": m.get("moduleUrl") or "",
                        "keywords": m.get("keywords") or [],
                        "hidden": bool(m.get("hidden")),
                        "disabled": bool(m.get("disabled")),
                        "deprecated": bool(m.get("deprecated")),
                    }
                )

        # 默认不暴露 hidden/disabled/deprecated —— 人在菜单里也看不到
        mods = [m for m in mods if not (m["hidden"] or m["disabled"] or m["deprecated"])]
        mods.sort(key=lambda m: (m["brand"].lower(), m["name"].lower()))
        self.modules = mods
        self.brands = sorted(brands)
        self.tag_set = sorted(tags)
        if broken:
            self.error = f"{len(broken)} 个 manifest 解析失败：" + "; ".join(broken[:3])
        return self


LIB = _Lib()

#: 中文口语 → 英文查询词（E10 裁决 2026-10-19：检索统一英文，中文口语靠
#: 词表**精确翻译**成英文再查，不做模糊匹配——实测中文直接猜英文原文不可靠，
#: 「金属打击」会命中 noise 发生器）。词条只收**实测校验过**的映射，
#: 源头是 modsearch.py ROUTES 速查表（那批映射已对照官方 manifest 校验）。
ZH_VOCAB: dict[str, list[str]] = {
    "古筝": ["plucked", "resonator"],
    "吉他": ["plucked", "resonator"],
    "竖琴": ["plucked", "resonator"],
    "拨弦": ["plucked", "resonator"],
    "马林巴": ["modal"],
    "木鱼": ["modal"],
    "钢琴": ["piano"],
    "电钢琴": ["electric", "piano"],
    "钟": ["bell"],
    "铃": ["bell"],
    "马林巴": ["modal", "percussion"],
    "木鱼": ["percussion"],
    "长笛": ["flute"],
    "笛子": ["flute"],
    "萨克斯": ["saxophone"],
    "单簧管": ["clarinet"],
    "管风琴": ["organ"],
    "管乐": ["wind"],
    "人声": ["voice", "vocal"],
    "元音": ["vowel"],
    "说话": ["vowel"],
    "鼓": ["drum"],
    "鼓组": ["drum"],
    "打击": ["percussion"],
    "金属打击": ["metallic", "percussion"],
    "贝斯": ["bass"],
    "减法": ["subtractive"],
    "加法": ["additive"],
    "弦乐": ["string"],
    "颗粒": ["granular"],
    "采样": ["sampler"],
    "波表": ["wavetable"],
    "氛围": ["ambient"],
    "噪声": ["noise"],
    "失真": ["distortion"],
    "过载": ["distortion"],
    "混响": ["reverb"],
    "延迟": ["delay"],
    "回声": ["delay"],
    "滤波": ["filter"],
    "合唱": ["chorus"],
    "移相": ["phaser"],
    "镶边": ["flanger"],
    "压缩": ["compressor"],
    "贝斯": ["bass"],
    "琶音": ["arpeggiator"],
    "失谐": ["unison"],
    "超锯齿": ["unison", "supersaw"],
    "暖": ["warm"],
    "暗": ["dark"],
    "亮": ["bright"],
}
_CJK = re.compile(r"[\u4e00-\u9fff]")


def _expand(query: str) -> tuple[list[str], dict[str, list[str]], list[str]]:
    """分词 + 中文口语词表翻译（E10 裁决：检索本体只走英文）。

    返回 (terms, translations, unmapped)：
    - translations = {中文词: [英文词]}，翻译成功的映射
    - unmapped = 词表里没有的中文词（保留原文进 terms，多半查不中，
      调用方据此提示换英文）
    """
    terms: list[str] = []
    trans: dict[str, list[str]] = {}
    unmapped: list[str] = []
    for w in dict.fromkeys(re.split(r"[\s,，、+]+", query.lower())):
        if not w:
            continue
        if _CJK.search(w):
            en = ZH_VOCAB.get(w)
            if en:
                trans[w] = list(en)
                terms.extend(en)
            else:
                unmapped.append(w)
                terms.append(w)
        else:
            terms.append(w)
    return [w for w in dict.fromkeys(terms) if w], trans, unmapped


def _score(m: dict[str, Any], terms: list[str]) -> tuple[float, list[str]]:
    """返回 (得分, 命中词)。得分 0 = 不匹配。

    权重按人点菜单时的直觉：名字 > 标签 > 品牌 > 描述。
    """
    if not terms:
        return 1.0, []
    name = (m["name"] + " " + m["model"]).lower()
    tags = " ".join(m["tags"]).lower()
    tag_exact = {t.lower() for t in m["tags"]}
    brand = m["brand"].lower()
    desc = m["description"].lower()
    kw = " ".join(m["keywords"]).lower() if m["keywords"] else ""

    # 描述是弱信号：英文描述里 "analog" 这类词会到处出现，命中它几乎没有
    # 判别力（实测「暖 pad」会把 Analog to Digital Logic 排到第一）。
    # 只有当查询词是完整短语、且描述里出现多次时，才认为描述命中更可信。
    best = 0.0
    hits: list[str] = []
    for t in terms:
        s = 0.0
        if t in tag_exact:
            s = 1.2                      # 官方标签精确命中 —— 最可信
        elif t in name:
            s = 1.0
        elif t in tags:
            s = 0.9
        elif t in kw:
            s = 0.5
        elif t in desc:
            # 描述命中按词频加权：出现 3 次以上才算真相关
            cnt = desc.count(t)
            s = 0.3 + min(0.2, 0.05 * cnt)
        elif t in brand:
            s = 0.45
        if s > 0:
            hits.append(t)
            best = max(best, s)
    return best, hits


def search(
    query: str = "",
    tags: list[str] | None = None,
    brand: str | None = None,
    limit: int = 20,
    include_desc: bool = True,
) -> dict[str, Any]:
    """检索模块库（人右键菜单的等价能力）。

    query      人话或英文，如 "暖 pad"、"warm pad"、"减法合成器"
    tags       官方标签精确过滤，如 ["Oscillator"] 或 ["Filter","Polyphonic"]
    brand      品牌过滤（大小写不敏感）
    limit      返回条数上限
    """
    lib = LIB.load()
    out: dict[str, Any] = {
        "query": query,
        "filters": {"tags": tags or [], "brand": brand},
        "manifest_dir": lib.dir,
        "library_size": len(lib.modules),
        "n_brands": len(lib.brands),
        "n_tags": len(lib.tag_set),
        "matched": 0,
        "modules": [],
    }
    if lib.error:
        out["library_error"] = lib.error
    if not lib.modules:
        out["error"] = lib.error or "模块库为空"
        out["hint"] = (
            "Cardinal 安装目录里没找到 PluginManifests。"
            "确认安装路径，或设 CARDINAL_MANIFEST_DIR。"
        )
        return out

    pool = lib.modules

    if brand:
        b = brand.lower()
        pool = [m for m in pool if b in m["brand"].lower()]

    if tags:
        # 多标签取交集（人要的是"同时满足"），但空标签表给个明确提示
        low = [t.lower() for t in tags]
        def has_all(m: dict[str, Any]) -> bool:
            mt = [t.lower() for t in m["tags"]]
            return any(t in mt for t in low)
        pool = [m for m in pool if has_all(m)]

    if query.strip():
        terms, zh_map, zh_unmapped = _expand(query)
        if zh_map:
            out["zh_translations"] = zh_map
        if zh_unmapped:
            out["untranslated_zh"] = zh_unmapped
            out["untranslated_hint"] = (
                f"「{'」「'.join(zh_unmapped)}」不在中文词表里，未参与有效检索。"
                "换成英文词（warm/pad/dark…）或告诉我这个词指什么音色，我来补词表。"
            )
        scored: list[tuple[float, list[str], dict[str, Any]]] = []
        for m in pool:
            sc, hits = _score(m, terms)
            if sc > 0:
                scored.append((sc, hits, m))
        scored.sort(key=lambda x: (-x[0], len(x[1]) * -1, x[2]["brand"].lower()))
        picked = scored[: max(1, limit)]
        out["expanded_terms"] = terms
        out["matched"] = len(scored)
        if not scored:
            out["hint"] = (
                f"「{query}」在 {len(pool)} 个候选模块里没命中。"
                "换英文词试（如 warm/pad/dark），或只用标签筛。"
                f"当前库共有 {len(lib.tag_set)} 种标签可用。"
            )
            out["available_tags_sample"] = lib.tag_set[:40]
        out["modules"] = [
            {
                "plugin": m["plugin"],
                "brand": m["brand"],
                "model": m["model"],
                "name": m["name"],
                "description": (m["description"] if include_desc else "")[:220],
                "tags": m["tags"],
                "match_score": round(sc, 3),
                "matched_terms": hits,
                "manualUrl": m["manualUrl"],
            }
            for sc, hits, m in picked
        ]
    else:
        out["matched"] = len(pool)
        out["modules"] = [
            {
                "plugin": m["plugin"],
                "brand": m["brand"],
                "model": m["model"],
                "name": m["name"],
                "description": (m["description"] if include_desc else "")[:220],
                "tags": m["tags"],
                "manualUrl": m["manualUrl"],
            }
            for m in pool[: max(1, limit)]
        ]

    out["next_step"] = (
        "manualUrl 可直接打开看官方说明。选定了再告诉我 slug（plugin|model），"
        "我去查它的端口和参数定义 —— 别凭名字猜端口号。"
    )
    return out


def list_tags(limit: int = 120) -> dict[str, Any]:
    """列出库里的全部标签及各自模块数（对应人右键菜单里的 Tags 筛选项）。"""
    lib = LIB.load()
    if not lib.modules:
        return {"error": lib.error or "模块库为空", "manifest_dir": lib.dir}
    from collections import Counter

    c: Counter[str] = Counter()
    for m in lib.modules:
        c.update(m["tags"])
    return {
        "manifest_dir": lib.dir,
        "library_size": len(lib.modules),
        "n_brands": len(lib.brands),
        "brands": lib.brands,
        "tags": [{"tag": t, "count": n} for t, n in c.most_common(limit)],
        "total_tag_kinds": len(c),
    }


def list_brands(limit: int = 120) -> dict[str, Any]:
    """列出全部品牌及各品牌模块数。"""
    lib = LIB.load()
    if not lib.modules:
        return {"error": lib.error or "模块库为空", "manifest_dir": lib.dir}
    from collections import Counter

    c: Counter[str] = Counter(m["brand"] for m in lib.modules)
    return {
        "manifest_dir": lib.dir,
        "brands": [{"brand": b, "count": n} for b, n in c.most_common(limit)],
        "n_brands": len(c),
    }


def detail(plugin: str, model: str) -> dict[str, Any]:
    """单个模块的完整信息（对应人右键菜单里的详情预览）。"""
    lib = LIB.load()
    hits = [
        m
        for m in lib.modules
        if m["model"].lower() == model.lower()
        and plugin.lower() in (m["plugin"].lower(), m["brand"].lower())
    ]
    if not hits:
        hits = [m for m in lib.modules if m["model"].lower() == model.lower()]
    if not hits:
        return {
            "error": f"库里没有 {plugin}|{model}",
            "manifest_dir": lib.dir,
            "library_size": len(lib.modules),
            "hint": "用 search 带 model 名搜一下，看正确 slug 拼法。",
        }
    out = dict(hits[0])
    out["same_brand_alternatives"] = [
        {"model": m["model"], "name": m["name"], "tags": m["tags"]}
        for m in lib.modules
        if m["brand"].lower() == hits[0]["brand"].lower()
        and m["model"] != hits[0]["model"]
    ][:12]
    out["note"] = (
        "这里只有 manifest 声明的信息（名字/描述/标签/手册链接）。"
        "端口号和参数定义不在 manifest 里 —— 要用 module_params 或编译后的 "
        "/param-get 去拿实测值，别猜。"
    )
    return out


# ---------------------------------------------------------------- CLI
# 人类终端直查入口（E10：检索主入口；英文关键词，中文走内置词表）。

def _cli() -> None:
    import argparse
    import json as _json

    ap = argparse.ArgumentParser(
        description="Cardinal module browser（主检索入口；英文关键词，中文走词表）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="search modules by keyword")
    s.add_argument("query")
    s.add_argument("--tag", action="append", default=None)
    s.add_argument("--brand", default=None)
    s.add_argument("--limit", type=int, default=10)
    sub.add_parser("tags", help="list all manifest tags")
    sub.add_parser("brands", help="list all brands")
    d = sub.add_parser("detail", help="one module's manifest info")
    d.add_argument("plugin")
    d.add_argument("model")
    a = ap.parse_args()
    if a.cmd == "search":
        r = search(a.query, a.tag, a.brand, a.limit)
    elif a.cmd == "tags":
        r = list_tags()
    elif a.cmd == "brands":
        r = list_brands()
    else:
        r = detail(a.plugin, a.model)
    print(_json.dumps(r, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- 自检

if __name__ == "__main__" and len(__import__("sys").argv) > 1:
    _cli()
elif __name__ == "__main__":
    import json as _json

    lib = LIB.load()
    print("manifest 目录:", lib.dir)
    print("manifest 文件数:", lib.n_files)
    print("模块总数:", len(lib.modules))
    print("品牌数:", len(lib.brands))
    print("标签种类:", len(lib.tag_set))
    if lib.error:
        print("注意:", lib.error)
    print()
    for kw in ["暖 pad", "warm pad", "弦乐", "金属打击", "有颗粒"]:
        r = search(kw, limit=3)
        print(f"查询「{kw}」→ 命中 {r.get('matched')} 个，前 3：")
        for m in r.get("modules", []):
            print(f"   {m['brand']:20s} {m['name']:22s} {'/'.join(m['tags'][:3])}")
            print(f"      {m['description'][:80]}")
        print()