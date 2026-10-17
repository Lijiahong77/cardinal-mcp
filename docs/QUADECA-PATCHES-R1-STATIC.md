# Quadeca 风格机架 · 验收单

> 日期：2026-10-17
> 状态：**三张全部通过静态门禁 + 实机加载复验**。声音尚未试听（李 10-17 关麦，决定先走静默验收）。

## 一、这批机架要解决什么

把 Obsidian 那份 `Quadeca 深度解析（2018–2026 完整版）` 当成需求说明书，
用三个音乐时期各做一张 Cardinal 机架，**顺带把过去练过的整套能力真跑一遍**：
读需求拆风格 → 从已验收机架克隆模块 → 查模块端口 → 生成 `.vcv` →
布局门禁 → 端口审计 → `patchio` 回读 → OSC 推送 → 截图复验。

## 二、三张机架对照表

| 文件 | 对应时期 / 风格 | 模块数 | 线缆数 | 核心模块链 |
|---|---|---|---|---|
| `quadeca_ghostfolk.vcv` | 早期「鬼魂民谣 / IDMTHY」 | 20 | 32 | Clocked → Starsea 8 轨编曲 → 两条 VCO+VCF+ADSR+VCA → Mixer → Plateau |
| `quadeca_scrapyard.vcv` | 中期「废料场故障」 | 11 | 23 | Clocked → Starsea + `samplerx8` 8 触发 → Clouds 颗粒 → VCF → Mixer → Plateau |
| `quadeca_life1.vcv` | 近期「数字焦虑 / life1」 | 15 | 24 | Bogaudio-Unison 扩复音 → VCO+VCF+ADSR+VCA → FMOp → SurgeXT Distortion → ShapeMaster → Plateau |

**风格对应的思路**：

- **ghostfolk** —— 物理建模（Elements / Rings）拿原声质感与民谣纹理，
  Plateau 长混响做「幽灵」拖尾；8 轨编曲器负责慢速留白式配器。
- **scrapyard** —— 采样切片 + `samplerx8` 触发，Clouds 做颗粒破碎，
  VCF 压高频制造工业噪声感，整体走反拍 / 不规则节奏。
- **life1** —— Unison 把单音扩成锯齿厚波，FMOp 加金属味，
  SurgeXT 失真压到Overdrive，ShapeMaster 做 203 参数的大幅自动化扫描。

## 三、验收结果（逐项）

| 检查项 | ghostfolk | scrapyard | life1 |
|---|---|---|---|
| 生成成功（模块/线缆数对得上） | ✅ 20/32 | ✅ 11/23 | ✅ 15/24 |
| 布局门禁 `layout_patch.py guard` | ✅ PASS | ✅ PASS | ✅ PASS |
| 模块无重叠、无输入口重复接线 | ✅ | ✅ | ✅ |
| 端口合法性审计 `validate.py` | ✅ 0 问题 | ✅ 0 问题 | ✅ 0 问题 |
| `patchio` 回读（参数/数据落盘） | ✅ | ✅ | ✅ |
| OSC `/load` 实机加载 | ✅ ok | ✅ ok | ✅ ok |
| 窗口截图复验 | ✅ | ✅ | ✅ |

### 截图（窗口级，`refs/` 下）

- `refs/quadeca_ghostfolk.png`
- `refs/quadeca_scrapyard.png`
- `refs/quadeca_life1.png`

三张都能看到：模块正常渲染、面板无重叠、Starsea 主模块与扩展器紧贴、
线缆走向合理、TextEditor 说明牌在可视区内。

## 四、过程中排掉的五个问题

1. **说明牌跑到可视区右缘之外**（ghostfolk 第一版）。
   原因是 zoom 0.75 × 模块横跨太宽。→ zoom 改 0.68，并把模块整体收进第一行。
2. **`Bogaudio-Unison` 宽度被误按 10 HP 兜底**，
   导致 life1 出现假阳性重叠告警。→ `layout_patch.py` 补实测宽度 **3 HP**。
3. **`validate.py` 跨文件错误累积**：前一个文件报错会把后续文件也标成有问题；
   且把自建 Starsea 包当成未知模块误报。→ 两处都修。
4. **voxglitch 插件名大小写**：源码 master 分支 enum 与构造函数不同步，
   实际用的是全小写 `samplerx8`。→ 以本机 manifest + 已有 `.vcv` + 实机加载结果为准。
5. **截图截到的是浏览器不是机架**：`shot.py` 抓整块桌面，Cardinal 不在前台就拍到别的窗口。
   → 新写 `tmp/win_shot.py`，按窗口句柄定位 + `PrintWindow` 抓取，标题可校验（如 `Cardinal - quadeca_life1.vcv`）。

## 五、待办 / 下一步（未做，需李定夺）

- ⏸ **试听**：三张都还没听过。ghostfolk 与 life1 的输出口是音频链可直接听；
  scrapyard 的采样触发依赖 `Clocked` 运行态，需要先确认发门。
- ⏸ **让风格更贴近原曲**：目前是「用对应年代的合成器手法搭出近似质地」，
  不是复刻具体某首歌的和声/音色。要更贴近需要指定参考曲目再调。
- ⏸ **扩展器 Mute 开关**（老遗留，扩展器 4 轨目前无 Mute）。
- ⏸ **停止时门要不要落**（现为保持）。

## 六、复现方式

```bash
PY=<USERPROFILE>/.workbuddy/binaries/python/envs/music-ai/Scripts/python.exe
cd /d/Cardinal/tools
$PY make_quadeca.py                                     # 生成三张 .vcv
$PY layout_patch.py guard /d/Cardinal/patches/quadeca_*.vcv   # 布局门禁
$PY validate.py /d/Cardinal/patches/quadeca_*.vcv       # 端口审计
$PY <WORKSPACE>/tmp/win_shot.py \
    D:/Cardinal/refs/out.png Cardinal 1500                # 窗口级截图
```

⚠️ 用的是 **Windows 版 venv**（`Scripts/python.exe`），
不是 `bin/python.exe`——后者在 Git Bash 下会报 No such file。

## 七、素材出处

风格参照自李提供的 Quadeca 分析文档；机架模板来自本项目已验收机架；
采样素材为本机合成（`D:\Cardinal\samples\`，版权干净）。无第三方素材引用。