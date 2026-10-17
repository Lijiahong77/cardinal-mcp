#!/bin/bash
# 修复「空壳子模块」：git 目录在、HEAD 提交号正确，但工作区文件是空的
#
# 症状：git submodule status 显示正常（提交号对得上），但目录里只有 .git，编译报
#       "xxx/plugin.hpp: No such file or directory"。
# 成因：子模块在 checkout 中途被中断，索引被标成「全部已删除」，工作区被清空。
#       之后 git submodule update 只看 HEAD 是否等于目标 SHA → 判定"已就绪"→ 跳过检出。
# 修法：reset --hard HEAD（工作区本来就是空的，不会丢任何东西）。
set -u
cd /home/lijia/Cardinal || exit 1

echo "=== 修复前扫描 ==="
BEFORE=0
while read -r line; do
    [ -z "$line" ] && continue
    p="${line:1}"; p="${p#* }"; path="${p%% *}"
    [ -z "$path" ] && continue
    [ -f "$path/.git" ] || [ -d "$path/.git" ] || continue
    n=$(ls -A "$path" 2>/dev/null | grep -vc '^\.git$')
    [ "$n" -eq 0 ] && BEFORE=$((BEFORE+1))
done < <(git submodule status --recursive 2>/dev/null)
echo "空壳数: $BEFORE"

if [ "$BEFORE" -eq 0 ]; then
    echo "无需修复"
    exit 0
fi

echo
echo "=== 逐个 reset --hard HEAD ==="
git submodule foreach --recursive '
  n=$(ls -A . 2>/dev/null | grep -vc "^\.git$")
  if [ "$n" -eq 0 ]; then
    sha=$(git rev-parse HEAD 2>/dev/null)
    git reset --hard -q HEAD >/dev/null 2>&1
    git checkout -f -q "$sha" >/dev/null 2>&1
    m=$(ls -A . 2>/dev/null | grep -vc "^\.git$")
    if [ "$m" -gt 0 ]; then
      echo "  [好] $displaypath  修复后 $m 个条目"
    else
      echo "  [坏] $displaypath  仍是空的！sha=$sha"
    fi
  fi
' 2>&1 | grep -E '^\s+\[(好|坏)\]'

echo
echo "=== 修复后复查 ==="
AFTER=0
STILL=""
while read -r line; do
    [ -z "$line" ] && continue
    p="${line:1}"; p="${p#* }"; path="${p%% *}"
    [ -z "$path" ] && continue
    [ -f "$path/.git" ] || [ -d "$path/.git" ] || continue
    n=$(ls -A "$path" 2>/dev/null | grep -vc '^\.git$')
    if [ "$n" -eq 0 ]; then
        AFTER=$((AFTER+1))
        STILL="$STILL
  $path"
    fi
done < <(git submodule status --recursive 2>/dev/null)

echo "空壳数: $BEFORE -> $AFTER"
if [ "$AFTER" -gt 0 ]; then
    echo "仍未修复:$STILL"
    echo "REPAIR_INCOMPLETE"
else
    echo "ALL_WORKTREES_OK"
fi
