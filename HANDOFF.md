# HANDOFF · Cardinal MCP 项目交接 / 开工说明书

> **最后更新：2026-10-21 10:52**（E3 完工 + 待办总表清空 + WSL 树状态复核订正 + `.bak` 清理）
>
> **用途**：新会话、压缩后的上下文、或任何一个第一次接手的人，**只读这一份就能开工**。
> 细节都指向 `docs/` 里的权威文档，这里只放「结论 + 可直接照抄的命令」。
>
> **读法**：§0 速览 → §1 现状 → §2 照抄命令开工 → 卡住了再看 §5 的坑。

---

## 0. 30 秒速览

| 问题 | 答案 |
|---|---|
| **这是什么项目** | 给 Cardinal 模块化合成器加一套 **MCP 遥控能力**（**54 个工具**）+ **OSC 端点**（**28 个**），让 AI 能在软件里读状态、改机架、加模块、导出乐谱。 |
| **现在能用吗** | **能。** 部署的 `D:\Cardinal\win64\CardinalNative.exe` 已通过真机验收（10-21 10:08 构建，含 E1 三段式 + E2 分页 + E3 注册表抽函数）。 |
| **最需要注意什么** | ① `D:\Cardinal` 是你的 fork（可 push）；WSL 的 `~/Cardinal` 是上游 clone（**绝不能 push**）。<br>② WSL 源码树**已经是「带 OSC 的可编译状态」**（10-21 实测：28 端点注册全在）⇒ 改完直接编；但 `git checkout .` 会把 OSC 改动冲掉（`MenuBar.cpp` 的自动开 OSC 补丁不在任何注入器里，**尤其别丢**）。<br>③ 改 `.vcv` 只写文件**李看不见**，要走 OSC `/load` 推送。 |
| **明天第一件事** | 把本地那个还没推的提交推上去：`cd /d/Cardinal && git push origin main`（见 §2.1）。 |
| **最权威的三份文档** | `HANDOFF.md`（本文件，怎么开工）· `docs/TODO-BACKLOG.md`（还有什么没做）· `docs/CARDINAL-MCP-CAPABILITY-MAP.md`（每个工具/端点对应哪段源码） |

---

## 1. 当前状态（2026-10-20 17:00）

### 1.1 ✅ 已就绪、可直接用

| 项 | 实际状态 / 位置 |
|---|---|
| **MCP 工具** | **54 个**（`tools/cardinal_mcp.py`，TOOLS == DISPATCH 已校验） |
| **OSC 端点** | **28 个**（A 组读数 5 / B 组零 hook 5 / C 组模拟人类操作 9 + QuickJS 2 / D 组 `/screenshot` 1 / E 组 E1 三段式 + E2 分页 1 + E3 注册表重构） |
| **部署的 exe** | `D:\Cardinal\win64\CardinalNative.exe`，**103,001,088 B**，MD5 `608c94aaa22c48f17c85c8a90d6ff522`，构建于 10-21 10:08（含 E1 三段式 + E2 分页 + E3 注册表抽函数 + 自动开 OSC 延后） |
| **OSC 自动开启** | 已生效（`CARDINAL_OSC_AUTOSTART` 未设或 ≠ `0` 时，启动即开 2228 端口，不用再手点菜单） |
| **MCP 注册** | `C:\Users\lijia\.workbuddy\mcp.json`，server 名 `cardinal` |
| **机架资产** | `patches/` 下 **53 个 `.vcv`**；已验收成品见 §6.3 |
| **Python 环境** | `C:\Users\lijia\.workbuddy\binaries\python\envs\music-ai\Scripts\python.exe`（已装 `python-osc` + `zstandard`，实测 OK） |

### 1.2 ⚠️ 未就位 / 待处理

