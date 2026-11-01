"""数据库层：独立引擎、约束生效、两库互不可见。"""

from datetime import datetime

import pytest
from sqlalchemy import String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base, utcnow
from app.db.session import build_engine, database_reachable
from app.db.base import TimestampType


class Widget(Base):
    __tablename__ = "widget"
    __table_args__ = (UniqueConstraint("code", name="uq_widget_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)


@pytest.fixture
def engine_pair(tmp_path):
    first = build_engine(f"sqlite:///{tmp_path / 'flowai.db'}")
    second = build_engine(f"sqlite:///{tmp_path / 'industrial.db'}")
    Base.metadata.create_all(first)
    Base.metadata.create_all(second)
    return first, second


def test_each_database_is_isolated(engine_pair):
    first, second = engine_pair
    with Session(first) as session:
        session.add(Widget(code="A-1", note="flowai"))
        session.commit()
    with Session(second) as session:
        session.add(Widget(code="B-1", note="industrial"))
        session.commit()

    with Session(first) as session:
        rows = session.execute(select(Widget)).scalars().all()
    assert [row.note for row in rows] == ["flowai"]

    with Session(second) as session:
        rows = session.execute(select(Widget)).scalars().all()
    assert [row.note for row in rows] == ["industrial"]


def test_unique_constraint_is_enforced_by_database(engine_pair):
    first, _ = engine_pair
    with Session(first) as session:
        session.add(Widget(code="DUP", note="first"))
        session.commit()

    with Session(first) as session:
        session.add(Widget(code="DUP", note="second"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_database_reachable_true_and_false(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'probe.db'}")
    Base.metadata.create_all(engine)
    engine.dispose()

    assert database_reachable(f"sqlite:///{tmp_path / 'probe.db'}") is True
    assert database_reachable("mysql+pymysql://u:p@127.0.0.1:1/none") is False