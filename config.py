"""配置文件"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _db_uri() -> str:
    """解析 DATABASE_URL, 兼容 Render 提供的 postgres:// 协议"""
    uri = os.environ.get("DATABASE_URL", "")
    if uri.startswith("postgres://"):
        # SQLAlchemy 1.4+ 要求 postgresql://
        uri = uri.replace("postgres://", "postgresql://", 1)
    if not uri:
        uri = "sqlite:///" + os.path.join(BASE_DIR, "instance", "class.db")
    return uri


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "banzhuren-mange-key-change-in-prod")
    SQLALCHEMY_DATABASE_URI = _db_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB 上传上限
    WTF_CSRF_TIME_LIMIT = None
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "instance", "uploads")
    ALLOWED_EXCEL = {".xlsx", ".xls"}


class DevConfig(Config):
    DEBUG = True
    ENV = "development"


class ProdConfig(Config):
    DEBUG = False
    ENV = "production"


# 优先使用 FLASK_CONFIG 环境变量, 否则根据是否有外部数据库自动选择
# 有 DATABASE_URL 时默认用生产配置, 否则用开发配置
_env = os.environ.get("FLASK_CONFIG", "")
if _env in ("dev", "prod"):
    _default_config = ProdConfig if _env == "prod" else DevConfig
elif os.environ.get("DATABASE_URL"):
    _default_config = ProdConfig
else:
    _default_config = DevConfig

config_map = {"dev": DevConfig, "prod": ProdConfig, "default": _default_config}
