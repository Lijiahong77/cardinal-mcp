# Cardinal OSC 远程控制「默认开启」调研

> 日期：2026-10-18
> 目的：查清为什么 Cardinal 的 OSC 远程控制每次启动都要手动点 `Engine → Enable OSC`，
>       以及有没有办法让它默认打开。
> 结论：当前**无法**默认打开（是设计局限，不是配置错误）；本次决定**暂不修改源码**，
>       仅落盘备查。

## 0. 结论（先看）

- Cardinal 的 OSC 远程控制开关**不能默认开启、也不跨重启持久化**。每次启动 Cardinal 都要手动点
  `Engine → Enable OSC remote control`，否则基于 OSC 的远程控制（包括 `cardinal_mcp` 推机架）全部无反应。
- 这不是「配置错了」或「被源码拒绝」，而是 **Cardinal 没有把 OSC 开关做成可持久化 / 默认开启**，
  且开启时还要弹一个端口确认框。
- 三条落地路（改源码 / AutoHotkey 启动器 / MCP 握手引导）见 §5。**当前决定：暂不实施，保持现状**
  （用户考量可能有更深层的设计意图，先不动源码）。

## 1. 现象与影响

- 你用的「remote control 那个东西」= Cardinal 引擎 OSC 远程控制；`cardinal_mcp`（MCP server）通过它向
  运行中的 Cardinal 发 `/load`、`/param`、`/hello` 等 OSC 消息。
- 端口：默认 UDP **2228**（与 `mcp.example.json` 的 `CARDINAL_PORT=2228` 一致）。
- 现象：Cardinal 启动后，若没手点 `Engine → Enable OSC`，MCP 推机架会「发送成功但收不到回复」
  —— `load_patch` 返回 `note: sent but no reply (Cardinal OSC off? wrong port?)`。
- 影响：每次开 Cardinal 都要多一步手动操作，是工作流里反复摩擦的点。

## 2. 根因：三处真数据交叉验证

1. **cardinal_mcp.py 注释明说**（`D:/Cardinal/tools/cardinal_mcp.py` 第 27–31 行）：
   > Cardinal standalone must have OSC enabled manually: `Engine -> Enable OSC remote control`
   > (default UDP port 2228). This toggle is **NOT persisted across restarts** — the user has
   > to click it every time they launch Cardinal.
2. **Cardinal 配置文件里没有 OSC 字段**：`C:/Users/lijia/Documents/Cardinal/native.json`
   （Cardinal 的设置文件）通读一遍，全是窗口 / 主题 / 采样率 / 模块收藏等，**完全没有 OSC /
   engine / remote 相关字段**。说明 OSC 开关是纯运行时内存状态，不落盘。
3. **源码确认开关位置与行为**（WSL 源码 `/home/lijia/Cardinal/src/override/MenuBar.cpp`）：
   - 第 755 行就是那个菜单项 `createMenuItem("Enable OSC remote control", remoteControlText, ...)`。
   - 状态存于 `remoteServerStarted`（MenuBar 对象的成员），没有任何写回 settings 的代码，
     也没有启动时读取并 enable 的逻辑。
   - 整个 OSC 菜单项被 `#ifdef HAVE_LIBLO` 包裹，只在 standalone 且编译进 liblo 时才有。

## 3. OSC 开关的实现细节（MenuBar.cpp:740–778）

- 它是 **nanogui 自绘菜单**（Cardinal 重写了 `MenuBar.cpp`，放在 `src/override/` 下），
  **不是 Windows 系统菜单**。所以连「自动点菜单」都得模拟屏幕坐标，不能用系统的菜单 API。
- 点击逻辑（简化）：
  ```cpp
  if (remoteServerStarted) {
      plugin->stopRemoteServer();
      remoteServerStarted = false;
  } else {
      async_dialog_text_input("OSC network port", CARDINAL_DEFAULT_REMOTE_PORT, [=](char* port) {
          if (port && plugin->startRemoteServer(port)) remoteServerStarted = true;
          std::free(port);
      });
  }
  ```
- **关键细节：开启时还会弹一个「OSC network port」文本输入框**（默认 `2228`），要再确认端口才真正
  `startRemoteServer(port)` + `remoteServerStarted=true`。所以即便自动点击，也得再过一道端口确认框。
- `CARDINAL_DEFAULT_REMOTE_PORT` 即 2228，与 MCP 配置一致。

## 4. 为什么不能「默认打开」（以及「是否被拒绝」的澄清）

技术上不能默认开，原因有三：

1. **无持久化**：开关只存在 `remoteServerStarted` 这个运行时布尔里，没有任何代码把它写入
   `native.json` 或任何配置文件。