| 项 | 状态 |
|---|---|
| **Git 推送** | 本地 `main` 已与 `origin/main` 同步（2026-10-21 推了 `ef612be` + `6fd95f7`）。⚠️ 沙箱内 push 会被代理 502 挡住，需在沙箱外「清代理 + 直连」推（见 §2.1） |
| **WSL 源码树** | ✅ **已是「带 OSC 的可编译状态」**（2026-10-21 10:50 实测复核）。`src/CardinalCommon.cpp` 里 **28 个端点注册全在**，`CARDINAL_OSC_METHODS` X-macro 在、`/modules-page` 在，`src/override/MenuBar.cpp` 的延后 120 帧补丁也在 ⇒ **改完直接编即可，不必重跑 A→B→C→D 注入**。⚠️ 但它**不在任何注入器的可重放清单里**——`git checkout .` 会把 OSC 改动全冲掉（`MenuBar.cpp` 的补丁尤其危险，它不在任何注入器中） |
| **WSL 里的 MenuBar 自动开 OSC 补丁** | **仍在**（未提交，`src/override/MenuBar.cpp`）。它**不在任何注入器里**，整树 `git checkout .` 会丢掉 → 见 §2.3 |
| **E 组（协议级）** | **E1 三段式响应 ✅ / E2 分页 ✅ / E3 注册表抽函数 ✅ 全部完工**（E3 为纯重构：27 端点行为指纹与重构前逐条一致） |
| **其他待拍板** | life1 三修法、段落编排规格、`.mid` 导出 —— 见 §6 |
| **`.bak-*` 残留** | 已全清（41 个，WSL 树现 0 个） |

### 1.3 上一轮到底发生了什么（失败 / 搁置 / 回退到哪里）

**失败的是「脚本的可复现性」，不是功能。**
`tools/osc_patch/inject_osc_d.py` 有两个真 bug，导致它**无法在干净 upstream 上重放**部署态：

1. `D2_LOAD_HANDLER_NEW` 的函数签名被写错（丢了具名参数 `types/argv/argc`，函数体却还在用）→ **编译不过**。
2. `D2-fromjson-dialog` 的锚点（OLD）多了一行上游根本不存在的 `warningLog = "";` → 干净树重放时这一条**直接失败**。

这两个 bug 的副作用就是 **WSL 工作树被污染**：坏的幂等逻辑让注入器重复插入，顶层 `CardinalCommon.cpp` 多出 7 行重复的 `/screenshot` 注册，并留下 33 个 `.bak-*`。

**已修并验证**：干净 upstream 树首次应用 **54 条规则 0 失败**；第二次运行 **幂等 no-op**；`--check` 全就位、无重复、副本一致。

**搁置 / 放弃的只有两样：**

- 放弃「WSL 源树里保留带 OSC 的可编译状态」→ 选择整棵回退到干净 upstream（下次要重编就重新注入）。
- 「变体作用域」问题不再需要讨论 —— 见 §4.2，**6 份变体是符号链接**，改顶层就自动覆盖全部变体。

**回退到了哪里：**

- WSL `~/Cardinal/src` 的 7 个 D 受影响文件 → `git checkout HEAD --` → **干净 upstream**。
- 部署的 exe **不受影响**（来自更早的干净构建，仍带 OSC）。
- `MenuBar.cpp`、`plugins/`、各 submodule 等无关改动 **保留未动**。

> ⚠️ **上面这段是 10-20 的历史叙述，现状已经变了** —— 10-21 E2/E3 注入时又把 A→B→C→D→E1→E2→E3 全部打进 WSL 树，**现在那棵树是带 OSC 的可编译状态**（实测 28 端点注册全在）。⇒ **下次重编不用重注入**。但它**不在任何注入器的可重放清单里**：`git checkout .` 会把 OSC 改动冲光，其中 `src/override/MenuBar.cpp` 的自动开 OSC 补丁**任何注入器都不会给你装回去**，只能手工重打。

---

## 2. 明天开工 SOP（命令可直接照抄）

### 2.0 环境前提

- Windows 侧用 **Git Bash**（本文命令都是 bash 语法）。
- WSL 发行版能进：`wsl.exe -e bash -lc 'echo ok'`。
- 若 Bash 报 `command not found`，先补 PATH：
  ```bash
  export PATH="/c/Windows/System32:/c/Windows:/usr/bin:/bin:$PATH"
  ```

---

### 2.1 推送（沙箱内会 502，务必在沙箱外清代理直连）

**前提**：沙箱内 `https_proxy=127.0.0.1:13115` 只放行 `api.github.com`、挡 `github.com:443`（CONNECT 502）；`unset` 代理后沙箱内直连又会超时。所以要**在沙箱外**执行：

```bash
cd /d/Cardinal
git status -sb          # 应显示 ## main...origin/main [ahead N]
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
git push origin main
git status -sb          # 成功后会变成不显示 ahead
```

