from datetime import date

from app import repository
from app.config import get_settings
from app.db import make_engine, make_session_factory
from scripts.restore import restaurar


async def test_restaurar_recarrega_os_dados_iniciais():
    settings = get_settings()
    await restaurar(settings.database_url)

    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    async with session_factory() as session:
        reservas_101 = await repository.listar_reservas(session, "101")
        reservas_302 = await repository.listar_reservas(session, "302")
        visitantes_302 = await repository.listar_visitantes(session, "302")
    await engine.dispose()

    assert any(r.codigo == "RSV-1377" and r.area == "quadra" and r.data == date(2030, 3, 9) for r in reservas_101)
    assert any(r.codigo == "RSV-4821" for r in reservas_302)
    assert any(v.nome == "Marina Duarte" and v.data == date(2030, 3, 16) for v in visitantes_302)
