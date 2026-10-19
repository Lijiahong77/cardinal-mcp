# Cardinal 重建 + OSC 自动开启 · 实施计划

> 日期：2026-10-18
> 用途：本计划交给他人执行。目标 = ① 干净重建 Windows Native 二进制，让 MiniArranger 面板修复真正生效；
> ② 改源码让 OSC remote control 默认开启（可用环境变量关闭）；③ 部署并验证。
> 本文件只描述做法，不替你改源码、不替你编译。

---

## 0. 结论（先读）

1. **编译本身能成功**：`CardinalNative` 单独编是过的（本次实测 `MAKE_EXIT=0`）。
   "老是报错"是宽构建里 `CardinalMiniSep`（LV2/MOD）在该 WSL 环境失败中断，与 Windows 用的 Native 无关。
2. **螺丝没对齐 ≠ 修复无效**：修复（`.cpp` + `MiniArranger.svg`）在磁盘上是对的，但**增量编译没把嵌入的 SVG 资源重编进二进制**，
   导致面板尺寸和螺丝算法用的是两版。必须 **clean rebuild Starsea 插件** 才能一致。
3. **OSC 自动开启只动一个文件**：`src/override/MenuBar.cpp`，加一个 env 开关，启动时跳过端口弹框直接 `startRemoteServer(2228)`。

---

## 1. 编译能否成功？（回答"会不会编不成功"）

**实测结论**：`make -C src/CardinalNative` 能成功（本次 `MAKE_EXIT=0`，产物落在 `bin/CardinalNative.exe`）。

**"老是报错"的真相**（来自 `src/Makefile` 与顶层 `Makefile`）：
- 顶层默认 `make` 的 `all` = `cardinal carla deps dgl plugins gen resources`（只编库/插件，**不含 standalone**）。
- standalone 走 `src/Makefile`：`native` / `mini` 等目标会顺带 `$(MAKE) -C CardinalMiniSep`（LV2/MOD，`lv2_sep`）。
  该步骤依赖 LV2/modgui 工具链，在本 WSL 环境会失败并中断，**给人"整个编不过"的错觉**。
- **Windows 实际用的 `CardinalNative` 不依赖 `CardinalMiniSep`**，直接 `make -C src/CardinalNative` 即可绕开失败。

**唯一需要警惕的坑（螺丝错位根因）**：
- MiniArranger 面板高度由 `res/MiniArranger.svg` 提供，该 SVG 是**编译期嵌入**插件的资源。
- 增量编译只重链、不重编 Starsea 的 `.o` 与嵌入资源对象，旧嵌入 SVG（128.5mm）可能残留在二进制里，
  而 `.cpp` 螺丝已用 `box.size.y`（147.3mm）→ 面板与螺丝算法错配 → 视觉错位。
- 解决：**删掉 `build/plugins/Starsea/` 整个目录再重编**，强制 `.cpp` + 嵌入 SVG 一起从 10-17 源码重编。

---

## 2. 改动一：OSC remote control 默认开启（源码）

**文件**：`src/override/MenuBar.cpp`

**现有开关机制（已确认行号/符号）**：
- `remoteServerStarted` 是 MenuBar 的成员 bool，声明于 `MenuBar.cpp:732`（`bool remoteServerStarted = false;`）。
- 菜单项构建在 `MenuBar.cpp:751-767`，仅在 `isStandalone()` 时出现：
  ```cpp
  CardinalPluginContext* const context = static_cast<CardinalPluginContext*>(APP);
  CardinalBasePlugin* const plugin = static_cast<CardinalBasePlugin*>(context->plugin);
  // ...
  menu->addChild(createMenuItem("Enable OSC remote control", remoteControlText, [=]() {
      if (remoteServerStarted) { remoteServerStarted = false; plugin->stopRemoteServer(); return; }
      async_dialog_text_input("OSC network port", CARDINAL_DEFAULT_REMOTE_PORT, [=](char* const port) {
          if (port == nullptr) return;
          if (plugin->startRemoteServer(port)) remoteServerStarted = true;
          std::free(port);
      });
  }));
  ```
- 默认端口常量 `CARDINAL_DEFAULT_REMOTE_PORT` = **2228**，与 `mcp.example.json` 里 `CARDINAL_PORT=2228` 一致 → 自动开启后 MCP 直接可用，无需手点。

**推荐改法（env 开关，默认开、可逆、不破坏默认行为）**：
- 新增环境变量 `CARDINAL_OSC_AUTOSTART`（未设置或 =1 时默认开启；显式设 0 则关闭，保留原手动行为）。
- 把上面 click lambda 里的"启动体"抽成一个成员函数 `startOsc()`（调 `plugin->startRemoteServer(CARDINAL_DEFAULT_REMOTE_PORT)` 并置 `remoteServerStarted=true`，**跳过端口弹框**）。
- 在 standalone 初始化、能拿到 `APP`/`plugin` 之处（例如 MenuBar 构造完成后或 App 初始化末尾）按 env 条件调用一次 `startOsc()`。
- 菜单点击逻辑保持不变（仍可手动开关/关闭）。
- 注意：`remoteServerStarted` 与 `plugin` 都来自 `APP` 上下文，自动开启代码必须放在 `APP` 已初始化之后。

**备选（更简单但略欠灵活）**：无条件在 standalone 初始化时直接 `startRemoteServer(2228)`，不读 env。优点少一行判断；缺点是关不掉、上游合并时默认行为变化更大。

