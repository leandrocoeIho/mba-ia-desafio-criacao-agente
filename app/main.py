import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import db
from app.adk_app import make_runner, make_session_service
from app.agents.root import build_root_agent
from app.api.routes_sessoes import router as sessoes_router
from app.api.routes_verificacao import router as verificacao_router
from app.config import get_settings
from app.db import make_engine, make_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    db.configurar_session_factory(session_factory)

    session_service = make_session_service()
    runner = make_runner(build_root_agent(), session_service)

    app.state.session_factory = session_factory
    app.state.session_service = session_service
    app.state.runner = runner
    yield
    await engine.dispose()


app = FastAPI(lifespan=lifespan)
app.include_router(sessoes_router)
app.include_router(verificacao_router)
