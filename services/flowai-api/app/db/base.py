"""声明式基类：每个服务独立 Base，禁止跨服务导入模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, MetaData
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import DeclarativeBase

# 命名约定便于 Alembic 生成稳定的约束名
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# MySQL 使用 DATETIME(6)，SQLite 使用通用 DateTime（docs/03：时间 UTC DATETIME(6)）
TimestampType = DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")

# BIGINT 主键；SQLite 需 INTEGER PRIMARY KEY 才能自增（仅测试用）
BigIntType = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> datetime:
    """统一 UTC 时间（不带时区写入，对外序列化为 ISO8601）。"""
    from datetime import timezone

    return datetime.now(timezone.utc).replace(tzinfo=None)