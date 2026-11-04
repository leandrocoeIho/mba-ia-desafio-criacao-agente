import httpx
import pytest

from app.main import app, lifespan


@pytest.fixture
async def client(session_factory):  # pede session_factory só pela limpeza do banco no teardown
    async with lifespan(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_reservas_e_visitantes_de_apartamento_sem_dados_sao_listas_vazias(client):
    resp_reservas = await client.get("/apartamentos/999/reservas")
    assert resp_reservas.status_code == 200
    assert resp_reservas.json() == []

    resp_visitantes = await client.get("/apartamentos/999/visitantes")
    assert resp_visitantes.status_code == 200
    assert resp_visitantes.json() == []


async def test_reserva_criada_pela_api_aparece_na_rota_de_verificacao(client):
    sessao = (await client.post("/sessoes", json={"apartamento": "101"})).json()["session_id"]
    await client.post(f"/sessoes/{sessao}/mensagens", json={"texto": "Reserve a quadra para 2030-04-06"})

    resp = await client.get("/apartamentos/101/reservas")
    assert any(r["area"] == "quadra" and r["data"] == "2030-04-06" for r in resp.json())
