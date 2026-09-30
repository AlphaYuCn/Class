"""Flask 应用工厂"""
import os

from flask import Flask
from config import config_map
from app.extensions import db, csrf


def create_app(config_name: str = "default") -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_map[config_name])

    # 确保 instance 目录存在
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config.get("UPLOAD_FOLDER", "instance/uploads"), exist_ok=True)

    # 初始化扩展
    db.init_app(app)
    csrf.init_app(app)

    # 注册蓝图
    from app.blueprints.main import main_bp
    from app.blueprints.students import students_bp
    from app.blueprints.scores import scores_bp
    from app.blueprints.daily import daily_bp
    from app.blueprints.tools import tools_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(students_bp, url_prefix="/students")
    app.register_blueprint(scores_bp, url_prefix="/scores")
    app.register_blueprint(daily_bp, url_prefix="/daily")
    app.register_blueprint(tools_bp, url_prefix="/tools")

    # Jinja 全局过滤器
    from app.utils.jinja_filters import register_filters

    register_filters(app)

    # 首次建表 + 增量迁移
    with app.app_context():
        from app import models  # noqa: F401 触发模型注册

        db.create_all()
        _ensure_columns(app)

    return app


def _ensure_columns(app):
    """对已存在的表，自动补齐 ORM 中新增的列(SQLite ALTER TABLE ADD COLUMN)。
    仅用于开发期轻量迁移，避免 drop_all 丢数据。
    """
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    # 表 -> [(列名, 列DDL类型)]
    table_columns = {
        "student": [
            ("father_name", "VARCHAR(50)"),
            ("father_phone", "VARCHAR(20)"),
            ("mother_name", "VARCHAR(50)"),
            ("mother_phone", "VARCHAR(20)"),
            ("emergency_contact", "VARCHAR(50)"),
            ("emergency_phone", "VARCHAR(20)"),
        ],
        "daily_record": [
            ("start_date", "DATE"),
            ("end_date", "DATE"),
            ("leave_days", "FLOAT"),
            ("leave_reason", "VARCHAR(100)"),
            ("parent_notified", "BOOLEAN"),
            ("cancel_date", "DATE"),
        ],
    }
    with db.engine.begin() as conn:
        for table, cols in table_columns.items():
            if table not in inspector.get_table_names():
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for col_name, col_type in cols:
                if col_name not in existing:
                    conn.execute(text(
                        f'ALTER TABLE "{table}" ADD COLUMN "{col_name}" {col_type}'
                    ))
                    app.logger.info(f"[migrate] added {table}.{col_name}")
