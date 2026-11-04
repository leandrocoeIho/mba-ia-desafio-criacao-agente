import asyncio

import httpx
import pytest

from app.main import app, lifespan


@pytest.fixture
async def client(session_factory):  # pede session_factory só pela limpeza do banco no teardown
    async with lifespan(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_duas_sessoes_aprovando_a_mesma_area_data_ao_mesmo_tempo_so_uma_vence(client):
    s3 = (await client.post("/sessoes", json={"apartamento": "101"})).json()["session_id"]
    s4 = (await client.post("/sessoes", json={"apartamento": "201"})).json()["session_id"]

    texto = "Reserve o salão de festas para 2030-05-11"
    resp3, resp4 = await asyncio.gather(
        client.post(f"/sessoes/{s3}/mensagens", json={"texto": texto}),
        client.post(f"/sessoes/{s4}/mensagens", json={"texto": texto}),
    )
    confirmacao3 = resp3.json()["confirmacoes_pendentes"][0]["id"]
    confirmacao4 = resp4.json()["confirmacoes_pendentes"][0]["id"]

    aprov3, aprov4 = await asyncio.gather(
        client.post(f"/sessoes/{s3}/confirmacoes", json={"id": confirmacao3, "confirmado": True}),
        client.post(f"/sessoes/{s4}/confirmacoes", json={"id": confirmacao4, "confirmado": True}),
    )
    assert aprov3.status_code == 200
    assert aprov4.status_code == 200

    reservas_101 = (await client.get("/apartamentos/101/reservas")).json()
    reservas_201 = (await client.get("/apartamentos/201/reservas")).json()
    total = sum(1 for r in reservas_101 + reservas_201 if r["area"] == "salao-de-festas" and r["data"] == "2030-05-11")
    assert total == 1
