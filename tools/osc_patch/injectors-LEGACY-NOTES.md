# injectors-LEGACY-NOTES · 6 个注入器的已知坑清单

> 建立：2026-10-22 深夜（C5 清理）· 用途：**只有你非要重跑某个 `inject_osc_*.py` 时**才需要读本文件。
> 正常重放路径是 `replay_osc.py` + `patches/*.patch`（见 README）——**注入器已全部降级为历史记录**。

## 总则（三条通用坑，任何注入器都可能踩）

1. **幂等判据不能用报错文本**：git 对「已应用」和「真冲突」报**同样的** `patch does not apply`
   ⇒ 判「已存在」必须用反向检查 `git apply --check -R`。
2. **E3 之后端点总数不能数 `add_method`**：注册已改 X-macro `REG("/path", ...)`
   ⇒ 数 `REG("` 开头行且**排除 `#define REG(` 那一行**才等于真实端点数。
3. **`git apply` 在非 git 目录里会「静默跳过」并返回 0（假成功）**
   ⇒ 应用根要先 `git init`，并显式检测输出里的 "skipped patch" 字样当失败。

## 各注入器的坑

### `inject_osc_read.py`（A 组，5 个读数端点）
- 无记录在案的坑。锚点是函数签名级匹配，upstream 大改才会失效。

### `inject_osc_b.py`（B 组，5 个零 hook 端点）
- 无记录在案的坑。同上。

### `inject_osc_c.py`（C 组，9 操作 + 2 JS 端点）
- 无记录在案的坑。但注意：C 组的 4 个写端点（cable-add / cable-remove / module-move /
  module-remove）**行为 bug 已于 2026-10-21 深夜 C6 批修复**（只 push 不手动执行）——
  本注入器写进去的仍是**修复前**的代码，别拿它的输出当现状。

### `inject_osc_d.py`（D 组，/screenshot + /load 回 warningLog）
- 两个真 bug（**10-20 已修并验证**：干净 upstream 54 条规则 0 失败、幂等 no-op）：
  1. `D2_LOAD_HANDLER_NEW` 函数签名被写错（丢具名参数 `types/argv/argc`，函数体却还在用）⇒ 编译不过。
  2. `D2-fromjson-dialog` 锚点多了一行上游根本不存在的 `warningLog = "";` ⇒ 干净树重放失败。
- 历史副作用记录：坏的幂等逻辑曾让顶层 `CardinalCommon.cpp` 多出 7 行重复的 `/screenshot` 注册，
  并留下 33 个 `.bak-*`（已清）。

### `inject_osc_e2.py`（E2，/modules-page 分页）
- `MARKER` 变量直接贴在字符串字面量后面**漏 `+` 号** ⇒ SyntaxError（已修，改内联字面量）。
- `check()` 断言写 `'"modules-page", "ii"'` 漏了 `/` 前缀（注册行实际带 `/`）⇒ 断言恒失败（已修）。

### `inject_osc_e3.py`（E3，注册表抽 X-macro）
- ① **字符串拼接漏 `+`**（同类 e2，MARKER 贴字面量）。
- ② **块边界 off-by-one**：注册块终点算成 `fb_idx`（开区间）⇒ fallback 行残留 ⇒ **重复注册 fallback**。
  修法：`fb_idx + 1` + fallback 计数断言（thread/plain 各恰好 1 次）。
- ③ **校验数到注释里的 `#undef REG`** ⇒ `s.count` 误判 ⇒ 改按整行精确匹配。
- ④ 初版引入 2 个新警告（`-Wmisleading-indentation` + `-Wunused-function`）⇒ 调用点改 4 空格 +
  两薄封装各包 `#ifdef`/`#else`。
- ⑤ **探针选错基线 exe**：拿 `CardinalNative.20261021-093225-old.exe`（E1 版）当 E2 版
  ⇒ 误报「/modules-page 不存在」。⇒ 基线 exe 必须 md5 对账。
- ⑥ **探针连续跑两轮时端口残留**：上一轮 wine 没释放 2228 ⇒ 下一轮 OSC 绑定失败
  ⇒ 全端点无回包、看起来像「重构把端点弄没了」。⇒ run 脚本必须轮询等端口释放/就绪。

## 结论

这些坑**不影响 `replay_osc.py` 主路径**——改动的真相是 `patches/*.patch`（已进 git、
双向 `git apply --check` 验证过、干净副本重放 22/22 逐字节一致）。本文件只为
「非要重跑注入器做考古/调试」的人备着。**日常一律走 replay。**