> ssh 22 端口通，但本机没配公钥（`Permission denied (publickey)`），SSH 通道走不通。
> `gh` CLI 只连 `api.github.com`，能 `gh repo view` 但不能替 `git push`。
> 所以唯一可靠路径 = 走 `/commit-push-pr` 命令（它会挑沙箱外直连），或手动在 GitHub Desktop / 本机终端推。

---

### 2.2 第二步：只在 Windows 侧改 Python / 用 MCP（**不需要编译**）

绝大多数「加工具 / 改机架 / 查数据」的活儿都在这一层，**完全不用碰 WSL**。

```bash
cd /d/Cardinal

# 列工具（应看到 54 个）
"C:/Users/lijia/.workbuddy/binaries/python/envs/music-ai/Scripts/python.exe" \
  D:/Cardinal/tools/cardinal_mcp.py --tools

# 自检：OSC 通不通、Cardinal 在不在
"C:/Users/lijia/.workbuddy/binaries/python/envs/music-ai/Scripts/python.exe" \
  D:/Cardinal/tools/cardinal_mcp.py --selftest

# 直接调一个工具（不经过 MCP 客户端）
"C:/Users/lijia/.workbuddy/binaries/python/envs/music-ai/Scripts/python.exe" \
  D:/Cardinal/tools/cardinal_mcp.py --call cardinal_ping

# 截图（D1 新能力：落盘 + 回路径）
"C:/Users/lijia/.workbuddy/binaries/python/envs/music-ai/Scripts/python.exe" \
  D:/Cardinal/tools/cardinal_mcp.py --call cardinal_screenshot
```

前提：**Cardinal 正在运行**，且 OSC 已开。部署版会自动开（见 §4.4）；如果 `--selftest` 超时，先确认 2228 端口：

```bash
netstat -ano | findstr 2228
```

---

### 2.3 第三步：要重编（把 OSC 改动重新注入源码树）

> 只有「改了 C++ / 要新 OSC 端点 / 要新编译产物」才需要这一步。**注入器必须在 WSL 里跑**（它写的是 `/home/lijia/...`）。

**① 进 WSL，确认树是干净的：**

```bash
wsl.exe -e bash -lc '
  cd ~/Cardinal &&
  git -C . status --short src/CardinalCommon.cpp src/CardinalCommon.hpp src/override/Window.cpp src/override/Engine.cpp &&
  git -C src/Rack status --short include/settings.hpp src/settings.cpp src/patch.cpp &&
  echo "(以上应为空 = 干净)"
'
```

**② 按 A → B → C → D 顺序注入（顺序不能乱，后一组依赖前一组）：**

```bash
wsl.exe -e bash -lc '
  cd ~/Cardinal &&
  python3 /mnt/d/Cardinal/tools/osc_patch/inject_osc_read.py &&
  python3 /mnt/d/Cardinal/tools/osc_patch/inject_osc_b.py &&
  python3 /mnt/d/Cardinal/tools/osc_patch/inject_osc_c.py &&
  python3 /mnt/d/Cardinal/tools/osc_patch/inject_osc_d.py
'
```

**③ 验证（四条都应是 OK / 已注入 True）：**

```bash
wsl.exe -e bash -lc '
  python3 /mnt/d/Cardinal/tools/osc_patch/inject_osc_read.py --check &&
  python3 /mnt/d/Cardinal/tools/osc_patch/inject_osc_b.py --check &&
  python3 /mnt/d/Cardinal/tools/osc_patch/inject_osc_c.py --check &&
  python3 /mnt/d/Cardinal/tools/osc_patch/inject_osc_d.py --check
'
```

`inject_osc_d.py --check` 的正确输出大致是：

```
全部就位、无重复、副本一致 ✔
```

> 重复跑是安全的：A/B/C 看到 marker 会 `[skip]`；D 是幂等的（已存在即跳过）。
> 要撤销某一组：给对应脚本加 `--rollback`（按文件 stem 取最新备份还原）。

**④ 如果整棵树被 `git checkout .` 重置过，补回「启动自动开 OSC」补丁**（它不在注入器里）：

先检查：

```bash
wsl.exe -e bash -lc 'grep -c "oscAutostartEnabled" ~/Cardinal/src/override/MenuBar.cpp'
```

- 输出 `1`（或更大）→ 补丁还在，跳过本步。
- 输出 `0` → 需要重贴。补丁内容见 §2.3.1，贴进 `src/override/MenuBar.cpp` 的三处位置。

#### 2.3.1 MenuBar 自动开 OSC 补丁（原样）

