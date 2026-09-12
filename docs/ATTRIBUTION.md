# 第三方资源来源标注 / Attribution

> 本仓库**不随附**第三方版权资料（CC0 / GPL / 商业图片皆有）。这一份是「这些资源从哪儿来、怎么拿、用了什么」的清单。
> 任何人 fork 这个仓库想完全复刻功能，按本清单自己取、自己遵守对应许可即可。

---

## 1. Cardinal 自带模块 —— C++ 源码

**用途**：`tools/paramlib.py` 第一次运行时从这些 GitHub 仓库抓 `.cpp / .hpp` 文件，正则提取 PORT 编号 + 参数名，生成 `params/modules.json`。
产物缓存在 `tools/_srccache/`，**不进仓库**（已被 `.gitignore` 排除）。

### 模块清单与仓库对应

| Cardinal 中的模块 | 上游仓库 (Apache-2.0/GPL-3.0) | 抓的源码 |
|---|---|---|
| Fundamental/ADSR, VCF, VCO, VCA, Sum, Mixer | [`VCVRack/Fundamental`](https://github.com/VCVRack/Fundamental) | `src/ADSR.cpp`, `src/VCF.cpp`, `src/VCO.cpp`, `src/VCA.cpp`, `src/Sum.cpp`, `src/Mixer.cpp` |
| Cardinal/HostMIDI, HostAudio, TextEditor, HostMIDIMap, HostMIDI-Gate, HostMIDICC | [`DISTRHO/Cardinal`](https://github.com/DISTRHO/Cardinal) | `plugins/Cardinal/src/HostMIDI.cpp`, `HostAudio.cpp`, `TextEditor.cpp`, `HostMIDI-Map.cpp`, `HostMIDI-Gate.cpp`, `HostMIDICC.cpp` |
| ImpromptuModular/Clocked | [`MarcBoule/ImpromptuModular`](https://github.com/MarcBoule/ImpromptuModular) | `src/Clocked.cpp` |
| MindMeldModular/MixMaster & MixMasterJr | [`MarcBoule/MindMeldModular`](https://github.com/MarcBoule/MindMeldModular) | `src/MixMaster/MixMaster.cpp`, `MixMaster.hpp`, `MixerCommon.hpp` |
| ValleyAudio/Plateau | [`ValleyAudio/ValleyRackFree`](https://github.com/ValleyAudio/ValleyRackFree) | `src/Plateau/Plateau.cpp`, `Plateau.hpp` |
| WSTD-Drums/*（BD-9, Snare, HHat, Tomi, DMX, CR78, SampleController） | [`Wasted-Audio/WSTD_Drums`](https://github.com/Wasted-Audio/WSTD_Drums) | `src/WSTD_Drums.cpp` 全部 |

**许可证**：混 GPL-3.0（VCV Rack 系与社区插件多用）+ Apache-2.0（Cardinal 本体）。
本项目只**读取源码文本做正则提取**，不内嵌、不分发；用户本地缓存自负责任。

---

## 2. Cardinal 官方示例与模板

**用途**：写新机架时用作"模块接线范本"。本仓库**不随附**。

### 模板文件（`*.tpl.vcv`）

来自 Cardinal 自带安装 `C:\Program Files\Cardinal-win64-26.02\CardinalNative\resources\` 下的：

- `main.tpl.vcv` —— Cardinal 默认模板，含 HostMIDI/VCO/VCF/VCA/Plateau 链条
- `fx.tpl.vcv` —— 效果器模板
- `mini.tpl.vcv` —— Mini 变体默认
- `native.tpl.vcv` —— Standalone 启动机架（**写新机架前必对照此模板**）
- `synth.tpl.vcv` —— Synth 变体默认

### 社区示例（`refs/examples/*.vcv`）

由 Cardinal 上游 `examples/` 目录提供的演示机架（用于研究模块接线范式，不是要播放）：

- DRMR / JTB / VT / SpotlightKid / falkTX / nooneknowspeter 等作者的 15 个示例

**获取**：

- 模板随 Cardinal 安装包附赠（无需额外下载）
- 社区示例：clone Cardinal 仓库 `git clone https://github.com/DISTRHO/Cardinal`，目录 `plugins/Cardinal/res/` 或 `examples/`。

**许可证**：VCV Rack Module Manifest License（参见 Cardinal 的 LICENSE 文件）。本仓库只**引用**文件名，不随附内容。

---

## 3. M-VAVE MidiSuite 配置截图

**用途**：理解 M-VAVE SMK25 键盘的硬件配置（旋钮 / 鼓垫 / 触控条 / 踏板分别发什么 CC / Note / 通道）。
本仓库**不随附**（截图含个人配置与升级提示）。需要的自己去 MidiSuite 重截。

**获取**：

- 软件：[M-VAVE MidiSuite](https://www.m-vave.com/)（厂商私有软件，附带在键盘驱动包里）
- 11 张配置截图对应的页面：**Keybed, Knob1-4, Knob5-8, Knob9-12, Knob13-16, Pad1-4, Pad5-8, Pad9-12, Pad13-16, Strips&Pedal, Transport**

实测结论已脱敏归纳到 `docs/SMK25-midi-map.md`，无需原图也能用。

---

## 4. M-VAVE SMK25 官方手册

**用途**：核对手册中关于控件功能（ARP 琶音器 / SC-CH 智能和弦 / KNOB-B / PAD-B 等）的官方描述。
**不随附**（版权属于 M-VAVE）。实测发现手册与实际行为在某些细节上不一致（详见 `docs/SMK25-midi-map.md` §3.5 "分离测试"）。

**获取**：随键盘包装内附 / M-VAVE 官网支持页。

---

## 5. Cardinal 自身（被操控的目标）

**用途**：本项目操控的合成器本体。
**不重新分发**——本仓库不携带 Cardinal 二进制或源码，假定用户已经独立安装。

- 项目：https://github.com/DISTRHO/Cardinal
- 安装包：https://github.com/DISTRHO/Cardinal/releases
- 许可证：GPL-3.0

---

## 6. Python 第三方依赖

```text
python-osc>=1.8.0    MIT
zstandard>=0.21.0    BSD-3-Clause
```

均为 Python 包，pip 安装，不需要单独下载。

---

## 7. MCP 协议

Model Context Protocol 是 [Anthropic](https://www.anthropic.com/) 发布的协议规范。本项目用到的子集：

- 通信层：stdio + JSON-RPC 2.0
- 工具描述：JSON Schema
- 资源描述：URI

协议本身不附加版权要求，规范见 https://modelcontextprotocol.io/。

---

## 8. VCV Rack 社区规范

Cardinal 是 VCV Rack 的硬分叉。本项目与之相关的两点借用（参考而非抄袭）：

- **模块宽度物理约定**：1 HP = 5.08 mm（Rack / Eurorack 模块尺寸标准）
- **Rack 模块面板 SVG**：用于宽度自动测量。SVG 在 Cardinal 安装目录的 `Cardinal.lv2/resources/` 下，**仅作为本地读取源**，不重新分发。

---

## 使用本仓库时的版权风险点

| 风险 | 本仓库的做法 | 用户自做时 |
|---|---|---|
| 把第三方版权文件拷进仓库 | **明确排除**（见 `.gitignore` 与本清单） | 复刻时同样排除，或遵守对应许可 |
| 把屏幕截图等含个人信息的图片推到公网 | **`refs/_*.png` 全部** `.gitignore` 排除 | 截屏前先确认不含个人数据 |
| 把 MidiSuite 配置（厂商私有协议）上传 | `refs/smk25_config/` 全排除 | 同上 |
| 把 Cardinal 自身代码 / 二进制打包 | 不打包；假定用户已独立安装 | 同上 |

---

最后更新：2026-09-12
