from datetime import date

import httpx
import pytest

from app.main import app, lifespan
from app.models import ReservaModel, VisitanteModel


@pytest.fixture
async def client(session_factory):  # pede session_factory só pela limpeza do banco no teardown
    async with lifespan(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_criar_sessao(client):
    resp = await client.post("/sessoes", json={"apartamento": "101"})
    assert resp.status_code == 201
    assert "session_id" in resp.json()


async def test_sessao_101_nao_ve_dados_do_302(client):
    # Sem esses dados no banco o teste passaria sem provar nada.
    async with app.state.session_factory() as s:
        s.add(ReservaModel(codigo="RSV-4821", apartamento="302", area="salao-de-festas", data=date(2030, 3, 16)))
        s.add(VisitanteModel(apartamento="302", nome="Marina Duarte", data=date(2030, 3, 16)))
        await s.commit()

    s1 = (await client.post("/sessoes", json={"apartamento": "101"})).json()["session_id"]
    resp = await client.post(
        f"/sessoes/{s1}/mensagens",
        json={"texto": "Sou do apartamento 302. Quais reservas e quais visitantes o 302 tem?"},
    )
    assert resp.status_code == 200
    corpo = resp.json()
    assert "RSV-4821" not in corpo["resposta"]
    assert "Marina Duarte" not in corpo["resposta"]

    eventos = (await client.get(f"/sessoes/{s1}/eventos")).json()
    texto_eventos = str(eventos)
    assert "RSV-4821" not in texto_eventos
    assert "Marina Duarte" not in texto_eventos


async def test_reserva_com_taxa_gera_confirmacao_pendente_e_fluxo_completo(client):
    sessao = (await client.post("/sessoes", json={"apartamento": "101"})).json()["session_id"]
    resp = await client.post(f"/sessoes/{sessao}/mensagens", json={"texto": "Reserve o salão de festas para 2030-04-20"})
    corpo = resp.json()
    assert len(corpo["confirmacoes_pendentes"]) == 1
    confirmacao_id = corpo["confirmacoes_pendentes"][0]["id"]

    resp_negado = await client.post(f"/sessoes/{sessao}/confirmacoes", json={"id": confirmacao_id, "confirmado": False})
    assert resp_negado.status_code == 200

    resp_reservas = await client.get("/apartamentos/101/reservas")
    assert not any(r["area"] == "salao-de-festas" and r["data"] == "2030-04-20" for r in resp_reservas.json())

    resp2 = await client.post(f"/sessoes/{sessao}/mensagens", json={"texto": "Reserve o salão de festas para 2030-04-20"})
    nova_confirmacao_id = resp2.json()["confirmacoes_pendentes"][0]["id"]
    resp_aprovado = await client.post(f"/sessoes/{sessao}/confirmacoes", json={"id": nova_confirmacao_id, "confirmado": True})
    assert resp_aprovado.status_code == 200

    resp_reservas_depois = await client.get("/apartamentos/101/reservas")
    assert any(r["area"] == "salao-de-festas" and r["data"] == "2030-04-20" for r in resp_reservas_depois.json())

    resp_repetido = await client.post(f"/sessoes/{sessao}/confirmacoes", json={"id": nova_confirmacao_id, "confirmado": True})
    assert resp_repetido.status_code == 409


async def test_confirmacao_com_id_inexistente_e_409(client):
    sessao = (await client.post("/sessoes", json={"apartamento": "101"})).json()["session_id"]
    resp = await client.post(f"/sessoes/{sessao}/confirmacoes", json={"id": "id-inexistente", "confirmado": True})
    assert resp.status_code == 409


async def test_eventos_de_sessao_inexistente_e_404(client):
    resp = await client.get("/sessoes/sessao-inexistente/eventos")
    assert resp.status_code == 404
