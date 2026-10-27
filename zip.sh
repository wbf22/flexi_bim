#!/usr/bin/env bash
# Package the addon for "Install from Disk" (package directory at the zip root).
set -euo pipefail
cd "$(dirname "$0")"
rm -f flexi_bim.zip
zip -r flexi_bim.zip flexi_bim -x '*__pycache__*' -x '*.DS_Store' -x '*.pyc'
