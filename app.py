"""启动入口

用法:
    python app.py
然后访问 http://127.0.0.1:5000

首次试用建议先执行:
    python -m scripts.seed_demo
"""
import sys
import os

# 确保项目根在 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

app = create_app(os.environ.get("FLASK_CONFIG", "default"))


if __name__ == "__main__":
    # 规避 Windows PowerShell ExecutionPolicy 限制, 直接 python 启动
    app.run(host="127.0.0.1", port=5000, debug=app.config.get("DEBUG", False))
