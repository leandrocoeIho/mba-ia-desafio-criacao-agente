import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import pytest_asyncio

from app.db import Base, make_engine, make_session_factory
from app.models import ReservaModel, VisitanteModel  # noqa: F401

TEST_DATABASE_URL = "postgresql+asyncpg://aurora:aurora@127.0.0.1:5432/aurora_test"

@pytest_asyncio.fixture(scope="session")
async def engine():
    eng = make_engine(TEST_DATABASE_URL)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    factory = make_session_factory(engine)
    yield factory
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
