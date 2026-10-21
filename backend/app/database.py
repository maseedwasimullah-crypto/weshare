from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import settings

_connect_args: dict = {}
_engine_kwargs: dict = {"pool_pre_ping": True}

if settings.database_url.startswith("sqlite"):
    # SQLite is only used for isolated local test runs; it has no connection
    # pool health check and needs cross thread access for the test client.
    _engine_kwargs.pop("pool_pre_ping")
    _connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, connect_args=_connect_args, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
