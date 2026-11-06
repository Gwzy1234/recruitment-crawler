#!/bin/bash
# Finder 可直接双击的 macOS 入口；.sh 文件可能被关联为文本文件。
cd -- "$(dirname -- "$0")" || exit 1
exec /bin/bash "$PWD/start.sh" "$@"
