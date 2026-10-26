# 文档导航 / Documentation

[English entry](../README.md) · [中文入口](../README.zh-CN.md)

先看 [当前交付记录](DELIVERY-2026-10-26.md)，再按任务选下面的资料。
[HANDOFF](../HANDOFF.md) 是接手入口，[TODO-BACKLOG](TODO-BACKLOG.md) 是唯一待办总表；
两者正文保留历史阶段，旧“未编译/未部署/待推送”和操作命令不能覆盖页首当前状态，也不构成新授权。
本页只导航，不另建一份产品计划。旧技术页的工具数、端点数、源码行号可能过时：
工具以 `tools/cardinal_mcp.py` 的 TOOLS/DISPATCH 为准，恢复以 replay_osc.py 与交付页为准。

## 使用指南 / Usage

- [实用说明 / Practical notes](USAGE-NOTES.md)：文件与 live 的区别、JS、采样与工作流。
- [采样指南](SAMPLING-GUIDE.md)、[采样演示](SAMPLING-DEMO-WALKTHROUGH.md)。
- [歌曲到机架](SONG-TO-PATCH-WORKFLOW.md)、[风格数据 schema](STYLE-SCHEMA.md)。
- [SMK25 MIDI 测量](SMK25-midi-map.md)、[音色设计资源](SOUND-DESIGN-RESOURCES.md)、[真实乐器模拟](REAL-INSTRUMENT-EMULATION.md)。

## 开发与恢复 / Development and recovery

- [源码 patch 恢复入口](../tools/osc_patch/README.md)：唯一重放链；旧 injectors 只作历史参考。
- [测试与 harness 导航](../tools/osc_patch/TESTING.md)：显式 runner、依赖、reference 来源与壳测试边界。
- [WSL2 构建手册](WSL2-BUILD-MANUAL.md)、[构建笔记](BUILD-NOTES.md)、[上游 Win64 可移植性](UPSTREAM-WIN64-PORTABILITY.md)：历史环境经验，须结合当前交付前提。
- [MCP 规格](CARDINAL-MCP-SPEC.md)、[能力地图](CARDINAL-MCP-CAPABILITY-MAP.md)、[人类操作映射](HUMAN-INTERACTION-MAP.md)：查设计与源码位置，不替代当前工具表。
- [OSC 自动开启](CARDINAL-OSC-AUTOSTART.md)、[重建计划](CARDINAL-REBUILD-PLAN.md)：按日期理解，部署/启动仍需单独许可。

## 交付与历史 / Delivery and history

- [2026-10-26 交付记录](DELIVERY-2026-10-26.md)：已提交代码、离线回归、恢复、完整构建、有限实机与未验项。
- [接手说明](../HANDOFF.md)、[唯一待办总表](TODO-BACKLOG.md)。
- [10-22 进展](PROGRESS-2026-10-22.md)、[状态历史](STATUS-OVERVIEW.md)、[环境历史](ENV-READINESS-REPORT.md)、[迭代报告](ITERATION-LOOP-REPORT.md)。
- 机架验收：[Quadeca](QUADECA-PATCHES-ACCEPTANCE.md)、[Quadeca 静态检查](QUADECA-PATCHES-R1-STATIC.md)、[8 voice](8VOICE-PATCH-ACCEPTANCE.md)、[Yorushika](YORUSHIKA-ACCEPTANCE.md)。旧版验收不自动继承到 native17。
- [设计档案](DESIGN-NOTES.md)、[企划 2 规格](PROJECT2-SPEC.md)、[尾音自反馈事故](TAIL-SELFFEED-INCIDENT.md)。

## 参考资料 / References

- [Cardinal 上游研究](CARDINAL-REPO-NOTES.md)、[Biset 参考映射](BISET-REFERENCE-MAP.md)。
- [历史第三方来源](ATTRIBUTION.md)：其中“不分发源码”总述早于现有 fixtures；当前源码来源/许可边界见[交付记录](DELIVERY-2026-10-26.md)。
- [历史 AI 声明](../AI-DISCLOSURE.md)、[仓库许可证](../LICENSE)：MIT 不重新授权上游源码。
- [视频脚本](BILIBILI-VIDEO-SCRIPT.md)、[给上游的信草稿](letter-to-paul-draft.md)：草稿不是已发布/已发送证明。
- 原资产目录：[refs](../refs/)、[patches](../patches/)、[params](../params/)、[music](../music/)、[samples](../samples/)。
