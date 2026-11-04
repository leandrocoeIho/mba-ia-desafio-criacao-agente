import asyncio
import json
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.adk_app import make_session_service
from app.config import get_settings
from app.db import Base, make_engine, make_session_factory
from app.models import ReservaModel, VisitanteModel
from app.reference_data import DADOS_DIR


async def restaurar(database_url: str) -> None:
    engine = make_engine(database_url)

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    session_factory = make_session_factory(engine)
    reservas = json.loads((DADOS_DIR / "reservas.json").read_text(encoding="utf-8"))
    visitantes = json.loads((DADOS_DIR / "visitantes.json").read_text(encoding="utf-8"))

    async with session_factory() as session:
        for r in reservas:
            session.add(
                ReservaModel(
                    codigo=r["codigo"],
                    apartamento=r["apartamento"],
                    area=r["area"],
                    data=date.fromisoformat(r["data"]),
                    status="ativa",
                )
            )
        for v in visitantes:
            session.add(
                VisitanteModel(
                    apartamento=v["apartamento"],
                    nome=v["nome"],
                    data=date.fromisoformat(v["data"]),
                )
            )
        await session.commit()

    await engine.dispose()

    # Recria as tabelas do ADK (sessões/eventos), apagadas junto com o schema.
    adk_session_service = make_session_service()
    await adk_session_service.prepare_tables()

    print(f"Restaurado: {len(reservas)} reservas, {len(visitantes)} visitantes.")


if __name__ == "__main__":
    settings = get_settings()
    asyncio.run(restaurar(settings.database_url))