```diff
--- a/src/override/MenuBar.cpp
+++ b/src/override/MenuBar.cpp
@@ -27,6 +27,7 @@
 #include <thread>
 #include <utility>
+#include <cstdlib>

 #include <app/MenuBar.hpp>
 #include <app/TipWindow.hpp>
@@ -730,6 +731,23 @@ struct ViewButton : MenuButton {
 struct EngineButton : MenuButton {
 #ifdef HAVE_LIBLO
 	bool remoteServerStarted = false;
+	bool oscAutostartAttempted = false;
+	int  oscAutostartFrames = 0;
+#endif
+
+#ifdef HAVE_LIBLO
+	// OSC remote control autostart: enabled when CARDINAL_OSC_AUTOSTART is unset or != "0",
+	// disabled when explicitly set to "0" (manual menu toggle keeps working).
+	bool oscAutostartEnabled() {
+		const char* const env = std::getenv("CARDINAL_OSC_AUTOSTART");
+		return env == nullptr || env[0] != '0';
+	}
+
+	void startOsc() {
+		CardinalPluginContext* const context = static_cast<CardinalPluginContext*>(APP);
+		CardinalBasePlugin* const plugin = static_cast<CardinalBasePlugin*>(context->plugin);
+		if (plugin != nullptr && plugin->startRemoteServer(CARDINAL_DEFAULT_REMOTE_PORT))
+			remoteServerStarted = true;
+	}
 #endif

 	void onAction(const ActionEvent& e) override {
@@ -818,6 +836,16 @@ struct EngineButton : MenuButton {
 	void step() override {
 		MenuButton::step();

+		// Autostart after the UI has settled: starting liblo's server thread on
+		// the very first frames races with GL/audio init (observed as a robust
+		// mutex assertion under Wine). Wait ~120 frames (~2 s at 60 fps).
+		if (!oscAutostartAttempted) {
+			++oscAutostartFrames;
+			CardinalPluginContext* const context = static_cast<CardinalPluginContext*>(APP);
+			if (context != nullptr && context->plugin != nullptr && oscAutostartFrames >= 120) {
+				oscAutostartAttempted = true;
+				if (isStandalone() && oscAutostartEnabled())
+					startOsc();
+			}
+		}
+
 		if (remoteServerStarted) {
 			CardinalPluginContext* const context = static_cast<CardinalPluginContext*>(APP);
 			CardinalBasePlugin* const plugin = static_cast<CardinalBasePlugin*>(context->plugin);
```

保存后复查：

```bash
wsl.exe -e bash -lc 'grep -c "oscAutostartEnabled" ~/Cardinal/src/override/MenuBar.cpp'
```

---

### 2.4 第四步：编译（只编 Windows 用的 Native 变体）

> **先关掉 Cardinal**，否则 exe 被锁住无法替换。
> **只编 `CardinalNative`**，别跑顶层 `make all`（会撞 LV2/`CardinalMiniSep` 的既有失败）。

```bash
wsl.exe -e bash -lc '
  cd ~/Cardinal &&
  source deps/PawPaw/local.env win64 &&
  echo "CC=$CC" &&
  echo "CXX=$CXX" &&
  cd src &&
  xvfb-run -a make -C CardinalNative;
  echo "MAKE_EXIT=$?"
'
```

**如果改了 `src/override/Engine.cpp` 或 Rack 层**（D2 就改过），先重编 `rack.a` 再编变体：

```bash
wsl.exe -e bash -lc '
  cd ~/Cardinal &&
  source deps/PawPaw/local.env win64 &&
  xvfb-run -a make -C src rack.a &&
  xvfb-run -a make -C src/CardinalNative;
  echo "MAKE_EXIT=$?"
'
```

成功判据：

- `MAKE_EXIT=0`
- `~/Cardinal/bin/CardinalNative.exe` 时间戳是刚才

```bash
wsl.exe -e bash -lc 'ls -l --time-style=long-iso ~/Cardinal/bin/CardinalNative.exe'
```

**常见失败**：`undefined reference to rack::...` / `file format not recognized`
→ 是「Linux 版 make 的 ELF `.o` 混进了 Windows 链接」。按 §5.4 精准清掉 ELF `.o` 再编。

---

### 2.5 第五步：部署到 Windows 现役目录

