#!/bin/bash
# macOS/Linux：自动查找 Python，后续环境准备由同一 Python 启动器完成。
cd -- "$(dirname -- "$0")" || exit 1
export PYTHONUTF8=1
export PYTHONUNBUFFERED=1

for candidate in "$PWD/.runtime/bin/python3" python3 python3.14 python3.13 python3.12 python3.11 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if command -v "$candidate" >/dev/null 2>&1 && \
       "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
        "$candidate" -B "$PWD/launch.py" "$@"
        result=$?
        if [ "$result" -ne 0 ] && [ -t 0 ]; then
            read -r -p '启动失败，按回车关闭窗口……' _
        fi
        exit "$result"
    fi
done

echo '未找到 Python 3.11 或更高版本。请先从 https://www.python.org/downloads/ 安装 Python。'
echo '安装完成后重新双击 start.command。无需安装 Node.js。'
if [ -t 0 ]; then read -r -p '按回车关闭窗口……' _; fi
exit 1
