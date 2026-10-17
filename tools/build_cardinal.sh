#!/bin/bash
# Cardinal 分阶段编译脚本（在 WSL 的 Ubuntu 里执行）
#
# 用法（Windows 侧调）:
#   python D:/Cardinal/tools/wslrun.py --sh "bash /mnt/d/Cardinal/tools/build_cardinal.sh deps"
#   python D:/Cardinal/tools/wslrun.py --sh "bash /mnt/d/Cardinal/tools/build_cardinal.sh mini"
#   python D:/Cardinal/tools/wslrun.py --sh "bash /mnt/d/Cardinal/tools/build_cardinal.sh full"
#
# 可选环境变量:
#   JOBS=8          并行度（默认 8；官方 CI 收尾用 -j1 防 OOM，别一上来 -j24）
#   USE_CCACHE=1    用 ccache 加速重复编译（默认关，首次编译没用）
#
# 阶段说明（从小到大，逐个验证，别跳）:
#   env      只看环境，不编译
#   deps     只编第三方依赖库（最快，验证工具链能用）
#   mini     官方 mini 目标 = 少量插件的最小可用版（哨兵）
#   plugins  只编插件系统（1400 模块，最耗时最容易出兼容性错）
#   full     完整构建 all = cardinal+carla+deps+dgl+plugins+gen+resources

set -u
SRC=/home/lijia/Cardinal
STAGE="${1:-env}"
JOBS="${JOBS:-8}"
OUT=/mnt/d/Cardinal/tmp
LOG="$OUT/build_${STAGE}.log"

# ---------------------------------------------------------------- 环境自检
echo "################ 环境 ################"
echo "时间      : $(date '+%F %T')"
echo "CPU 核数  : $(nproc)"
echo "内存      : $(free -g | awk '/^Mem:/{print $2" GiB 总 / "$7" GiB 可用"}')"
echo "swap      : $(free -g | awk '/^Swap:/{print $2" GiB"}')"
echo "磁盘(根)  : $(df -h / | awk 'NR==2{print $4" 可用"}')"
echo "gcc       : $(gcc --version 2>/dev/null | head -1 || echo '未安装')"
echo "make      : $(make --version 2>/dev/null | head -1 || echo '未安装')"
echo "阶段      : $STAGE"
echo "并行度    : -j$JOBS"
echo

if [ "$STAGE" = "env" ]; then
    echo "===== 源码目录状态 ====="
    if [ -d "$SRC/.git" ]; then
        cd "$SRC" || exit 1
        echo "分支      : $(git describe --tags --always 2>/dev/null)"
        echo "子模块总  : $(git submodule status 2>/dev/null | wc -l)"
        echo "已初始化  : $(git submodule status 2>/dev/null | grep -c '^ ')"
        echo "未初始化  : $(git submodule status 2>/dev/null | grep -c '^-')"
        echo "体积      : $(du -sh . 2>/dev/null | cut -f1)"
    else
        echo "源码目录不存在: $SRC"
    fi
    exit 0
fi

cd "$SRC" || { echo "ERR: 源码目录不存在 $SRC"; exit 1; }

# ---------------------------------------------------------------- 目标映射
case "$STAGE" in
    deps)    TARGET="deps" ;;
    mini)    TARGET="mini" ;;
    plugins) TARGET="plugins" ;;
    native)  TARGET="native" ;;
    full)    TARGET="all" ;;
    *) echo "ERR: 未知阶段 '$STAGE'（可选: env deps mini plugins native full）"; exit 2 ;;
esac

# ccache 可选
if [ "${USE_CCACHE:-0}" = "1" ] && command -v ccache >/dev/null 2>&1; then
    export CC="ccache gcc"
    export CXX="ccache g++"
    echo "ccache    : 已启用"
    echo
fi

# ---------------------------------------------------------------- 编译
echo "################ 开始编译: make -j$JOBS $TARGET ################"
echo "日志: $LOG"
START=$(date +%s)

# 关掉 make 的进度噪音写日志，终端只留尾部
make -j"$JOBS" "$TARGET" > "$LOG" 2>&1
CODE=$?

END=$(date +%s)
echo
echo "################ 结果 ################"
echo "退出码    : $CODE"
echo "用时      : $((END - START)) 秒"
echo "日志行数  : $(wc -l < "$LOG")"

if [ "$CODE" -ne 0 ]; then
    echo
    echo "===== 错误摘要（前 60 条 error）====="
    grep -nE 'error:|Error [0-9]|undefined reference|fatal error' "$LOG" | head -60
    echo
    echo "===== 日志尾部 30 行 ====="
    tail -30 "$LOG"
    echo
    echo "BUILD_FAILED"
    exit "$CODE"
fi

echo
echo "===== 日志尾部 20 行 ====="
tail -20 "$LOG"
echo
echo "===== 产物 ====="
ls -la "$SRC/bin" 2>/dev/null | head -30 || echo "（bin/ 尚未生成）"
echo "BUILD_OK"
