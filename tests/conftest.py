"""把测试的数据目录指到临时路径，别污染真实的 %APPDATA%\\jo-app。

必须在导入 joapp 之前设好 —— config.py 在模块级就算出了路径。
conftest 在测试模块之前被导入，正好赶得上。
"""

import os
import tempfile

os.environ.setdefault(
    "JOAPP_HOME", os.path.join(tempfile.gettempdir(), "jo-app-tests")
)