```bash
wsl.exe -e bash -lc '
  TS=$(date +%Y%m%d-%H%M%S) &&
  cp -p /mnt/d/Cardinal/win64/CardinalNative.exe "/mnt/d/Cardinal/win64/CardinalNative.${TS}-old.exe" &&
  cp /home/lijia/Cardinal/bin/CardinalNative.exe /mnt/d/Cardinal/win64/CardinalNative.exe &&
  md5sum /home/lijia/Cardinal/bin/CardinalNative.exe /mnt/d/Cardinal/win64/CardinalNative.exe
'
```

两个 MD5 必须一致。`win64/Cardinal.exe` 是 **JACK 版，别用**。

---

### 2.6 第六步：验证（数据为主，画面最后看一眼）

```bash
# 1) MCP 自检
"C:/Users/lijia/.workbuddy/binaries/python/envs/music-ai/Scripts/python.exe" \
  D:/Cardinal/tools/cardinal_mcp.py --selftest

# 2) 端点级探针
"C:/Users/lijia/.workbuddy/binaries/python/envs/music-ai/Scripts/python.exe" \
  D:/Cardinal/tools/cardinal_mcp.py --call cardinal_build_info

# 3) 截图（D1）
"C:/Users/lijia/.workbuddy/binaries/python/envs/music-ai/Scripts/python.exe" \
  D:/Cardinal/tools/cardinal_mcp.py --call cardinal_screenshot
```

判据：

- `--selftest` 显示 OSC 可达、工具数对；
- `cardinal_build_info` 返回的构建时间 = 刚才编译的时间（证明换的是新 exe）；
- `cardinal_screenshot` 返回 PNG 路径且文件存在。

> ⚠️ **WINE 下截图全黑是环境限制，不是 bug**（llvmpipe 的 GL 前缓冲读回限制）。
> 真机（硬件 GL）才需要看画面内容。详见 `docs/TODO-BACKLOG.md` D1 条目。

---

## 3. 命令速查表

### 3.1 Windows（Git Bash）

| 目的 | 命令 |
|---|---|
| 看仓库状态 | `cd /d/Cardinal && git status -sb` |
| 推送 | `cd /d/Cardinal && git push origin main` |
| 列 MCP 工具 | `"C:/.../music-ai/Scripts/python.exe" D:/Cardinal/tools/cardinal_mcp.py --tools` |
| MCP 自检 | `"C:/.../music-ai/Scripts/python.exe" D:/Cardinal/tools/cardinal_mcp.py --selftest` |
| 调工具 | `"C:/.../music-ai/Scripts/python.exe" D:/Cardinal/tools/cardinal_mcp.py --call <tool> '{"k":1}'` |
| 查 OSC 端口 | `netstat -ano \| findstr 2228` |

### 3.2 WSL（`wsl.exe -e bash -lc '...'`）

| 目的 | 命令 |
|---|---|
| 看源码状态 | `cd ~/Cardinal && git status --short` |
| 注入 A→B→C→D | 见 §2.3 ② |
| 验证注入 | 见 §2.3 ③ |
| 编 Native | 见 §2.4 |
| 部署 | 见 §2.5 |
| 清 ELF `.o` | 见 §5.4 |
| 全量重编 | `bash /mnt/d/Cardinal/tools/cross_build_cardinal.sh 8 true`（约 10 分钟，日志 `~/cardinal_cross_build.log`） |

---

## 4. 关键事实（不知道会踩坑）

### 4.1 两个仓库，别推错

| 路径 | 身份 | 能不能 push |
|---|---|---|
| `D:\Cardinal` | **你的 fork**：`https://github.com/Lijiahong77/cardinal-mcp.git` | ✅ 能，`origin/main` |
| WSL `~/Cardinal` | **上游 clone**：`DISTRHO/Cardinal` | ❌ **绝不能 push** |

两者**不是同一棵树**：`D:\Cardinal` 放工具/文档/机架；WSL 那棵才是要编译的 C++ 源码。
源码改动通过 `tools/osc_patch/*.py` 注入到 WSL 树，**不**靠 git 同步。

### 4.2 6 份变体文件是符号链接（2026-10-20 新确认）

```
src/CardinalCommon.cpp                ← 真文件
src/Cardinal/CardinalCommon.cpp       → ../CardinalCommon.cpp
src/CardinalNative/CardinalCommon.cpp → ../CardinalCommon.cpp
src/CardinalMini/...                  → ../CardinalCommon.cpp
src/CardinalFX/...                    → ../CardinalCommon.cpp
src/CardinalSynth/...                 → ../CardinalCommon.cpp
```