**保持最小改动**：不要动开关的 on/off 逻辑本身，只在"启动路径"上多一条自动触发分支。

---

## 3. 改动二：确保 MiniArranger 修复编入（clean rebuild）

**根因**：SVG 是编译期嵌入资源；增量编译会跳过 Starsea 的 `.o` 与嵌入对象，旧 128.5mm SVG 残留在二进制。
**磁盘上的修复本身是对的**（已核对）：
- `res/MiniArranger.svg`：`height="147.30"`（10-17 改，40HP×147.3mm / 435px）。
- `src/MiniArranger.cpp`：螺丝由写死 `RACK_GRID_HEIGHT` 改为 `box.size.y`（10-17 改），注释明说高度只能靠改 SVG + 三块底板矩形。

**做法**：删除该插件的整个构建缓存后重编，强制重编 `.cpp` 与嵌入 SVG：
```
rm -rf build/plugins/Starsea
```
然后按 §4 重编 `CardinalNative`。

---

## 4. 编译步骤（精确命令，在 WSL 内执行）

前置：
- **先关闭 Cardinal**（Windows 会锁住 `win64/CardinalNative.exe`，否则无法替换）。
- 确认 WSL 内仓库路径 `/home/lijia/Cardinal`，且 `deps/PawPaw/local.env` 存在。

命令：
```bash
cd /home/lijia/Cardinal
source deps/PawPaw/local.env win64
# 改动一已写入 MenuBar.cpp；下面 clean rebuild 同时覆盖改动二
rm -rf build/plugins/Starsea
cd src
xvfb-run -a make -C CardinalNative
echo "MAKE_EXIT=$?"
```
检查：
- `MAKE_EXIT=0`；
- `bin/CardinalNative.exe` 时间戳为本次编译时刻。

> 不要跑顶层 `make all` 或带 `CardinalMiniSep` 的目标，那会触发 LV2 失败。只编 `CardinalNative`。

---

## 5. 部署（落到 Windows 实际启动的文件）

1. 备份当前正在用的二进制（保留时间戳，便于回滚）：
   ```
   cp -p /mnt/d/Cardinal/win64/CardinalNative.exe \
        /mnt/d/Cardinal/win64/CardinalNative.<YYYYMMDD-HHMMSS>.exe
   ```
2. 复制新编的覆盖：
   ```
   cp /home/lijia/Cardinal/bin/CardinalNative.exe /mnt/d/Cardinal/win64/CardinalNative.exe
   ```
3. **确认用户启动的就是这个 exe**：核对 `win64/CardinalNative.exe` 的 md5 与
   `bin/CardinalNative.exe` 一致；注意桌面快捷方式/其他目录是否有**另一份旧副本**，若有需同步替换或改指向。

---

## 6. 验证（数据为主 + 最后看一眼画面）

**A. 构建成功（数据）**：`MAKE_EXIT=0`；新旧 exe md5 不同。
**B. OSC 自动开启（数据）**：启动 Cardinal（**不点** Engine→Enable OSC），用 `cardinal_mcp` 的 ping /
`cardinal_ping` 探测 UDP 2228 是否有响应。有响应 = 自动开启生效。
**C. MiniArranger 螺丝（画面，数据证明不了）**：打开含 `Starsea-MiniArranger` 的机架
（如 `patches/yorushika_shura.vcv` / `yorushika_hana.vcv`），看面板**底部两颗螺丝是否落在面板底边**
（面板应为 147.3mm / 435px 高）。对齐 = 修复生效。
**若 C 仍错位**：说明嵌入 SVG 仍陈旧 → 回到 §3，确认 `build` 日志里 `MiniArranger.cpp.o` 与
Starsea 的**资源对象**被重新编译（而不只是重链），必要时手动删 `build/plugins/Starsea` 再编。

---

## 7. 回滚

- `win64/CardinalNative.<时间戳>.exe` 是 9-23（或更早）的备份，出问题直接换回。
- 源码改动：Starsea 是 untracked 目录（改动在文件里，不在 git 跟踪），OSC 改动在 `MenuBar.cpp`（可用 `git diff` 查看、`git checkout` 还原）。

---

## 8. 风险与注意

- **Windows standalone 音频输入有 bug**：现场演奏建议用插件（DAW）形态，不要靠 standalone 麦克风输入。
- **CPU**：反馈/共鸣类模块（Rings/Elements）吃负载，定稿后冻结或打印音轨。
- **上游 rebase**：这两个 patch（MiniArranger 修复 + OSC 自动开启）是本地改动，拉上游更新时要保留/重放。
- **多份 exe**：务必确认"正在启动的那份"被替换，否则会误以为修复没生效。

---

## 9. 证据索引（供核查）

- `src/override/MenuBar.cpp`：`remoteServerStarted` 声明 L732；OSC 菜单块 L751-767；`startRemoteServer` L766；`CARDINAL_DEFAULT_REMOTE_PORT` L762。
- `res/MiniArranger.svg`：`height="147.30"`（rect 行）；`MiniArranger.cpp.bak-1017` vs 当前：螺丝改 `box.size.y`（diff 已核对）。
- `build/plugins/Starsea/src/*.cpp.o`：mtime 2026-10-17 10:35（修复当次编的，但嵌入资源对象可能更旧）。
- `mcp.example.json`：`CARDINAL_PORT=2228` ↔ `CARDINAL_DEFAULT_REMOTE_PORT`。
- `src/Makefile`：`native`/`mini` 目标会带 `CardinalMiniSep`（LV2），是该环境"报错"的来源。
