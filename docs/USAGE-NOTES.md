# Practical usage notes / 实用说明

[文档导航](README.md) · [English start](../README.md) · [中文上手](../README.zh-CN.md)

保留原长 README 的重要用法，并纠正已过时的推断；不是新的实机验收记录。

## Choose the right data layer / 区分数据层

- `cardinal_list_patches` / `cardinal_patch_info` 读已保存文件。文件修改不会自动进入 GUI；
  `cardinal_load_patch` 会替换当前机架，必须先保存、备份并取得许可。
- `cardinal_read_live` / `cardinal_save_live` 读取 autosave 快照。检查 `stale`、`age_seconds`、
  `note` 与会话关联；不能凭新文件时间认定它就是当前 GUI。
- 补丁版 `cardinal_live_modules` / `cardinal_modules_page`、`cardinal_cables_page`、
  `cardinal_module_json`、`cardinal_get_param` 用于实际运行态；大机架优先分页。
  查询模块需保留真实 ID，不能从旧文件猜 ID。
- 模块搜索依赖匹配构建的 PluginManifests，不把磁盘 manifest 条目数当作可实例化模块数。
  `cardinal_module_params` / `cardinal_find_param`、`cardinal_port_semantics` 辅助查参/端口；
  字典和源解析结果仍须核对，不能凭自然语言直接猜端口索引。
- `cardinal_audit` 聚合 validate/ports/chain/values/flow；FAIL 不加载。
  静态审计、`cardinal_diff` 或信号扫描不证明听感。`cardinal_deploy` 本身会加载，不是只读检查。
- raw 与 display 量纲不同且可能非线性；`cardinal_set_param_by_display` 改后用
  `cardinal_get_param` 读回。多个独立 history 动作不自动成为一次原子事务或一次 undo。
  接线时同一输入口只接一根线；module_move 的 x 是 HP 格、y 是行号，保护手工布局。

## Workflows / 工作流示意

下列是选择工具的说明，不是自动执行指令，也不是验证过的对话转录。

| 目的 | 保守做法 |
|---|---|
| 调亮滤波器 | 先查实际模块 ID、Cutoff 定义及量程；获准后改一个参数并读回，不虚构“已听到更亮” |
| 排查无声 | 先静态审计，再核实际模块/线与端口电压；最后由用户试听，零电压可能只是没有音符输入 |
| 换和弦/音色 | 用 `cardinal_music` 查进行/配方；`cardinal_apply_recipe` 写的是音色参数，不承诺一键生成完整和弦编排 |
| 编辑音乐 | `cardinal_seq_read` / `cardinal_seq_edit_note` 与 `cardinal_export_abc` 处理支持的序列器；SongRoll 段表使用 `cardinal_songroll_read/write/edit` |
| 采样迁移 | `cardinal_sample_inspect` 查失效路径，`cardinal_samples_list` 查真实文件；获准后 load/clear 并备份 |

[relocate_samples.py](../tools/relocate_samples.py) 用于迁移采样路径，先查其 CLI 并在副本操作。
不要删除 `samples/` 后仍假设使用采样的机架能响；旧机架可能含绝对路径。
生成器、布局工具、双格式 patch I/O、music/params 数据分别在
[rackgen.py](../tools/rackgen.py)、[layout_patch.py](../tools/layout_patch.py)、
[patchio.py](../tools/patchio.py)、[music](../music/)、[params](../params/)。
源码抓取/安装依赖可能要网络，不承诺所有工具从首次运行起都可脱机。

## Optional JS / 可选进程内脚本

`cardinal_js_list` 列 [js/](../js/) 脚本的 1-based 索引，`cardinal_js_run` 在 Cardinal 进程内执行。
自由文本/JSON 曾通过“脚本 + 数字索引”绕过特定旧构建的 string 输入问题；
旧“所有字符串端点都不能用/不能直接加模块”的结论不再通用，当前有 `cardinal_add_module`
与 `cardinal_add_module_named`，按真实工具 schema 使用。

- Cardinal 自身环境的 `CARDINAL_JS_MODE` 默认关闭；`read` 或 `write` 才启用，写 API 另需 `write`。
  仅改 MCP 客户端环境不会改变已运行的宿主。不要为了示例重启用户软件。
- 裸 QuickJS 不初始化 libc；默认墙钟预算 2000 ms，可由宿主环境的 `CARDINAL_JS_BUDGET_MS` 调整。
  这是限制措施，不是任意脚本无风险的保证。
- 脚本包在 IIFE 内，**用 `return` 返回结果**；不要只赋 `globalThis.result`。
- 只读 API 包括 `cardinal.modules()`、`cardinal.getParam(id, n)`、`cardinal.ports(id)`、
  `cardinal.cables()`、`cardinal.transport()`、`cardinal.moduleJson(id)`。
  `cardinal.setDisplayValue(...)`、`cardinal.moduleFromJson(...)`、`cardinal.addModule(...)`、
  `cardinal.cableAdd(...)`、`cardinal.undo()` / `cardinal.redo()` 会改状态；先审脚本、备份、许可。

## Historical details / 历史细节去向

原工具长表改由 `python -B tools/cardinal_mcp.py --tools` 与源码 `TOOLS` schema 维护，避免第二份过期清单。
恢复、源码根与编译命令以[恢复指南](../tools/osc_patch/README.md)和[交付记录](DELIVERY-2026-10-26.md)为准，
旧注入器保留在原目录。设计原因、autosave 坑、旧设备环境见[设计档案](DESIGN-NOTES.md)、
[SMK25 测量](SMK25-midi-map.md)、[交接历史](../HANDOFF.md)。
旧机架验收仍在[Quadeca](QUADECA-PATCHES-ACCEPTANCE.md)、[8 voice](8VOICE-PATCH-ACCEPTANCE.md)
与[Yorushika](YORUSHIKA-ACCEPTANCE.md)页，不自动扩大为当前版本已验。
整理前 README 原文也保留在 [338a955 提交](https://github.com/Lijiahong77/cardinal-mcp/tree/338a95501c8fb981999bee016b7b523331cb1c55)。
