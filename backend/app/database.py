from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from backend.app.config import DATABASE_URL

Base = declarative_base()

_engine = None
SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False, future=True)


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
        SessionLocal.configure(bind=_engine)
    return _engine


def get_session() -> Iterator[Session]:
    get_engine()
    with SessionLocal() as session:
        yield session
