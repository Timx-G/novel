#!/bin/sh
set -eu
root=$(git rev-parse --show-toplevel)
configured=$(git config --get core.hooksPath || true)
if [ -n "$configured" ] && [ "$configured" != '.githooks' ]; then
    printf '已有 hooksPath：%s；请先协调现有钩子，未覆盖配置。\n' "$configured" >&2
    exit 1
fi
if [ -z "$configured" ]; then
    default_hooks=$(git rev-parse --git-path hooks)
    for hook in "$default_hooks"/*; do
        [ -f "$hook" ] || continue
        case "$hook" in *.sample) continue ;; esac
        printf '发现已有 Git 钩子：%s；请先协调，未覆盖配置。\n' "$hook" >&2
        exit 1
    done
fi
for hook in post-merge post-commit post-rewrite run-book-export; do
    test -f "$root/.githooks/$hook"
    chmod +x "$root/.githooks/$hook"
done
git config --local core.hooksPath .githooks
printf '%s\n' '已启用本仓库的阅读版自动导出钩子；未执行提交或合并。'
