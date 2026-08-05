"""生成 joapp/resources/jo-app.ico。

图标是用 QPainter 画出来的（见 joapp/ui/style.py），平时不需要资源文件；
但 Windows 快捷方式要的是磁盘上的 .ico，所以单独导一次。改了配色或形状之后
重跑这个脚本：

    .venv\\Scripts\\python.exe scripts\\make_icon.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QGuiApplication  # noqa: E402

from joapp.ui.style import write_ico  # noqa: E402

ICO_PATH = Path(__file__).resolve().parent.parent / "joapp" / "resources" / "jo-app.ico"

if __name__ == "__main__":
    app = QGuiApplication([])  # QPixmap 需要一个 GUI application 实例
    path = write_ico(ICO_PATH)
    print(f"已生成 {path} ({Path(path).stat().st_size} bytes)")
