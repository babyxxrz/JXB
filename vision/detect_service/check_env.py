# -*- coding: utf-8 -*-
"""
check_env.py — 板载环境自检(上板第一步,在 Atlas 200I DK A2 上运行)

用途: 部署 detect_service 前,确认 Python/依赖/ACL/摄像头 是否就绪,
缺什么补什么,避免"报错报半天才发现是环境没装"。

用法(板子上):
  python check_env.py
开发机也可以跑: ACL 相关项会明确提示"仅板载可用",其余照常检查。
"""

import sys

print("=" * 60)
print("vision 板载环境自检")
print("=" * 60)

ok = True


def check(name, cond, hint=""):
    global ok
    mark = "[OK]" if cond else "[缺失]"
    if not cond:
        ok = False
    print(f"  {mark} {name}" + (f"  <- {hint}" if hint and not cond else ""))


# 1. Python 版本(板载镜像自带,一般无需动)
py = sys.version_info
check(f"Python {py.major}.{py.minor}.{py.micro} (>=3.8)",
      py >= (3, 8))

# 2. numpy / cv2(detect_service 的硬依赖)
try:
    import numpy
    check(f"numpy {numpy.__version__}", True)
except ImportError:
    check("numpy", False, "pip install numpy")

try:
    import cv2
    check(f"opencv {cv2.__version__}", True)
except ImportError:
    check("opencv-python", False, "pip install opencv-python")

# 3. ACL(PyACL,由 CANN 工具链提供,不是 pip 包)
try:
    import acl
    check("PyACL(import acl)", True)
except ImportError:
    check("PyACL(import acl)", False,
          "板子上需安装 CANN 工具链并 source set_env.sh;开发机无此项属正常")

# 4. CANN 环境变量(板子上转换/运行会用到)
import os
ascend = os.environ.get("ASCEND_HOME_PATH")
check("ASCEND_HOME_PATH 环境变量", bool(ascend),
      "source /usr/local/Ascend/ascend-toolkit/set_env.sh")

# 5. 摄像头(任务3 用的 VideoCapture(0),部署后 demo 要用)
try:
    cap = cv2.VideoCapture(0)
    cam_ok = cap.isOpened()
    cap.release()
    check("摄像头 /dev/video0 可打开", cam_ok,
          "检查摄像头接线,或 ls /dev/video*")
except Exception:
    check("摄像头 /dev/video0 可打开", False)

print("-" * 60)
if ok:
    print("结论: 环境就绪,可以部署 detect_service")
    print("下一步: python demo_detect.py --mock  # 先跑模拟,再接真模型")
else:
    print("结论: 有缺失项,按上面 <- 提示补齐后重跑本脚本")
print("=" * 60)
sys.exit(0 if ok else 1)
