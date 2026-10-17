# -*- coding: utf-8 -*-
r"""make_probe_min.py —— 极简探针：2 个模块，逐步加参数，锁定 GrainEngineMK2 静默之谜。

★ 为什么必须走到这一步
  v1550 探针三组（A 裸引擎/ B CV / C 全链）**全部没声**。
  已排除：WAV 文件合规（`_chk_wav.py` 十项全过）· data 字段路径正确 ·
  plugin/version 字段正确（`read_live` 回读 10 模块/14 线全对）·
  WINDOW 量纲（已改 4320 采样点）· CLK in/out channel（同一路）。
  ⇒ **静态读代码已经读不出更多信息了**，必须靠最笨的办法：一次只加一样。

★ 这一张只放**两个模块**：GrainEngineMK2 → HostAudio2
  连 Clocked 都不要（模块内部 RATE 自跑；反正 A 组证明时钟不是原因）。
  参数**全部拉满**：WINDOW 封顶 / TRIM 2.0 / GRAINS 1.0 / RATE 0.9 /
  JITTER 0 / POSITION 0.5（避开起音） / SAMPLE 0。
  5 个槽**全部填同一文件**。

★ 判读（李只需回答一句）
  有声 ⇒ 前面某层的问题（pianoroll/Clocked/混音），定位到「单独引擎能响」。
  静音 ⇒ **模块本身在此版本 Cardinal 里不工作**（voxglitch 可能未编译进
         win64 运行版）⇒ 该换模块，而不是继续调参数。
"""
import datetime
import os
import sys

sys.path.insert(0, r"D:\Cardinal\tools")
import patchio
import audit_ports
from make_quadeca_auto import sanitize
from make_scrapyard import make_grain, clone_mod, FRAG, GRAINS

GHOST = r"D:\Cardinal\patches\quadeca_auto_ghostfolk__v1328.vcv"
SAMPLE = os.path.join(FRAG, GRAINS[0])


def main():
    ghost = patchio.read_patch(GHOST)
    mods, cables = [], []
    cid = [9950000000001000]

    def cab(a, ao, b, bi):
        nonlocal cid
        cid[0] += 1
        cables.append({"id": cid[0], "outputModuleId": a, "outputId": ao,
                       "inputModuleId": b, "inputId": bi, "color": ""})

    # GrainEngineMK2：所有旋钮拉满/归零歧义最小
    g = make_grain(9950000000000101, [-10, 0],
                   [SAMPLE] * 5,
                   pitch_knob=0.0,
                   window=1.0,       # 封顶 6400 采样点
                   trim=2.0,        # TRIM 上限 = 2.0
                   jitter=0.0,      # 关掉随机，避免 grain 落空
                   grains=1.0,      # 颗粒数拉满
                   rate=0.9,        # 内部 RATE 拉满（最密）
                   sample_knob=0.0)
    # POSITION 用 param2（0~1），拉到 0.5 避开起音爆音
    for q in g["params"]:
        if q["id"] == 2:
            q["value"] = 0.5
        if q["id"] == 3:
            q["value"] = 0.0     # POSITION_ATTN = 0（只认旋钮值）
        if q["id"] == 1:
            q["value"] = 0.0     # WINDOW_ATTN = 0（同理）
        if q["id"] == 8:
            q["value"] = 0.0     # GRAINS_ATTN
        if q["id"] == 10:
            q["value"] = 0.0     # RATE_ATTN
        if q["id"] == 12:
            q["value"] = 0.0     # SAMPLE_ATTN
    mods.append(g)

    ha = clone_mod(ghost, "HostAudio2", 9950000000000201, [30, 0])
    mods.append(ha)
    cab(g["id"], 0, ha["id"], 0)         # OUT L → HostAudio IN
    cab(g["id"], 1, ha["id"], 0)         # OUT R → 同一路（单声道就同相，若啸叫可拔掉这根）

    p = {"version": "2.4.1", "zoom": 0.7, "gridOffset": [0, 0],
         "modules": mods, "cables": cables}
    ver = datetime.datetime.now().strftime("%H%M")
    out = r"D:\Cardinal\patches\probe_min__v%s.vcv" % ver
    sanitize(p, out)
    patchio.write_patch(out, p)

    print("生成 %s：模块 %d / 连线 %d"
          % (os.path.basename(out), len(mods), len(cables)))
    print("采样:", SAMPLE)
    print()
    v = {x["id"]: x["value"] for x in g["params"]}
    print("GrainEngineMK2 参数（全部拉满歧义最小）:")
    names = ["WINDOW", "WINDOW_ATTN", "POSITION", "POSITION_ATTN", "PITCH",
             "TRIM", "JITTER", "GRAINS", "GRAINS_ATTN", "RATE", "RATE_ATTN",
             "SAMPLE", "SAMPLE_ATTN"]
    for i, nm in enumerate(names):
        extra = ""
        if nm == "WINDOW":
            extra = " → %d 采样点 ≈ %.0fms" % (int(v[i] * 6400),
                                             v[i] * 6400 / 48.0)
        print("   %-14s = %.3f%s" % (nm, v[i], extra))
    bad = audit_ports.audit(out, verbose=True)
    print("端口越界自检:", "全部通过" if not bad else "❌ %d 处" % len(bad))
    print()
    print("★ 加载后什么都不用按 —— 没有时钟，这张应当**立即**出声。")
    print("  有声 → 问题在 pianoroll/Clocked/混音那一层")
    print("  静音 → GrainEngineMK2 在本机 win64 里不工作（voxglitch 可能没编进去）")
    return out


if __name__ == "__main__":
    main()