`Window.cpp` 同理，5 个变体全部指向 `../override/Window.cpp`。

**两个推论：**

1. **A/B/C 注入器只改顶层文件，就自动覆盖全部变体** —— 不需要逐份改。
2. **D 注入器遍历「6 份副本」时，实际写的是同一个文件 6 次** —— 这正是旧版重复插入 7 行 `/screenshot` 的根源。修好后的 D 靠「新内容已存在即跳过」保证幂等，**不会**再重复。

### 4.3 哪些是权威源

- **`.vcv` 文件**是唯一权威源；Cardinal 内存里的画面可能不同。
- 只改文件 **李看不见**；必须走 OSC `/load` 推送。
- Cardinal 运行时按 Ctrl+S 会把内存写回文件 → **改完文件要推一次**。
- 参数改动（`/param`）**不会**写回 autosave，所以**参数无法程序化回读**（只能靠显示值接口或看画面）。

### 4.4 OSC 开关

- 部署版**启动自动开** 2228（`CARDINAL_OSC_AUTOSTART` 未设或 ≠ `0`）。
- 想关掉自动开：启动前设 `CARDINAL_OSC_AUTOSTART=0`。
- 自动开是 `src/override/MenuBar.cpp` 的**未提交补丁**，不在注入器里（见 §2.3.1）。
- 手动开关仍在：`Engine → Enable OSC remote control`。

### 4.5 MCP 工具的生效时机

- `tools/cardinal_mcp.py` 改动后，**WorkBuddy 要重启 MCP server** 才会进工具列表。
- 急着用可以走命令行：`--call <tool>`，不依赖 MCP 客户端。

---

## 5. 最容易踩的坑（按杀伤力排序）

### 5.1 🔴 加载即崩：悬空接线

`leftModuleId` / `rightModuleId` 指向不存在的模块 → Cardinal 一加载就崩。
写机架一律 **deepcopy 一个能打开的机架**，只改 `id/pos/params/data`，别凭空构造。

### 5.2 🔴 一个输入口只能接一根线

后接的**静默挤掉**前面的：不报错、存档也看不出来。
要并流就进混音台空闲轨道，别抢同一个输入口。

### 5.3 🔴 旋钮值是归一化 0..1，不是物理量

`VCO.Frequency` 存的是半音参数（param2）；`Clocked`/`Gnome` 的 param0 才是绝对 BPM。
塞 Hz 进去 = 量纲错误 → 崩或哑。

### 5.4 🟡 `.o` 平台串味（Windows 链接报 undefined）

现象：`undefined reference to rack::...`、`file format not recognized`、找不到 `libarchive_static.a`。
根因：先跑过 Linux 版 make，ELF `.o` 被 Windows 链接复用。

精准清掉 ELF `.o`（**保留 mingw 的 PE/COFF `.o` 和 PawPaw 的 50 个 `.a`**）：

```bash
wsl.exe -e bash -lc '
  cd ~/Cardinal &&
  find . -name "*.o" -not -path "./deps/PawPaw/*" -print0 \
    | xargs -0 file \
    | grep "ELF 64-bit LSB relocatable, x86-64" \
    | cut -d: -f1 \
    | xargs -r rm -f &&
  echo "ELF .o 已清理"
'
```

然后按 §2.4 重编。

### 5.5 🟡 别跑顶层 `make all`

会撞 `CardinalMiniSep` / LV2 的既有失败，给人「全编不过」的错觉。
**只编 `make -C CardinalNative`**。

### 5.6 🟡 liblo 收不了 string 参数

发 string 正常，收 string 全哑。需要文本/JSON 的操作：
走 **JS 脚本文件 + 数值索引**（`/osc-js-run <index>`），脚本放 `js/` 目录。

### 5.7 🟡 JS 预算是「墙钟」不是指令数

默认 2000ms（`CARDINAL_JS_BUDGET_MS` 可覆盖）。别改回指令数——实测差 5 个数量级，会把 UI 线程永久卡死。
脚本被包成 IIFE，**用 `return` 交结果**。

### 5.8 🟡 WSL 命令输出会被当成二进制

`wsl.exe ... | grep` 偶尔报 `Binary file matches`（locale 警告混进 stdout）。
**先把输出重定向到文件再读**：

```bash
wsl.exe -e bash -lc '...' > /d/tmp/out.log 2>&1
```

