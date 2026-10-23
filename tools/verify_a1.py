#!/usr/bin/env python3
"""A1 真机验收清单 —— 一键跑完三步，数据自动断言 + 位置真值喊你肉眼确认。

用法（先启动 Windows 侧 CardinalNative.exe，确认 OSC 已开在 2228）：
    python tools/verify_a1.py

它会做三件事，每件事数据能判的自动判，判不了（模块到底落在哪个格子）
就停下来让你看一眼画面、敲 y/n：
    ①  /module-move   位置真值（单位 px→格 修复是否生效）
    ②  /module-add    新模块落位 + 外观
    ③  /load-skipped  缺失插件时如实报 skip

⚠️ 步骤 ③ 会 `load` 一份坏 patch —— 这会整体替换当前机架、抹掉 GUI 手改。
   脚本在载入前会停下来问你确认；你也可以用 --no-load 跳过 ③ 只跑 ①②。
⚠️ 步骤 ①② 会用 undo 恢复，尽量不留改动；但仍建议在测试副本机架上跑。

依赖 music-ai venv（有 python-osc + zstandard）：
    C:/Users/lijia/.workbuddy/binaries/python/envs/music-ai/Scripts/python.exe tools/verify_a1.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
REPO_ROOT = os.path.dirname(HERE)

import cardinal_mcp as m  # noqa: E402
import patchio  # noqa: E402

# 真机默认连着 127.0.0.1:2228（由 CARDINAL_IP / CARDINAL_PORT 覆盖）。
TARGET = f"{m.CARDINAL_IP}:{m.CARDINAL_PORT}"

# 使用一个已知存在、structure 干净的 patch 来造"坏 patch"（含缺失插件）。
BAD_SRC = "polytest_minimal.vcv"


def ok(msg):
    print(f"\033[32m[PASS]\033[0m {msg}")


def fail(msg):
    print(f"\033[31m[FAIL]\033[0m {msg}")


def ask(msg):
    """停下让李肉眼确认，回答 y 通过、n 不通过、q 中止。"""
    while True:
        a = input(f"\n{msg}\n  [y=通过 / n=不通过 / q=中止] ").strip().lower()
        if a in ("y", "yes"):
            return True
        if a in ("n", "no"):
            return False
        if a in ("q", "quit"):
            sys.exit(2)
        print("  请回答 y / n / q")


def step(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def count_modules():
    r = m.live_modules()
    if r.get("error"):
        return None, r
    return r.get("count"), r


def main():
    no_load = "--no-load" in sys.argv
    passed = []
    failed = []

    print(f"目标: {TARGET}   patch 目录: {m.PATCH_DIR}")

    # 0) 连通性
    step("0 · 连通性（ping）")
    r = m.ping()
    if r.get("ok"):
        ok("OSC 已连通，Cardinal 在响应")
        passed.append("0-ping")
    else:
        fail("OSC 无响应 —— 确认 CardinalNative.exe 已启动、Engine 菜单 OSC 已开")
        failed.append("0-ping")
        return report(passed, failed)

    # 记录初始模块数
    n0, r0 = count_modules()
    if n0 is None:
        fail(f"读不到 live_modules：{r0}")
        return report(passed, failed)
    print(f"  当前机架 {n0} 个模块")

    # ---------- ① module-move ----------
    step("① /module-move —— 位置真值（px→格 修复是否生效）")
    mods = r0["modules"]
    # 挑一个非 Host 的普通模块来挪（HostAudio2/HostMIDI 是固定宿主模块，别动）。
    victim = next((x for x in mods
                   if x["model"] not in ("HostAudio2", "HostMIDI", "HostMIDIMap", "HostCV", "HostParameters")), None)
    if victim is None:
        fail("机架里没有可挪动的普通模块，请先在默认机架或测试副本上跑")
        return report(passed, failed)

    vid, vmodel = victim["module_id"], victim["model"]
    print(f"  将挪动模块 {vmodel} (id={vid}) 到 x=30, y=8（右下方）")
    mv = m.module_move(vid, 30, 8)
    if not mv.get("ok"):
        fail(f"module_move 返回异常：{mv}")
        failed.append("1-move")
    else:
        print(f"  OSC 回包：{mv.get('result') or mv.get('status')}")
        time.sleep(0.4)
        if ask(f"请盯住画面：模块 {vmodel} 有没有明显跳到右下方的格子？\n"
               f"  （整格跳=单位修好了；只抖 1/15 极小一点=仍是旧 px bug）"):
            ok("module-move 单位语义正确（整格生效）")
            passed.append("1-move")
        else:
            fail("module-move 位置有问题 → 记入待修")
            failed.append("1-move")
    m.undo()  # 恢复位置

    # ---------- ② module-add ----------
    step("② /module-add —— 新模块落位 + 外观")
    r = m.add_module("Fundamental", "VCO", 4, 2)
    if not r.get("ok"):
        fail(f"add_module 失败：{r}")
        failed.append("2-add")
    else:
        new_id = r.get("result")
        n1, _ = count_modules()
        if n1 == n0 + 1:
            ok(f"数据层通过：模块数 {n0} → {n1}（新 id={new_id}）")
        else:
            fail(f"模块数没 +1（{n0} → {n1}），引擎可能没真加")
            failed.append("2-add")
        if ask("请盯住画面：左上角 (4,2) 格有没有出现一个新的 VCO？\n"
               "  面板完整、不堆叠、不贴边被裁、旋钮能拖？"):
            ok("module-add 落位 + 外观正常")
            passed.append("2-add")
        else:
            fail("module-add 落位/外观有问题 → 记入待修")
            failed.append("2-add")
        m.undo()  # 移除新模块

    # ---------- ③ load-skipped ----------
    if no_load:
        print("\n（--no-load：跳过步骤 ③）")
    else:
        step("③ /load-skipped —— 缺失插件时如实报 skip")
        # 造坏 patch：读 polytest_minimal，改一个 plugin 成不存在的 slug。
        src = os.path.join(m.PATCH_DIR, BAD_SRC)
        if not os.path.exists(src):
            print(f"  跳过 ③：找不到造坏 patch 的源 {src}")
        else:
            d = patchio.read_patch(src)
            victim = next((x for x in d.get("modules", [])
                           if x.get("plugin") not in ("Cardinal",)), None)
            if victim is None:
                print("  跳过 ③：源 patch 里没有可改的普通模块")
            else:
                victim["plugin"] = "NonexistentPluginXYZ"
                bad = os.path.join(REPO_ROOT, "tmp", "a1_bad_plugin.vcv")
                os.makedirs(os.path.dirname(bad), exist_ok=True)
                patchio.write_patch(bad, d, as_archive=True)
                print(f"  已造坏 patch：{bad}（{victim['model']} 的 plugin 改成不存在的）")
                if not ask("⚠️ 步骤 ③ 会 LOAD 这份坏 patch，整体替换当前机架、抹掉 GUI 手改。\n"
                           "  确认载入？"):
                    print("  已取消步骤 ③，恢复当前机架不动")
                    return report(passed, failed)
                lp = m.load_patch(bad)
                print(f"  /load 回包：{lp.get('reply') or lp}")
                sk = m.load_skipped()
                if sk.get("ok"):
                    n = sk.get("count", 0)
                    if n > 0:
                        kinds = [s["kind"] for s in sk.get("skips", [])]
                        ok(f"load-skipped 报 {n} 条 skip（{kinds}）—— 不再静默")
                        passed.append("3-skipped")
                    else:
                        fail("load-skipped 返回 0 条，但坏 patch 里明明有缺失插件")
                        failed.append("3-skipped")
                else:
                    fail(f"load_skipped 异常：{sk}")
                    failed.append("3-skipped")
                # 载回一份干净 patch，别把机架停在坏状态
                clean = os.path.join(m.PATCH_DIR, BAD_SRC)
                m.load_patch(clean)
                print(f"  已载回干净 patch：{BAD_SRC}")

    return report(passed, failed)


def report(passed, failed):
    print("\n" + "=" * 60)
    print("验收清单结果")
    print("=" * 60)
    for p in passed:
        ok(p)
    for f in failed:
        fail(f)
    print(f"\n通过 {len(passed)} 项 / 失败 {len(failed)} 项")
    if failed:
        print("⚠️ 有失败项，别提交，先把失败项定位清楚。")
        return 1
    print("全部通过。A1 真机验收闭环。")
    return 0


if __name__ == "__main__":
    sys.exit(main())