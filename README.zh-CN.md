# cardinal-mcp

[English](README.md) · [文档导航](docs/README.md)

通过 MCP/OSC 与文件工具，检查、编写和控制
[Cardinal](https://github.com/DISTRHO/Cardinal) 模块化合成器机架。

> AI 协作的代码和文档可能出错。先审查，在已备份副本上测试；电压不等于听感。
> [历史 AI 声明](AI-DISCLOSURE.md) 记录早期 WorkBuddy 来源，后续工作也使用 Hermes。
> 任何 agent 的自检都不能代替用户验收。

## 能力与交付状态

- **64 个 MCP 工具**，[cardinal_mcp.py](tools/cardinal_mcp.py) 的 `TOOLS` / `DISPATCH`
  名称一致：机架检查与五道静态审计、模块/参数查询、实时读写、连线、history、序列器、
  SongRoll 段表、采样槽、ABC 导出与可选进程内 JS。
- 可选[源码恢复链](tools/osc_patch/README.md)共 **17 组 patch**，预期 **33 个 OSC 端点**、
  **36 项诊断标记**；标记检查不认证源码完整身份、构建或实机运行。
- 已交付 Python 安全修复与持久化回归 fixtures/harness。本地 native17 Windows 版本
  已获许可构建部署，用户短测 SongRoll 编辑/撤销/重做通过。精确范围与复现见
  [交付记录](docs/DELIVERY-2026-10-26.md)。
- **本仓库不提供 Cardinal 可执行文件、二进制 release 或完整构建工具链。**
  本地部署不等于新访客可下载的发布包。

## 最低安全上手

准备 Python 3.13（实际使用过的系列）、Git 与本仓库副本。在自己的环境安装两个声明依赖：

```bash
python -m pip install -r requirements.txt
python -B tools/cardinal_mcp.py --tools
```

`--tools` 只列真实工具表，不联系 Cardinal，也不是实机自测。先在 MCP 客户端使用文件只读操作，
例如：“列出已保存机架，选一个检查，但不要加载。”

实时操作需另行安装 Cardinal standalone。原版**没有全部补丁版实时读写能力**；需要时按源码补丁
及构建指南准备。允许加载、编辑、undo/redo、MIDI 或播放前，先保存当前机架并备份。
不要自动用演示架覆盖未保存修改，播放由用户控制。

只在确认目标实例并在该实例开启 OSC 后，可选择运行只读连通检查：

```bash
python -B tools/cardinal_mcp.py --call cardinal_ping
```

UDP 监听不等于应答，超时也不能证明端点不支持。检查返回错误与验证字段，不能只看进程启动成功。
`--selftest` 范围更广、会联系实机；它不能证明所有写工具或音频链均已验收。

## MCP 配置与前提

把 `<REPO>`、`<PYTHON>`、`<CARDINAL_RESOURCES>` 换成自己机器上的绝对路径（Windows 用正斜杠）；
占位符不是 shell 变量。资源目录必须对应实际使用的 Cardinal 构建。

```json
{
  "mcpServers": {
    "cardinal": {
      "command": "<PYTHON>",
      "args": ["-B", "<REPO>/tools/cardinal_mcp.py"],
      "env": {
        "CARDINAL_PATCH_DIR": "<REPO>/patches",
        "CARDINAL_MANIFEST_DIR": "<CARDINAL_RESOURCES>/PluginManifests",
        "CARDINAL_IP": "127.0.0.1",
        "CARDINAL_PORT": "2228",
        "CARDINAL_TIMEOUT": "1.5"
      }
    }
  }
}
```

另见 [mcp.example.json](mcp.example.json)。写操作保留逐次确认。服务使用 stdio/JSON-RPC；
这些环境变量配置 Python 客户端，不会改变已经运行的 Cardinal 进程环境。
Windows 桌面/MIDI 工具需要 Windows，未认证 Linux/macOS 功能对等。
旧机架和旧 helper 可能含本机路径：加载前检查采样路径，迁移可用
[relocate_samples.py](tools/relocate_samples.py)，不能假定搬目录后采样仍会响。

可选 C++ 路径还需独立上游源码、固定 Git 对象、第三方依赖与编译/交叉编译环境。
按[恢复指南](tools/osc_patch/README.md)与[交付/构建边界](docs/DELIVERY-2026-10-26.md)
操作，不走旧 injectors，不在现役 dirty 源码树重放；四个恢复根不是完整构建依赖锁。

## 测试

显式离线入口：[run_safety_regression.py](tools/run_safety_regression.py)。最后记录为
**15 个 suite、295 个唯一 unittest 方法**通过；这是已有执行记录，不是本次重跑或托管 CI 全绿声明。
需要 Windows + Ubuntu-26.04 WSL、固定源码对象、Python 依赖、g++、pthread 与真实 Jansson
开发头/运行库；缺前提失败而不是 skip。输出和 scratch 在仓库外，输出目录全新，
使用普通 Python，**不能加 `-O`**。

```text
python -B tools/run_safety_regression.py --help
python -B tools/run_safety_regression.py --out D:/external-audit/run-001 --tmpdir D:/external-scratch --wsl-source /home/USER/Cardinal --jansson-include-dir /path/to/jansson-development/include
```

示例路径须自行替换，不代表仓库附带依赖。
[交付前提](docs/DELIVERY-2026-10-26.md)与[测试导航](tools/osc_patch/TESTING.md)
解释固定对象、Jansson、standalone runner、源码来源及测试壳替换范围。

## 验证边界

- 文件审计、固定源码恢复、提取 C++ 壳测试、完整 Native 构建、有限实机行为、人耳试听分别验收。
- native17 本版用户声音确认、长时/全库、下游 PianoRoll 同步停止/静音、硬实时/延迟仍待。
  SongRoll 的锁不代表 MiniArranger 快照风险已修。
- `read_live` / `save_live` 是 autosave 快照，不是当前 GUI 权威状态；检查陈旧标记及会话关联，
  支持时使用 live module/parameter 读回。多 writer、跨输出资源事务等未证范围继续保守，
  不把 `verified=false` 改说成功。
- raw 参数值与显示单位不同，改后按实际值读回；能加载、有电压、静态通过均不等于声音验收。

## 导航

- [文档索引](docs/README.md)：使用、开发恢复、交付历史与参考资料。
  [HANDOFF](HANDOFF.md) 是接手入口，[TODO](docs/TODO-BACKLOG.md) 是唯一待办总表，均保留分阶段历史。
- [实用说明](docs/USAGE-NOTES.md)：原长 README 的实时/文件区别、JS 安全、采样迁移和工作流要点。
- 原目录不搬：[tools](tools/)、[patches](patches/)、[params](params/)、[music](music/)、
  [samples](samples/)、[refs](refs/) 与 [js](js/)。

## 许可证与来源

仓库 MIT 许可证见 [LICENSE](LICENSE)，**不重新授权** patch、fixture 或 harness `reference/`
中的上游 Cardinal/Rack/插件源码。保留原头并遵守对应上游许可（包括适用的 GPL）。
来源见[交付记录](docs/DELIVERY-2026-10-26.md)与[历史来源页](docs/ATTRIBUTION.md)；
旧来源页笼统“不随附第三方源码”的表述早于这些 fixtures，不代表当前清单。
感谢 Cardinal、VCV Rack 与社区模块作者，以及 python-osc、zstandard 依赖项目。