### 5.9 🟡 低频先算频率，绝不进混响

低频（< 100Hz）先算好频率再写参数；低频信号不要送混响。
混响用 `Plateau`（Feline 是立体声滤波器，不是混响）。

### 5.10 🟡 布局只走 `layout_patch.py`

绝不手写 `pos`。`pos[0]` 单位是**格**，`pos[1]` 是**行号**。
`LAYOUT.json` 存坐标；改完跑 `extract_layout.py`；排版只走 `layout_patch.py`。

### 5.11 🟡 WINE 验证：用 WSLg 的 `DISPLAY=:0`，别用 Xvfb

`/tmp/.X11-unix` 是 WSLg 的**只读挂载**，`Xvfb :99` 建不了 socket（进程在、但连不上），
Wine 会在窗口创建阶段直接崩。正确做法：

```bash
DISPLAY=:0 CARDINAL_OSC_AUTOSTART=1 wine bin/CardinalNative.exe
```

另外 `pkill -f wineserver` 会匹配到**包含该字符串的 shell 自己**（命令自杀）⇒ 用 `pkill -x wineserver`。
进程名会被截断成 `CardinalNative.`，`pkill -x CardinalNative` 打不中 ⇒ 用 PID 或 `pkill -f 'bin/CardinalNative.exe'`（注意别打中自己的 shell）。

---

## 6. 待办 / 待拍板

### 6.1 技术待办

| 项 | 内容 | 状态 |
|---|---|---|
| **E1 · 三段式响应** | 采用**追加式** `/resp (tag, payload, status)`：payload 位置不动，旧客户端零破坏；status = `ok` / `err:<CODE>`（9 个码） | ✅ 已完工（WINE 14/14 + MCP 端到端） |
| **E2 · 分页** | 新增 `/modules-page "ii"`（offset, limit），旧 `/modules` 保留全量；payload = `<returned>/<total>\|<items>`，limit 上限 64 | ✅ 已完工（WINE 15/15 + MCP 端到端） |
| **E3 · 注册表抽函数** | 端点表抽成 **X-macro 单一真源**（`CARDINAL_OSC_METHODS(REG)`），thread/plain 各一个薄封装；两版入口后 3 参类型一致、只有第 1 参不同 ⇒ **零类型强转** | ✅ 已完工（纯重构：27 端点行为指纹与重构前逐条一致） |

> ⚠️ **E 组没有 E4**。`TODO-BACKLOG.md` 第三章出现的 E4~E10 是**另一套编号**（「已知错误与待澄清」：E4 = `/load` 的 skipped 列表拿不到、E8 = A3 死锁、E10 = 文档重复），**不是 E 组批次**，别看混。

### 6.2 已由李结案（2026-10-21 裁决，**不是待办**）

| 事项 | 裁决 | 备注 |
|---|---|---|
| **`.mid` 导出** | ⛔ 作废 | 李：「废了就不管它」。`.abc`（A10）已覆盖乐谱导出需求 |
| **段落编排规格（Song 模式）** | ⏸ 暂缓 | 李：「暂时也不用管，后面需要的时候我会再让你做」。⇒ MiniArranger **至今没有 Song 模式**（只有 pattern 循环）。⚠️ 将来开工前必须先问清三件事：段落表语法 / 和弦跨段落延续 / 段落切换时音色轨怎么变 —— 李没答过，**不得自行假设** |
| **life1 三修法** | ⛔ 不修 | 李：「Life1 那个不用修了」。且 10-17 已选**方案 B**（休止符+短时值）并交付 `quadeca_life1_wdtg.vcv`（李已确认有声）⇒ 记账上的「待选」是过时条目。残留备案：三层 `duration` 全 `None`（方案 B 的「短时值」那半未做）+ 混响仍是 `Feline`（纪律是 `Plateau`）—— 本批不做，且**不得重跑生成器**（会冲掉李手工调的布局） |

### 6.3 待李拍板（决定权在李，别替他定）

- **E 组优先级**：现在做还是等有需求再做（E1/E2/E3 已全完工，暂无 E4 候选）。

### 6.4 机架资产（文件名别写错）

```
patches/yorushika_hana.vcv        ✅ 已验收
patches/yorushika_shura.vcv       ✅ 已验收（另有 shura2 / shura_live）
patches/quadeca_life1_wdtg.vcv    ✅ 已验收
patches/quadeca_scrapyard.vcv     ✅ 已冻结（另有 _final）
patches/demo_S4_sampling.vcv      🟡 待验收
patches/demo_S5_fullkit.vcv       🟡 待验收
```

