# AI Disclosure / 人工智能生成声明

> **Read this before relying on anything in this repository.**
> 在使用本仓库任何内容之前，请先读这一段。

## English

This project — `cardinal-mcp` — was generated **almost entirely by an AI Agent
(WorkBuddy)**, not written line-by-line by a human author.

That means:

- The **Python tools** (`tools/*.py`), the **MCP server** (`cardinal_mcp.py`), the
  **param dictionary** (`params/modules.json`, scraped from Cardinal's C++ sources by
  an LLM-written parser), the **music knowledge base** (`music/knowledge.json`), and
  **all documentation** were produced and self-reviewed by an AI.
- The agent reasoned about Cardinal's `.vcv` format, OSC protocol, and module
  parameters from source code and experiments. It can be **wrong**, it can
  **hallucinate** parameter numbers or file paths, and it **cannot hear audio** or see
  your screen.
- No human has independently audited every line for correctness, safety, or musical
  usefulness.

### What this implies for you

- **Do not trust blindly.** Review, test, and audit anything you intend to run.
- The tools that **edit files** (`layout_patch.py apply`, `musiclib.py apply`,
  `cardinal_save_live` / `cardinal_apply_recipe` over OSC) write to your patches and to
  a running Cardinal instance. Run them on **backed-up or test** patches first.
- The param / module numbers come from an automated source scraper. If a knob does
  something unexpected, cross-check against Cardinal's own UI.
- The `docs/` write-ups (DESIGN-NOTES, SMK25-midi-map, etc.) are the agent's best
  understanding at generation time — useful context, not gospel.

This code is provided **as-is, without warranty**. Use at your own risk.

## 中文

本项目 `cardinal-mcp` **几乎全部由 AI Agent（WorkBuddy）自动生成**，并非由人类逐行手写。

也就是说：

- 所有 **Python 工具**（`tools/*.py`）、**MCP 服务**（`cardinal_mcp.py`）、
  **参数字典**（`params/modules.json`，由 AI 写的解析器从 Cardinal 的 C++ 源码抓取）、
  **音乐知识库**（`music/knowledge.json`）以及**全部文档**，均由 AI 生成并自检。
- AI 是基于 Cardinal 的 `.vcv` 格式、OSC 协议与模块参数（源码 + 实验）推理得出的。
  它**可能出错**，可能**编造**参数编号或文件路径，也**听不到声音**、看不到你的屏幕。
- 没有任何人类独立审计过每一行代码的正确性、安全性或音乐上的可用性。

### 对你意味着什么

- **请勿盲目信任。** 凡打算运行的内容，请自行审查、测试、核对。
- 会**改文件**的工具（`layout_patch.py apply`、`musiclib.py apply`、经 OSC 的
  `cardinal_save_live` / `cardinal_apply_recipe`）会写入你的机架与一个正在运行的
  Cardinal 实例。先在**已备份或测试用**机架上跑。
- 参数 / 模块编号来自自动源码抓取器。如果某个旋钮表现异常，请以 Cardinal 自身界面为准核对。
- `docs/` 下的说明（DESIGN-NOTES、SMK25-midi-map 等）是生成时刻 AI 的最佳理解，
  可作参考，但不等于权威结论。

本代码**按原样提供，不附任何担保**。使用风险自负。

---

## How it was built / 生成方式

- **Agent:** WorkBuddy (AI coding agent), driving an MCP-aware client.
- **Human role:** defined the goal (play keyboard + drums + tweak on a MIDI keyboard,
  remotely controllable by AI), answered questions, tested audio, and clicked
  "Enable OSC remote control" in Cardinal. Did **not** write the code.
- **Process:** the agent explored Cardinal's repo, read panel SVGs and module C++ source,
  wrote the tools, ran them, screenshotted the result, and iterated — the same loop a
  human dev would, except the typing was done by the model.

## Suggested verification checklist / 建议核对清单

- [ ] Run `python tools/cardinal_mcp.py --selftest` and confirm OSC reachability.
- [ ] Open one patch in Cardinal manually and confirm module ids match `patch_info`.
- [ ] Try `cardinal_set_param` on a **non-critical** knob first.
- [ ] Back up `patches/` before using any `apply` / `save_live` tool.
- [ ] Spot-check a few param names in `params/modules.json` against the module's UI.
