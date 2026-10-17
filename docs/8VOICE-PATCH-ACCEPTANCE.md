# 8 轨发声链机架 · 验收清单（2026-10-17 生成 · 待实机验收）

## 交付物

| 文件 | 说明 |
|---|---|
| `D:\Cardinal\patches\mini_arranger_8voice.vcv` | **单声道版**（HostMIDI channels=1）。8 轨全接发声链 |
| `D:\Cardinal\patches\mini_arranger_8voice_poly.vcv` | **多声道版**（channels=16），能弹和弦 |

两份都是 **32 模块 / 46 线**，静态审计全过（自写审计 + 官方 validate.py 双重校验，0 问题）。
旧机架 `mini_arranger_audition.vcv` / `expanded.vcv` **未改动**，仍可正常打开。

---

## 一、这次改了什么

**之前**：8 条轨只有 2 条接了发声链（主模块试听口 + 扩展器 E1），其余 6 条输出口空悬 ⇒ 同时最多响 2 轨。

**现在**：8 条轨每条各挂一条 `VCO → ADSR → VCA`，分进两个 Mixer：

```
主模块 轨1/2/3/4 各自 V/Oct+Gate ─> VCO ─> ADSR ─┐
扩展器 E1/E2/E3/E4 各自 V/Oct+Gate ─> VCO ─> ADSR ─┴─> VCA
                                                      │
        T1-T4 + E1 + E2 ─> Mixer A (6 路) ──────────┼─> HostAudio2 IN0
                              E3 + E4 ─> Mixer B ────┴─> HostAudio2 IN1
```

**试听口 17/18 故意没接链** —— 它和轨 1 音源重叠，接了就会双重发声（就是你之前听到的"两层"）。
想用时：把 17/18 拖到某个还没接的 VCO 输入上，或加第 9 条链。

## 二、端口表（全部核实自 `MiniArranger.cpp` enum OutputIds）

| 源 | V/Oct | Gate |
|---|---|---|
| 主模块 轨 1 | OUT **0** | OUT **1** |
| 主模块 轨 2 | OUT **3** | OUT **4** |
| 主模块 轨 3 | OUT **6** | OUT **7** |
| 主模块 轨 4 | OUT **9** | OUT **10** |
| 试听口 | OUT **17** | OUT **18** |
| 扩展器 轨 1 | OUT **0** | OUT **1** |
| 扩展器 轨 2 | OUT **3** | OUT **4** |
| 扩展器 轨 3 | OUT **6** | OUT **7** |
| 扩展器 轨 4 | OUT **9** | OUT **10** |

⚠️ **VCA-1 的 IN0=CV、IN1=音频**（不是反过来）。审计时我第一次把顺序假设反了，
误报 23/26 机架"接线错误"，查 `PORTS.md` §Fundamental 后确认现有接法正确，已撤回。

## 三、验收步骤（勾着走）

### A. 单声道版 `mini_arranger_8voice.vcv`

1. 打开 Cardinal → 加载 `mini_arranger_8voice.vcv`
2. 确认模块**能加载、不崩溃**（32 个模块铺开两排）
3. 面板上 **4 个 mute 开关全部关掉**（扩展器没有 mute 开关，只有主模块有）
4. 确认 **Clocked 在跑**（RUN 灯亮）
5. 逐轨测 —— 点 TRACK 切到 1/2/3/4，每一轨按 RUN 都应该有声音
6. **多轨同时**：录好几轨不同内容 → 全部回放时应该**同时响**
7. 手弹测试：不按 REC 直接弹键 → 有声；跑着弹 → 手弹优先，松手回放（**不该有两层音**）

### B. 多声道版 `mini_arranger_8voice_poly.vcv`

只多测一项：
8. 按住**两个以上键**（和弦）→ 应该**同时响多个音**，而不是只出一个

## 四、已知会踩的坑

| 坑 | 说明 |
|---|---|
| **面板被底部工具栏遮住** | MiniArranger 面板高 708px，Rack 底部缩放条会盖住最下面 VEL 那排。按 `Ctrl+滚轮` 缩小，或把模块往下挪一格 |
| **试听口没接链** | 拧 TRACK 只改监听对象，不会自动出声。想听某轨就用它自己的输出口 |
| **扩展器没有 Mute** | 只有主模块 4 个轨有 mute 开关；扩展器 4 轨要静音得自己断线 |
| **扩展器必须紧贴主模块右侧** | 放错位置 = LINK 灯不亮、不录音、不出声 |

## 五、生成器与工具

- `tmp/make_8voice.py` —— 生成器（含审计：端口越界 / 输入口多线短路 / version 类型 / data 类型）
- `tmp/audit_vca2.py` —— 全机架 VCA 接线审计
- `tmp/dump_patch.py` —— 按 moduleId 逐线导出机架拓扑
- `tmp/fix_polyphony.py` —— 批量改 HostMIDI 声道
