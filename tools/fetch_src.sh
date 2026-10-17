#!/bin/bash
# 拉取 / 补全 Cardinal 源码与子模块（幂等，可反复执行，掉线能续）
#
# 用法:
#   python D:/Cardinal/tools/wslrun.py --sh "bash /mnt/d/Cardinal/tools/fetch_src.sh"
#
# 说明:
#   - 子模块用 --depth 1 逐个按【记录 SHA】浅取。GitHub 支持按完整 SHA 浅取
#     （注意：传缩写 SHA 会报 "couldn't find remote ref"，必须给 40 位完整 SHA）。
#   - 最多重试 3 遍；跑完做【三项校验】，任何一项不过都算没完成：
#       ① 提交号 == 父仓库索引记录的那个      (git submodule status 的前缀字符)
#       ② 工作区非空（防「空壳子模块」）      (目录里除 .git 外还有东西)
#       ③ 没有未初始化(-) 的项
#     ⚠️ ② 是必须的：子模块在 checkout 中途被打断，会留下「HEAD 对、文件空」的残局，
#        而 git 的 update 只看 HEAD，会误判"已就绪"而跳过。此时要跑 repair_subs.sh。
#   - 全部输出写入 /mnt/d/Cardinal/tmp/fetch_src.log（不接管道，免得缓冲看不到进度）。

set -u
SRC=/home/lijia/Cardinal
REPO=https://github.com/DISTRHO/Cardinal.git
REF=26.02
JOBS="${JOBS:-8}"
LOG=/mnt/d/Cardinal/tmp/fetch_src.log

exec > "$LOG" 2>&1

echo "===== fetch_src 开始 $(date '+%F %T') ====="
echo "目标目录 : $SRC"
echo "并行度   : $JOBS"

# ---------------------------------------------------------------- 1. 主仓库
if [ -d "$SRC/.git" ]; then
    echo "主仓库已存在，跳过 clone"
else
    echo "--- 主仓库不存在，开始 clone ---"
    cd /home/lijia || exit 1
    git clone --branch "$REF" --depth 1 "$REPO" "$SRC" || { echo "CLONE_FAILED"; exit 1; }
fi

cd "$SRC" || { echo "SRC_MISSING"; exit 1; }
echo "主仓库版本: $(git describe --tags --always 2>/dev/null)"

# ---------------------------------------------------------------- 2. 子模块（多遍，让嵌套层逐级浮现）
pass=0
while [ "$pass" -lt 4 ]; do
    pass=$((pass+1))
    echo
    echo "----- 第 $pass 遍 submodule update（--depth 1 --jobs $JOBS）-----"
    START=$(date +%s)
    git submodule sync --recursive >/dev/null 2>&1
    if git submodule update --init --recursive --depth 1 --jobs "$JOBS"; then
        echo "第 $pass 遍：命令成功"
    else
        echo "第 $pass 遍：有失败项"
    fi
    echo "用时 $(( $(date +%s) - START )) 秒"

    # 提前跳出：三项都过就不必再来一遍
    uninit_now=$(git submodule status --recursive 2>/dev/null | grep -c '^-')
    [ "$uninit_now" -eq 0 ] && echo "已无未初始化项，停止迭代" && break
    echo "仍有 $uninit_now 个未初始化（多为嵌套层），继续下一遍"
done

# ---------------------------------------------------------------- 3. 三项校验
# 判据：git 自己算出的【前缀字符】才是权威 ——
#   ' '  检出提交 == 索引记录   OK
#   '+'  检出提交 != 索引记录   不符
#   '-'  未初始化
# 不要用 git -C "$path" rev-parse 去比：两边值同源，永远相等，是【同义反复】，
# 什么都测不出来。旧版这么写，对嵌套路径还会整片误报（实测误报 158 个）。
echo
echo "===== 三项校验（提交号 / 工作区非空 / 未初始化）====="
TMP="${TMPDIR:-/tmp}/substatus.$$"
git submodule status --recursive 2>/dev/null > "$TMP"
total=$(wc -l < "$TMP" | tr -d ' ')
mismatch=$(grep -c '^+' "$TMP" || true)
uninit=$(grep -c '^-' "$TMP" || true)
emptybad=0
BAD=""

while IFS= read -r line; do
    [ -z "$line" ] && continue
    prefix="${line:0:1}"
    rest="${line:1}"
    path="${rest#* }"
    path="${path%% *}"
    [ -z "$path" ] && continue

    case "$prefix" in
        '-') BAD="$BAD
  [未初始化] $path" ;;
        '+') BAD="$BAD
  [提交号不符] $path" ;;
    esac

    # 空壳检查：git 查不出这一种（HEAD 对、工作区空），必须自己看目录
    n=$(ls -A "$path" 2>/dev/null | grep -vc '^\.git$' || true)
    if [ "$n" -eq 0 ]; then
        emptybad=$((emptybad+1))
        BAD="$BAD
  [空壳目录] $path"
    fi
done < "$TMP"
rm -f "$TMP"

echo "总数 $total | 提交号不符 $mismatch | 空壳 $emptybad | 未初始化 $uninit"
[ -n "$BAD" ] && echo "问题清单:$BAD"

echo
echo "体积: $(du -sh "$SRC" 2>/dev/null | cut -f1)"
if [ "$mismatch" -eq 0 ] && [ "$emptybad" -eq 0 ] && [ "$uninit" -eq 0 ]; then
    echo "SUBMODULES_ALL_OK"
else
    echo "SUBMODULES_INCOMPLETE"
fi
echo "===== fetch_src 结束 $(date '+%F %T') ====="
