"""演示数据 CLI 入口

用法:
    python -m scripts.seed_demo
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.utils.demo import seed_all


def main():
    app = create_app("default")
    with app.app_context():
        result = seed_all()
        print(f"演示数据生成完成:")
        print(f"  学生: {result['students']} 人")
        print(f"  考试: {result['exams']} 次")
        print(f"  日常记录: {result['records']} 条")
        print(f"  数据库: {app.config['SQLALCHEMY_DATABASE_URI']}")
        print(f"\n启动应用: python app.py  -> http://127.0.0.1:5000")


if __name__ == "__main__":
    main()
