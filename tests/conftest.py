import os

TEST_DATABASE_URL = "postgresql+asyncpg://aurora:aurora@127.0.0.1:5432/aurora_test"
# Antes de importar app: load_dotenv() não sobrescreve, então app/main.py e o ADK
# também usam o banco de teste, e rodar a suíte nunca apaga o banco de dev.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest_asyncio

from app.db import Base, make_engine, make_session_factory
from app.models import ReservaModel, VisitanteModel  # noqa: F401


@pytest_asyncio.fixture(scope="session", autouse=True)
async def engine():
    eng = make_engine(TEST_DATABASE_URL)
    # Limpa sobras de execuções anteriores (os testes de API não usam session_factory).
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
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
