"""PyInstaller 的入口。

joapp/__main__.py 用的是相对导入，不能直接当顶层脚本打包，所以单独放一个。
"""

import sys

from joapp.ui.app import run

if __name__ == "__main__":
    sys.exit(run())