2. **无命令行参数 / 环境变量**：源码里没有读取类似 `--osc` 或 `CARDINAL_OSC` 来启动时自动
   enable 的入口。
3. **开启路径带确认框**：enable 不是一步到位，而是弹端口框，更难「静默默认开」。

**澄清一个误解**：源码并不是「主动拒绝」远程启动。那段 `if (remoteServerStarted)` 只是普通的
on/off toggle，没有任何「禁止 / 拒绝 / 锁定」逻辑。准确说法是——**Cardinal 从来没把 OSC 做成
「可持久化 / 默认开启」的功能**，沿用的是 Rack 2 一贯的「连接外部世界的能力由用户显式开启」的设计。

**为什么作者可能故意不默认开（以下为基于代码与 Rack 生态的推测，非作者明示）**：

- **安全面**：OSC 监听一个 UDP 端口是网络暴露面，默认开等于每次启动都开一个可被本机任何程序
  发送的通道（虽然只绑 localhost，但 localhost 上的其他软件 / 网页也能发）。
- **端口冲突**：让用户显式确认端口，避免和已占用的 2228 撞车。
- **设计哲学**：Rack/Cardinal 把音频设备、MIDI、OSC 这类「接通外部世界」的能力都做成手动点
  Enable（`native.json` 里 `Enable Audio Input` / `Enable/Reconnect MIDI` 也是同样的手动机制），保持一致。
- **历史沿继**：Rack 2 的 OSC 一直以来都是手动 enable，Cardinal fork 没改这一行为。

> ⚠️ 以上关于「为什么」为推测。Cardinal 作者没有在代码或文档里写明理由。若想确认，可去
> Cardinal 的 GitHub / issue 直接问作者（Distrho/Cardinal）。

## 5. 三条落地路（备查，当前不实施）

> 用户已决定「先别动源码」，以下仅作为未来若想改时的方案存档。

- **A. 改源码 + 重编（最稳、一劳永逸）**
  - 改动点：在 standalone 初始化处（如 `CardinalUI.cpp` 的 standalone 启动路径，或 MenuBar 构造后）
    加一句「若 `!remoteServerStarted` 则 `plugin->startRemoteServer(CARDINAL_DEFAULT_REMOTE_PORT)`
    并置 `remoteServerStarted=true`」。
  - 可选做成环境变量开关（如 `CARDINAL_OSC_AUTOSTART=1`），默认关闭、不破坏现有行为。
  - 代价：需 WSL2 编译（环境已有）；上游更新时要 rebase 这个 patch。
  - 优点：精确、不依赖 GUI 自动化、永久生效，还能顺手跳过端口确认框。

- **B. AutoHotkey 启动器（成本最低、不动源码）**
  - 写 `.ahk`：启动 `CardinalNative.exe` → 等窗口 → 模拟点 Engine 菜单 → 点 Enable OSC
    → 在端口弹框按回车确认。
  - 代价：自绘菜单 + 端口弹框两道关，窗口位置 / 缩放一变就可能点歪；有零点几秒延迟。

- **C. MCP 侧握手引导（不算默认开，仅兜底）**
  - `ping` 失败时自动提示「请点 Engine→Enable OSC」，附菜单坐标 / 截图。
  - 但 OSC 关着时没法用 OSC 自己开（鸡生蛋），只能当兜底提示。

## 6. 现状与 workaround

- 当前做法：每次启动 Cardinal 后，手动点 `Engine → Enable OSC remote control`（弹框直接回车用默认 2228）。
- 验证是否真的开了：MCP 侧 `cardinal_ping` 能收到 `/resp` 即说明 OSC 已开；或看
  `tools/winprobe.py`（cardinal_mcp 注释提到的端口监听探测脚本）确认 2228 在监听。
- 备注：若嫌每次手点烦，优先级最低、零风险的折中是方案 C（MCP 在 ping 失败时给明确指引），
  不碰源码、不改行为。

## 7. 证据索引

- `D:/Cardinal/tools/cardinal_mcp.py` 第 27–31 行（注释）、第 82–83 行（端口 2228）、
  第 223–247 行（load_patch 的 OSC 路径与「无回复」提示）。
- `C:/Users/lijia/Documents/Cardinal/native.json`（配置文件，无 OSC 字段）。
- WSL 源码 `/home/lijia/Cardinal/src/override/MenuBar.cpp` 第 740–778 行（OSC 菜单项与开关逻辑）、
  `src/override/diffs/MenuBar.cpp.diff`。
- `D:/Cardinal/mcp.example.json`（`CARDINAL_PORT=2228`）。
