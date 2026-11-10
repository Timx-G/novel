#!/bin/sh
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
bundled_python="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
if [ -n "${BOOK_READING_PYTHON:-}" ]; then
    python_bin=$BOOK_READING_PYTHON
elif [ -x "$bundled_python" ]; then
    python_bin=$bundled_python
else
    python_bin=$(command -v python3)
fi
if ! "$python_bin" -c 'import reportlab, pypdf, pdfplumber' >/dev/null 2>&1; then
    printf '%s\n' '阅读版生成失败：所选 Python 缺少 reportlab、pypdf 或 pdfplumber；请设置 BOOK_READING_PYTHON。' >&2
    exit 1
fi
exec "$python_bin" "$script_dir/export_book.py" "$@"
