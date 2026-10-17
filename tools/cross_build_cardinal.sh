#!/bin/bash
# Cardinal 交叉编译 —— 第二阶段：产出 Windows 版 (.exe / .dll)
#
# 前置：deps/PawPaw 的 bootstrap-cardinal.sh win64 已跑完（38+ 个 Windows 静态库就绪）
# 用法：bash cross_build_cardinal.sh [jobs] [noopt]
#        jobs  默认 8（并行度）
#        noopt 默认 true（-O0，编译快；正式版设 false 走 -O3）
#
# 依据官方 CI .github/workflows/build.yml 的 `windows:` 段（第 388 行起）复刻，
# 关键差异都来自那里：
#   1. xvfb-run 包裹 make —— 构建中 wine 要跑 Windows 工具，需要 X display（否则挂）
#   2. make features 先跑 —— DPF 的宿主工具目标（dpf/Makefile.base.mk:790）
#   3. carla 单独走 make carla-win32
#
# 注意：
#  - 必须在 WSL 里以普通用户跑（PAWPAW_DIR 依赖 $HOME）
#  - 产物落 bin/*.exe，不覆盖无后缀的 Linux 版产物；但 .o 会复用/覆写，
#    所以交叉编译后想回 Linux 版需重跑 make（约 209 秒）
#  - 日志写 $HOME（/tmp 是 tmpfs，会话结束即消失）

set -o pipefail

JOBS="${1:-8}"
NOOPT="${2:-true}"
CARDINAL_ROOT="/home/lijia/Cardinal"
LOG="$HOME/cardinal_cross_build.log"
PREFIX="$HOME/PawPawBuilds/targets/win64"

echo "=============================================="
echo " Cardinal 交叉编译 (win64)  jobs=$JOBS  NOOPT=$NOOPT"
echo "=============================================="

# --- 前置检查：PawPaw 依赖是否就绪 ---
LIB_COUNT=$(ls "$PREFIX/lib/"*.a 2>/dev/null | wc -l)
echo "[前置] PawPaw 静态库数量 = $LIB_COUNT"
if [ "$LIB_COUNT" -lt 10 ]; then
    echo "[中止] PawPaw 依赖未就绪，先跑 bootstrap-cardinal.sh win64"
    exit 2
fi
if ! command -v x86_64-w64-mingw32-g++ >/dev/null 2>&1; then
    echo "[中止] 找不到 mingw 交叉编译器"
    exit 3
fi
if ! command -v xvfb-run >/dev/null 2>&1; then
    echo "[中止] 找不到 xvfb-run（apt-get install xvfb）"
    exit 7
fi

# --- 载入交叉编译环境（照 CI：在 Cardinal 根目录 source）---
cd "$CARDINAL_ROOT" || exit 4
# shellcheck disable=SC1091
source deps/PawPaw/local.env win64 >/dev/null 2>&1 || { echo "[中止] source local.env win64 失败"; exit 5; }

echo "[环境] CC          = $CC"
echo "[环境] CXX         = $CXX"
echo "[环境] AR          = $AR"
echo "[环境] EXE_WRAPPER = ${EXE_WRAPPER:-<none>}"
echo "[环境] PREFIX      = $PREFIX"
echo

rm -f "$LOG"
START=$(date +%s)

# --- 步骤 1/4：DPF features（宿主工具）---
echo "[1/4] make features ..."
make features >> "$LOG" 2>&1
RC1=$?
echo "[1/4] features exit=$RC1"

RC=$RC1

# --- 步骤 2/4：先把全部 Rack 依赖编完 ---
# 前置：这一步不能省。src/Cardinal 与 src/Rack/dep 由不同 make 进程驱动，
# 依赖关系不跨进程传递，-j 并发时它会抢在 dep 就绪前进链接，报
# `cannot find libarchive_static.a`。实测踩过两次。
if [ "$RC1" -eq 0 ]; then
    echo "[2/4] xvfb-run make deps -j$JOBS ..."
    xvfb-run -a make deps -j"$JOBS" >> "$LOG" 2>&1
    RC1=$?
    echo "[2/4] deps exit=$RC1"
fi

if [ "$RC1" -eq 0 ]; then
    # --- 步骤 3/4：主构建（xvfb-run 是硬要求）---
    echo "[3/4] xvfb-run make NOOPT=$NOOPT -j$JOBS ..."
    if [ "$NOOPT" = "true" ]; then
        xvfb-run -a make NOOPT=true -j"$JOBS" >> "$LOG" 2>&1
    else
        xvfb-run -a make -j"$JOBS" >> "$LOG" 2>&1
    fi
    RC2=$?
    echo "[3/4] make exit=$RC2"
    RC=$RC2

    if [ "$RC2" -eq 0 ]; then
        # --- 步骤 4/4：carla 的 Windows 版 ---
        echo "[4/4] xvfb-run make carla-win32 -j$JOBS ..."
        xvfb-run -a make carla-win32 -j"$JOBS" >> "$LOG" 2>&1
        RC3=$?
        echo "[4/4] carla exit=$RC3"
        RC=$RC3
    fi
fi

END=$(date +%s)

echo "=============================================="
echo " 耗时 $((END - START)) 秒    FINAL_EXIT=$RC"
echo "=============================================="

echo "--- 错误摘要（最多 30 条）---"
grep -n 'error:' "$LOG" 2>/dev/null | head -30
ERRN=$(grep -c 'error:' "$LOG" 2>/dev/null || echo 0)
echo "(error 总数: $ERRN)"

echo
echo "--- Windows 产物 ---"
ls -la "$CARDINAL_ROOT/bin/"*.exe 2>/dev/null || echo "(暂无 .exe)"
ls -la "$CARDINAL_ROOT/bin/"*.dll 2>/dev/null | head -10

echo
echo "--- 日志末尾 15 行 ---"
tail -15 "$LOG"

exit $RC
