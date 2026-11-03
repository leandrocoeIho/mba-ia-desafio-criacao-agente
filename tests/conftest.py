import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import pytest_asyncio

from app.config import get_settings
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


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _banco_de_dev_limpo():
    # Os testes de API (tests/test_api_*.py, tests/test_root_agent_fluxo.py)
    # rodam contra o banco de DEV de verdade (DATABASE_URL), nao o de teste,
    # pra exercitar o wiring real de app/main.py. Diferente do banco de teste
    # (acima), ele nao e limpo pela fixture session_factory entre testes, e
    # fica entre execucoes separadas do pytest -- sem isso, uma reserva criada
    # numa execucao anterior "vaza" pra um teste que espera a area/data livre.
    dev_engine = make_engine(get_settings().database_url)
    async with dev_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await dev_engine.dispose()
