# Offline tests and source-extraction harnesses / 测试导航

[文档索引](../../docs/README.md) · [恢复指南](README.md) · [交付证据与前提](../../docs/DELIVERY-2026-10-26.md)

本目录混有生产恢复 patch、历史注入器与回归资料；目录不搬，按下面区分。

| 路径 | 用途 |
|---|---|
| [patches/](patches/) + [replay_osc.py](replay_osc.py) | 01–17 正式恢复 payload 与唯一重放入口；只在另行获准的隔离源码树写入 |
| [test_replay_*.py](test_replay_osc.py) | 恢复契约、错误处理及集成的 unittest；完整集合由显式 runner 选择，不盲 discover |
| [fixtures/](fixtures/) | 带固定来源/hash 的压缩源码 preimages，不是可加载机架或生产模块 |
| [param_safety_harness/](param_safety_harness/) | 真实参数函数提取、ASan/UBSan 壳；56 场景与独审 10 组，非完整 Engine/GUI/插件 |
| [songroll_history_harness/](songroll_history_harness/) | 第16组完整 Module JSON history/UI 的串行真实方法测试；保留16的历史运行恢复规则 |
| [songroll_stopfirst_harness/](songroll_stopfirst_harness/README.md) | 第17组停止首段、并发争锁及取消规则；58 unittest 方法内含52 C++场景，不重复相加 |
| inject_osc_*.py / *.cpp.inc | 历史注入器/片段，非当前恢复入口；见[旧注入器说明](injectors-LEGACY-NOTES.md) |

## Recommended entry / 推荐入口

从仓库根使用 [tools/run_safety_regression.py](../run_safety_regression.py)，显式15个 suite，
最后记录295唯一方法通过（不是本次重跑）。`--help` 仅打印参数，不联系实机或运行测试。

```text
python -B tools/run_safety_regression.py --help
python -B tools/run_safety_regression.py --out D:/external-audit/run-001 --tmpdir D:/external-scratch --wsl-source /home/USER/Cardinal --jansson-include-dir /path/to/jansson-development/include
```

路径为占位示例。需要普通 Python 非 `-O`、python-osc/zstandard、Git、Windows + Ubuntu-26.04 WSL、
WSL python3/g++/pthread/真实 Jansson；`--wsl-source` 须含交付页列出的固定 rackwindows Git 对象，
只读 git show。输出全新且输出/scratch均在仓库外。缺前提失败，不 skip。
Python socket veto 在产品/测试导入前生效，不冒充 native 子进程网络 syscall 审计。

Jansson 目录**显式指定** `--jansson-include-dir` 或进程级 `JANSSON_INCLUDE_DIR`，必须是 Linux
绝对路径，同时含真实 `jansson.h` 和配套生成 `jansson_config.h`，且可链接 Linux `libjansson.so.4`。
系统包可显式指定 `/usr/include`，也可使用合法已配置依赖树；没有旧 lab 默认回退。
Windows runner 通过独立 `env` argv 传入 WSL，不改全局环境。详情见交付页。

## Standalone commands / 独立命令

以下在 WSL 中运行，从 Linux 可访问的仓库根执行，输出目录放仓库外且每次新建。
本次导航整理只核 CLI/源码，**没有执行编译、场景或实机操作**。

```bash
python3 -B tools/osc_patch/songroll_history_harness/run.py --help
python3 -B tools/osc_patch/songroll_history_harness/run.py --out /path/to/new/history-output --jansson-include-dir /path/to/jansson-development/include
python3 -B tools/osc_patch/songroll_stopfirst_harness/run.py --help
python3 -B tools/osc_patch/songroll_stopfirst_harness/run.py --out /path/to/new/stopfirst-output --jansson-include-dir /path/to/jansson-development/include
```

两个 SongRoll runner 使用仓库内 `reference/`，不依赖临时 workspace。原始参考通过
`sources.json` 等 manifest 固定；`--reference` 仅在明确审阅替代来源时使用。
ASan/UBSan 不等于竞态检测；TSan 是独立证据层，不增加 unittest 数量。

参数 harness 是位置参数脚本，**没有 `--help`**，不要将它当通用 CLI 运行。
需要额外准备按固定对象完整应用01–15的独立源码树（含 Rack 源码），并使用 g++ C++17、pthread、ASan/UBSan：

```bash
python3 -B tools/osc_patch/param_safety_harness/run_56.py /path/to/isolated/after15 /path/to/new/param-56-output
python3 -B tools/osc_patch/param_safety_harness/run_review_10.py /path/to/isolated/after15 /path/to/new/param-review10-output
```

位置参数按源码核对；两个脚本会创建/编译输出，不能以现役源码作为输出，也不以 scratch 残留作为前提。
统一295方法入口不声称每次自动运行这两套额外 standalone 参数壳或完整恢复/Native构建。

## Source and certification boundaries / 来源与验收边界

`*_harness/reference` 和压缩 fixtures 是上游/补丁后源码快照，用来提取真实方法，
**不是 production 插件、不是可直接加载运行的模块**。SongRoll/plugin 来自 rcm-modules 固定基线加补丁；
Engine 为 Cardinal override，Module/history/digital 来自 Rack，AddrSeq 来自 BogaudioModules。
保留原源码头并适用上游许可，不宣称这些第三方源码为本项目原创或被 MIT 重新授权。
精确来源及 hash 契约见[交付页](../../docs/DELIVERY-2026-10-26.md)和各 manifest。

Widget/布局、注册表、部分 Engine/端口等由测试壳替换；真实方法通过提取运行不代表完整窗口、
音频设备、插件生命周期或硬实时已验。第16历史 fixture 与第17 stop-first 规则分别验证，不能混用。
当前有限部署/实机与待验范围统一查交付页，不继承旧版声音或全库通过结论。