> ⚠️ 旧文档里写的 `yorushika_shura/hana` 是**错的**，实际是 `patches/yorushika_hana.vcv`（无目录层级）。

### 6.5 主线方向

**键盘即兴 + 风格自动伴奏**，核心是 **MiniArranger**：
HostMIDI 复音 8 声道分轨录和弦，4+4 循环，每轨独立音色链。
**不是** pianoroll 写死循环。键盘映射见 `docs/SMK25-midi-map.md`。

---

## 7. 文件地图

| 路径 | 作用 |
|---|---|
| `tools/cardinal_mcp.py` | **MCP 服务主体**，**54 个工具** + 命令行入口 |
| `tools/osc_patch/inject_osc_read.py` | A 组注入器（5 个读数端点） |
| `tools/osc_patch/inject_osc_b.py` | B 组注入器（5 个零 hook 端点） |
| `tools/osc_patch/inject_osc_c.py` | C 组注入器（9 个操作 + 2 个 JS 端点） |
| `tools/osc_patch/inject_osc_d.py` | D 组注入器（`/screenshot` + `/load` 回 warningLog） |
| `tools/osc_patch/inject_osc_e2.py` | E2 注入器（`/modules-page` 分页，依赖 E1+A 组） |
| `tools/osc_patch/inject_osc_e3.py` | E3 注入器（端点注册表抽 X-macro 单一真源；依赖 A/B/C/D/E1/E2） |
| `tools/osc_patch/*.inc` | 注入用的 C++ handler 源码 |
| `tools/rackgen.py` | 机架生成 DSL（新机架一律走它） |
| `tools/layout_patch.py` | 排班 + 门禁（`check` / `guard` / `apply` / `widths`） |
| `tools/topology.py` | 读接线 + 角色识别 + 信号可达性 |
| `tools/modbrowser.py` | 模块检索（含中文词表） |
| `tools/seq.py` | 序列器音符读写 |
| `tools/samplelib.py` | 采样槽装载 |
| `tools/abc_export.py` | 序列器 → `.abc` 乐谱 |
| `tools/cross_build_cardinal.sh` | 全量 Windows 交叉编译 |
| `tools/build_cardinal.sh` | 分阶段编译（deps/mini/plugins/full） |
| `js/*.js` | QuickJS 脚本（`/osc-js-run` 用） |
| `patches/*.vcv` | 53 个机架 |
| `docs/TODO-BACKLOG.md` | **待办总表**（还有什么没做） |
| `docs/CARDINAL-MCP-CAPABILITY-MAP.md` | 每个工具/端点 → 源码落点 |
| `docs/CARDINAL-MCP-SPEC.md` | 协议与端点规格 |
| `docs/SMK25-midi-map.md` | 键盘权威档案 |
| `docs/WSL2-BUILD-MANUAL.md` | WSL 编译手册 |
| `docs/UPSTREAM-WIN64-PORTABILITY.md` | 6 个可移植性缺陷 + 交叉编译 |
| `docs/CARDINAL-REBUILD-PLAN.md` | 重建步骤（含 MenuBar 补丁的设计说明） |
| `win64/CardinalNative.exe` | **Windows 现役可执行文件** |
| `~/.workbuddy/mcp.json` | MCP 注册（server 名 `cardinal`） |

---

## 8. 协作约定（李的偏好）

1. **别替他做决定**：岔路口把候选摆好、代价写清，决定权给他。
2. **不可逆操作先报后做**：磁盘、分区、系统配置、大批量删除、git 强推。
3. **文字要说人话**：结论放最前、术语首次出现给翻译、多用短句。
4. **同一文件的多处编辑要串行**：并行 Edit 同一文件会静默覆盖。
5. **交付格式跟项目惯例**：批改类任务先看同项目历史产物长什么样。
6. **验证以数据为主**：模块/端口/接线/参数一律读数据；画面只在最后看一眼。
7. **改机架前先存盘**：他的手工改动不能丢。
8. **动手前先查资料**：GitHub `patches/` → 本机 `docs/` → `refs/`，别凭空造。

---

## 附：一句话备忘

> **要重编，就先注入；要推机架，就走 OSC；推仓库，只推 `D:\Cardinal`。**
