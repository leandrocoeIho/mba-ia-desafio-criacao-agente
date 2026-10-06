# Assistente do Residencial Aurora — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Residencial Aurora assistant — an API (FastAPI) backed by a
Google ADK multi-agent assistant (1 root + 3 specialists) and a single
Postgres database — that satisfies the challenge's exact HTTP contract and
its five code-enforced guarantees.

**Architecture:** One `root_agent` routes to three ADK sub-agents
(`especialista_reservas`, `especialista_visitantes`,
`especialista_regulamento`) via native `transfer_to_agent`. All reservation/
visitor writes go through a shared `app/repository.py` data-access module
(never a second agent) backed by Postgres, with a partial unique index
enforcing reservation exclusivity at insert time. ADK's own
`DatabaseSessionService` (same Postgres) persists sessions/events/state,
and `ResumabilityConfig(is_resumable=True)` plus explicit `invocation_id`
handling make tool-confirmation resumption work across process restarts —
this exact mechanism was validated against the real ADK 2.11.0 source and a
live Gemini call before this plan was written (see spec).

**Tech Stack:** Python 3.12, `uv`, Google ADK `>=2.2.0` (`google-adk[db]`),
`google-genai`, FastAPI, SQLAlchemy 2.x (async) + `asyncpg`, Postgres 16
(Docker), `pytest` + `pytest-asyncio` + `httpx`.

**Spec:** `docs/superpowers/specs/2026-10-05-assistente-residencial-aurora-design.md`

## Global Constraints

- Python `>=3.12`, project managed by `uv` (`pyproject.toml` + `uv.lock` committed).
- `google-adk` pinned `>=2.2.0`, series 2 (installed/tested: `2.11.0`).
- Model for every agent: `gemini-3.5-flash-lite` (the only model that answered reliably against this project's API key at design time — see spec).
- No API key ever committed. `.env` stays out of git (already in `.gitignore`); `.env.example` lists variable names only.
- `dados/*.json` and `dados/regulamento.md` are read-only inputs — no task may modify them.
- Every write to `reservas`/`visitantes` goes through `app/repository.py`. No tool may accept an `apartamento` parameter from the model — it always comes from `tool_context.state["apartamento"]`.
- Postgres is the only backing store (ADK sessions and business tables share one instance), started via `docker compose up -d`.
- Windows dev environment: every entry point that touches the async Postgres driver sets `asyncio.WindowsSelectorEventLoopPolicy()` on `sys.platform == "win32"` (asyncpg does not work reliably on the default Proactor loop on Windows).

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`, `uv.lock`, `.python-version` (via `uv init`)
- Create: `app/__init__.py`
- Create: `docker-compose.yml`
- Create: `docker/init-test-db.sql`
- Test: `tests/test_scaffolding.py`

**Interfaces:**
- Produces: a `uv run pytest` command every later task relies on; a `db` Postgres service reachable at `localhost:5432` with databases `aurora` (dev) and `aurora_test` (tests), user/password `aurora`/`aurora`.

- [ ] **Step 1: Initialize the uv project**

Run: `uv init --python 3.12 --name residencial-aurora .`
Expected: creates `pyproject.toml`, `.python-version`, `src/residencial_aurora/__init__.py` (the `src/` layout is not used by this plan — delete it in the next step).

- [ ] **Step 2: Remove the unused src/ layout**

Run: `rm -rf src/`

- [ ] **Step 3: Add runtime dependencies**

Run: `uv add fastapi uvicorn "google-adk[db]>=2.2.0" google-genai python-dotenv sqlalchemy asyncpg`
Expected: `pyproject.toml` gets a `[project] dependencies = [...]` list including all of the above; `uv.lock` is created/updated.

- [ ] **Step 4: Add dev dependencies**

Run: `uv add --dev pytest pytest-asyncio httpx`

- [ ] **Step 5: Configure pytest for async tests**

Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 6: Create the app package**

Create `app/__init__.py` (empty file).

- [ ] **Step 7: Write docker-compose.yml**

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: aurora
      POSTGRES_PASSWORD: aurora
      POSTGRES_DB: aurora
    ports:
      - "5432:5432"
    volumes:
      - aurora_pgdata:/var/lib/postgresql/data
      - ./docker/init-test-db.sql:/docker-entrypoint-initdb.d/init-test-db.sql

volumes:
  aurora_pgdata:
```

- [ ] **Step 8: Write the test-database init script**

Create `docker/init-test-db.sql`:

```sql
CREATE DATABASE aurora_test;
```

- [ ] **Step 9: Start Postgres**

Run: `docker compose up -d`
Expected: container `residencial-aurora-db-1` (or similar) running; `docker compose logs db` shows `database system is ready to accept connections`.

- [ ] **Step 10: Write a smoke test**

Create `tests/test_scaffolding.py`:

```python
def test_project_is_wired_up():
    assert True
```

- [ ] **Step 11: Run the smoke test**

Run: `uv run pytest tests/test_scaffolding.py -v`
Expected: `1 passed`.

- [ ] **Step 12: Commit**

```bash
git add pyproject.toml uv.lock .python-version app/__init__.py docker-compose.yml docker/init-test-db.sql tests/test_scaffolding.py .gitignore
git commit -m "chore: scaffold uv project, Postgres compose, pytest config"
```

---

### Task 2: Reference data (areas, apartamentos) — in memory, no table

**Files:**
- Create: `app/reference_data.py`
- Test: `tests/test_reference_data.py`

**Interfaces:**
- Produces: `Area(id, nome, taxa)`, `Apartamento(numero, morador)` dataclasses; `carregar_areas(dados_dir=DADOS_DIR) -> dict[str, Area]`; `carregar_apartamentos(dados_dir=DADOS_DIR) -> dict[str, Apartamento]`. Consumed later by `app/agents/reservas.py` and `app/agents/visitantes.py` to look up area fees without ever touching the database.

- [ ] **Step 1: Write the failing test**

Create `tests/test_reference_data.py`:

```python
from app.reference_data import carregar_apartamentos, carregar_areas


def test_carregar_areas_reflete_o_json():
    areas = carregar_areas()
    assert areas["salao-de-festas"].taxa == 150.0
    assert areas["churrasqueira"].taxa == 80.0
    assert areas["quadra"].taxa == 0
    assert areas["quadra"].nome == "Quadra poliesportiva"


def test_carregar_apartamentos_reflete_o_json():
    apartamentos = carregar_apartamentos()
    assert apartamentos["101"].morador == "Helena Prado"
    assert apartamentos["302"].morador == "Rafael Moreira"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_reference_data.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.reference_data'`.

- [ ] **Step 3: Write the implementation**

Create `app/reference_data.py`:

```python
import json
from dataclasses import dataclass
from pathlib import Path

DADOS_DIR = Path(__file__).resolve().parent.parent / "dados"


@dataclass(frozen=True)
class Area:
    id: str
    nome: str
    taxa: float


@dataclass(frozen=True)
class Apartamento:
    numero: str
    morador: str


def carregar_areas(dados_dir: Path = DADOS_DIR) -> dict[str, Area]:
    data = json.loads((dados_dir / "areas.json").read_text(encoding="utf-8"))
    return {
        item["id"]: Area(id=item["id"], nome=item["nome"], taxa=float(item["taxa"]))
        for item in data
    }


def carregar_apartamentos(dados_dir: Path = DADOS_DIR) -> dict[str, Apartamento]:
    data = json.loads((dados_dir / "apartamentos.json").read_text(encoding="utf-8"))
    return {
        item["numero"]: Apartamento(numero=item["numero"], morador=item["morador"])
        for item in data
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_reference_data.py -v`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add app/reference_data.py tests/test_reference_data.py
git commit -m "feat: load areas/apartamentos reference data in memory"
```

---

### Task 3: Regulamento — split into chapters

**Files:**
- Create: `app/regulamento.py`
- Test: `tests/test_regulamento.py`

**Interfaces:**
- Produces: `Capitulo(titulo, conteudo)` dataclass; `carregar_capitulos(path=REGULAMENTO_PATH) -> list[Capitulo]`. Consumed by `app/agents/regulamento.py` to build the chapter lookup at import time (Guarantee 4: never the whole document in context).

- [ ] **Step 1: Write the failing test**

Create `tests/test_regulamento.py`:

```python
from app.regulamento import carregar_capitulos


def test_divide_em_14_capitulos():
    capitulos = carregar_capitulos()
    assert len(capitulos) == 14
    assert capitulos[0].titulo == "Capítulo I: Disposições gerais"
    assert capitulos[-1].titulo == "Capítulo XIV: Disposições finais"


def test_conteudo_de_um_capitulo_nao_vaza_para_o_outro():
    capitulos = carregar_capitulos()
    piscina = next(c for c in capitulos if c.titulo == "Capítulo IV: Piscina")
    assert "piscina" in piscina.conteudo.lower()
    assert "Capítulo V" not in piscina.conteudo
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_regulamento.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.regulamento'`.

- [ ] **Step 3: Write the implementation**

Create `app/regulamento.py`:

```python
import re
from dataclasses import dataclass
from pathlib import Path

REGULAMENTO_PATH = Path(__file__).resolve().parent.parent / "dados" / "regulamento.md"


@dataclass(frozen=True)
class Capitulo:
    titulo: str
    conteudo: str


def carregar_capitulos(path: Path = REGULAMENTO_PATH) -> list[Capitulo]:
    texto = path.read_text(encoding="utf-8")
    partes = re.split(r"(?m)^## (Capítulo .+)$", texto)
    return [
        Capitulo(titulo=titulo.strip(), conteudo=conteudo.strip())
        for titulo, conteudo in zip(partes[1::2], partes[2::2])
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_regulamento.py -v`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add app/regulamento.py tests/test_regulamento.py
git commit -m "feat: split regulamento.md into chapters"
```

---

### Task 4: Database engine, models, and test fixtures

**Files:**
- Create: `app/config.py`
- Create: `app/db.py`
- Create: `app/models.py`
- Create: `tests/conftest.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: `docker compose` Postgres from Task 1 (`aurora_test` database).
- Produces: `Settings(google_api_key, database_url)` / `get_settings()`; `Base` (SQLAlchemy declarative base); `make_engine(database_url) -> AsyncEngine`; `make_session_factory(engine) -> async_sessionmaker[AsyncSession]`; `configurar_session_factory(factory)` / `get_session_factory()` (process-global, used by tool functions in later tasks — ADK session `state` must stay JSON-serializable, so DB access can't ride in `state`); `ReservaModel`, `VisitanteModel`. `tests/conftest.py`'s `engine`/`session_factory` fixtures are reused by every DB-touching test from here on.

- [ ] **Step 1: Write the failing test**

Create `tests/test_models.py`:

```python
from datetime import date

from sqlalchemy import select

from app.models import ReservaModel, VisitanteModel


async def test_criar_tabelas_e_inserir_reserva(session_factory):
    async with session_factory() as session:
        session.add(
            ReservaModel(
                codigo="RSV-TESTE",
                apartamento="101",
                area="quadra",
                data=date(2030, 4, 6),
                status="ativa",
            )
        )
        await session.commit()

        result = await session.execute(
            select(ReservaModel).where(ReservaModel.codigo == "RSV-TESTE")
        )
        reserva = result.scalar_one()
        assert reserva.apartamento == "101"
        assert reserva.status == "ativa"


async def test_duas_reservas_ativas_mesma_area_data_violam_unique(session_factory):
    async with session_factory() as session:
        session.add(
            ReservaModel(codigo="RSV-A", apartamento="101", area="salao-de-festas", data=date(2030, 5, 11), status="ativa")
        )
        await session.commit()

    async with session_factory() as session:
        session.add(
            ReservaModel(codigo="RSV-B", apartamento="201", area="salao-de-festas", data=date(2030, 5, 11), status="ativa")
        )
        from sqlalchemy.exc import IntegrityError

        try:
            await session.commit()
            assert False, "deveria ter violado a constraint UNIQUE"
        except IntegrityError:
            await session.rollback()


async def test_insere_visitante(session_factory):
    async with session_factory() as session:
        session.add(VisitanteModel(apartamento="101", nome="Joana Ribeiro", data=date(2030, 4, 21)))
        await session.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.config'` (or `app.db`/`app.models`, and `fixture 'session_factory' not found`).

- [ ] **Step 3: Write app/config.py**

```python
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    google_api_key: str
    database_url: str


def get_settings() -> Settings:
    return Settings(
        google_api_key=os.environ["GOOGLE_API_KEY"],
        database_url=os.environ["DATABASE_URL"],
    )
```

- [ ] **Step 4: Write app/db.py**

```python
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, future=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


_session_factory: async_sessionmaker[AsyncSession] | None = None


def configurar_session_factory(factory: async_sessionmaker[AsyncSession]) -> None:
    global _session_factory
    _session_factory = factory


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError(
            "session factory não configurada — chame configurar_session_factory() no startup"
        )
    return _session_factory
```

- [ ] **Step 5: Write app/models.py**

```python
from datetime import date

from sqlalchemy import Date, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ReservaModel(Base):
    __tablename__ = "reservas"

    codigo: Mapped[str] = mapped_column(String(32), primary_key=True)
    apartamento: Mapped[str] = mapped_column(String(16), nullable=False)
    area: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ativa")

    __table_args__ = (
        Index(
            "ix_reservas_area_data_ativa",
            "area",
            "data",
            unique=True,
            postgresql_where=text("status = 'ativa'"),
        ),
    )


class VisitanteModel(Base):
    __tablename__ = "visitantes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    apartamento: Mapped[str] = mapped_column(String(16), nullable=False)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    data: Mapped[date] = mapped_column(Date, nullable=False)
```

- [ ] **Step 6: Write tests/conftest.py**

```python
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import pytest_asyncio

from app.db import Base, make_engine, make_session_factory
from app.models import ReservaModel, VisitanteModel  # noqa: F401 (registra os modelos no Base.metadata)

TEST_DATABASE_URL = "postgresql+asyncpg://aurora:aurora@localhost:5432/aurora_test"


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
```

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py -v`
Expected: `3 passed`. (Requires `docker compose up -d` from Task 1 to already be running.)

- [ ] **Step 8: Commit**

```bash
git add app/config.py app/db.py app/models.py tests/conftest.py tests/test_models.py
git commit -m "feat: add async Postgres engine, models, and the area/data partial unique index"
```

---

### Task 5: Repository — reservas/visitantes data access

**Files:**
- Create: `app/repository.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: `app.models.ReservaModel`/`VisitanteModel`, `tests/conftest.py`'s `session_factory` fixture.
- Produces: `Reserva(codigo, apartamento, area, data, status)`, `Visitante(apartamento, nome, data)` dataclasses; `AreaOcupadaError`; `criar_reserva(session, apartamento, area, data) -> Reserva`; `cancelar_reserva(session, apartamento, codigo) -> bool`; `listar_reservas(session, apartamento) -> list[Reserva]`; `data_disponivel(session, area, data) -> bool`; `autorizar_visitante(session, apartamento, nome, data) -> Visitante`; `listar_visitantes(session, apartamento) -> list[Visitante]`. Consumed by `app/agents/reservas.py`, `app/agents/visitantes.py`, and the verification routes.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_repository.py`:

```python
import asyncio
from datetime import date

import pytest

from app import repository


async def test_criar_reserva_retorna_codigo_unico(session_factory):
    async with session_factory() as session:
        reserva = await repository.criar_reserva(session, "101", "quadra", date(2030, 4, 6))
    assert reserva.codigo.startswith("RSV-")
    assert reserva.apartamento == "101"
    assert reserva.status == "ativa"


async def test_segunda_reserva_mesma_area_data_e_recusada(session_factory):
    async with session_factory() as session:
        await repository.criar_reserva(session, "101", "salao-de-festas", date(2030, 4, 20))

    async with session_factory() as session:
        with pytest.raises(repository.AreaOcupadaError):
            await repository.criar_reserva(session, "201", "salao-de-festas", date(2030, 4, 20))


async def test_duas_reservas_concorrentes_so_uma_vence(session_factory):
    async def tentar(apartamento: str):
        async with session_factory() as session:
            try:
                return await repository.criar_reserva(session, apartamento, "salao-de-festas", date(2030, 5, 11))
            except repository.AreaOcupadaError:
                return None

    r1, r2 = await asyncio.gather(tentar("101"), tentar("201"))
    sucesso = [r for r in (r1, r2) if r is not None]
    assert len(sucesso) == 1


async def test_cancelar_reserva_e_soft_delete(session_factory):
    async with session_factory() as session:
        reserva = await repository.criar_reserva(session, "101", "quadra", date(2030, 4, 6))

    async with session_factory() as session:
        cancelada = await repository.cancelar_reserva(session, "101", reserva.codigo)
    assert cancelada is True

    async with session_factory() as session:
        reservas = await repository.listar_reservas(session, "101")
    assert reservas == []  # soft-delete tira da listagem de ativas...

    # ...mas o código continua "existindo": reservar de novo a mesma área/data funciona,
    # e um código novo nunca pode colidir com um cancelado porque codigo é PK.
    async with session_factory() as session:
        nova = await repository.criar_reserva(session, "201", "quadra", date(2030, 4, 6))
    assert nova.codigo != reserva.codigo


async def test_cancelar_reserva_de_outro_apartamento_nao_funciona(session_factory):
    async with session_factory() as session:
        reserva = await repository.criar_reserva(session, "302", "churrasqueira", date(2030, 6, 1))

    async with session_factory() as session:
        resultado = await repository.cancelar_reserva(session, "101", reserva.codigo)
    assert resultado is False

    async with session_factory() as session:
        reservas_302 = await repository.listar_reservas(session, "302")
    assert any(r.codigo == reserva.codigo for r in reservas_302)


async def test_data_disponivel(session_factory):
    async with session_factory() as session:
        assert await repository.data_disponivel(session, "quadra", date(2030, 4, 6)) is True
        await repository.criar_reserva(session, "101", "quadra", date(2030, 4, 6))
    async with session_factory() as session:
        assert await repository.data_disponivel(session, "quadra", date(2030, 4, 6)) is False


async def test_autorizar_e_listar_visitantes(session_factory):
    async with session_factory() as session:
        await repository.autorizar_visitante(session, "101", "Joana Ribeiro", date(2030, 4, 21))
    async with session_factory() as session:
        visitantes = await repository.listar_visitantes(session, "101")
    assert [v.nome for v in visitantes] == ["Joana Ribeiro"]

    async with session_factory() as session:
        visitantes_outro_apto = await repository.listar_visitantes(session, "302")
    assert visitantes_outro_apto == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.repository'`.

- [ ] **Step 3: Write the implementation**

Create `app/repository.py`:

```python
import random
import string
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ReservaModel, VisitanteModel


@dataclass(frozen=True)
class Reserva:
    codigo: str
    apartamento: str
    area: str
    data: date
    status: str


@dataclass(frozen=True)
class Visitante:
    apartamento: str
    nome: str
    data: date


class AreaOcupadaError(Exception):
    """A área já tem uma reserva ativa na data pedida."""


def _gerar_codigo() -> str:
    sufixo = "".join(random.choices(string.digits, k=4))
    return f"RSV-{sufixo}"


async def criar_reserva(session: AsyncSession, apartamento: str, area: str, data: date) -> Reserva:
    for _ in range(5):
        codigo = _gerar_codigo()
        session.add(ReservaModel(codigo=codigo, apartamento=apartamento, area=area, data=data, status="ativa"))
        try:
            await session.commit()
            return Reserva(codigo=codigo, apartamento=apartamento, area=area, data=data, status="ativa")
        except IntegrityError as exc:
            await session.rollback()
            constraint = getattr(exc.orig, "constraint_name", None)
            if constraint == "ix_reservas_area_data_ativa":
                raise AreaOcupadaError(f"{area} já reservada em {data}") from exc
            # colisão de código (chave primária) — tenta outro código.
    raise RuntimeError("não foi possível gerar um código de reserva único após 5 tentativas")


async def cancelar_reserva(session: AsyncSession, apartamento: str, codigo: str) -> bool:
    result = await session.execute(
        select(ReservaModel).where(
            ReservaModel.codigo == codigo,
            ReservaModel.apartamento == apartamento,
            ReservaModel.status == "ativa",
        )
    )
    reserva = result.scalar_one_or_none()
    if reserva is None:
        return False
    reserva.status = "cancelada"
    await session.commit()
    return True


async def listar_reservas(session: AsyncSession, apartamento: str) -> list[Reserva]:
    result = await session.execute(
        select(ReservaModel).where(ReservaModel.apartamento == apartamento, ReservaModel.status == "ativa")
    )
    return [
        Reserva(codigo=r.codigo, apartamento=r.apartamento, area=r.area, data=r.data, status=r.status)
        for r in result.scalars()
    ]


async def data_disponivel(session: AsyncSession, area: str, data: date) -> bool:
    result = await session.execute(
        select(ReservaModel).where(ReservaModel.area == area, ReservaModel.data == data, ReservaModel.status == "ativa")
    )
    return result.scalar_one_or_none() is None


async def autorizar_visitante(session: AsyncSession, apartamento: str, nome: str, data: date) -> Visitante:
    session.add(VisitanteModel(apartamento=apartamento, nome=nome, data=data))
    await session.commit()
    return Visitante(apartamento=apartamento, nome=nome, data=data)


async def listar_visitantes(session: AsyncSession, apartamento: str) -> list[Visitante]:
    result = await session.execute(select(VisitanteModel).where(VisitanteModel.apartamento == apartamento))
    return [Visitante(apartamento=v.apartamento, nome=v.nome, data=v.data) for v in result.scalars()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_repository.py -v`
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add app/repository.py tests/test_repository.py
git commit -m "feat: add reservas/visitantes repository with atomic exclusivity"
```

---

### Task 6: ADK confirmation-scanning helpers

**Files:**
- Create: `app/adk_runtime.py`
- Test: `tests/test_adk_runtime.py`

**Interfaces:**
- Produces: `ConfirmacaoPendente(id, acao, detalhes, invocation_id)`; `confirmacoes_pendentes(events: list[Event]) -> list[ConfirmacaoPendente]`; `encontrar_confirmacao_pendente(events, call_id) -> ConfirmacaoPendente | None`; `montar_resposta_confirmacao(call_id, confirmado) -> types.Content`; `run_com_retry(runner, **kwargs) -> list[Event]` (retries on transient Gemini 503s, observed to happen on the free tier during design). These operate on plain `list[Event]`, never on a live `Session` object, so they're testable without any ADK session service or network call.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_adk_runtime.py`:

```python
from google.adk.events.event import Event
from google.genai import types

from app.adk_runtime import confirmacoes_pendentes, encontrar_confirmacao_pendente, montar_resposta_confirmacao


def _evento_pedido_confirmacao(invocation_id: str, call_id: str, nome_tool: str, args_tool: dict) -> Event:
    return Event(
        invocation_id=invocation_id,
        author="especialista_reservas",
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        id=call_id,
                        name="adk_request_confirmation",
                        args={"originalFunctionCall": {"id": "orig-1", "name": nome_tool, "args": args_tool}},
                    )
                )
            ],
        ),
    )


def _evento_resposta_confirmacao(invocation_id: str, call_id: str, confirmado: bool) -> Event:
    return Event(
        invocation_id=invocation_id,
        author="user",
        content=montar_resposta_confirmacao(call_id, confirmado),
    )


def test_confirmacao_sem_resposta_aparece_como_pendente():
    eventos = [_evento_pedido_confirmacao("inv-1", "call-1", "reservar_area", {"area": "salao-de-festas", "data": "2030-04-20"})]
    pendentes = confirmacoes_pendentes(eventos)
    assert len(pendentes) == 1
    assert pendentes[0].id == "call-1"
    assert pendentes[0].acao == "reservar_area"
    assert pendentes[0].detalhes == {"area": "salao-de-festas", "data": "2030-04-20"}
    assert pendentes[0].invocation_id == "inv-1"


def test_confirmacao_respondida_nao_aparece_mais_como_pendente():
    eventos = [
        _evento_pedido_confirmacao("inv-1", "call-1", "reservar_area", {"area": "quadra", "data": "2030-04-06"}),
        _evento_resposta_confirmacao("inv-1", "call-1", True),
    ]
    assert confirmacoes_pendentes(eventos) == []


def test_encontrar_confirmacao_pendente_por_id():
    eventos = [_evento_pedido_confirmacao("inv-1", "call-1", "autorizar_visitante", {"nome": "Joana Ribeiro", "data": "2030-04-21"})]
    achada = encontrar_confirmacao_pendente(eventos, "call-1")
    assert achada is not None
    assert achada.acao == "autorizar_visitante"

    assert encontrar_confirmacao_pendente(eventos, "id-inexistente") is None


def test_id_ja_respondido_nao_e_encontrado_de_novo():
    eventos = [
        _evento_pedido_confirmacao("inv-1", "call-1", "reservar_area", {"area": "quadra", "data": "2030-04-06"}),
        _evento_resposta_confirmacao("inv-1", "call-1", True),
    ]
    assert encontrar_confirmacao_pendente(eventos, "call-1") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_adk_runtime.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.adk_runtime'`.

- [ ] **Step 3: Write the implementation**

Create `app/adk_runtime.py`:

```python
import asyncio
from dataclasses import dataclass
from typing import Any

from google.adk.events.event import Event
from google.genai import errors as genai_errors
from google.genai import types

CONFIRMATION_FUNCTION_NAME = "adk_request_confirmation"


@dataclass(frozen=True)
class ConfirmacaoPendente:
    id: str
    acao: str
    detalhes: dict[str, Any]
    invocation_id: str


def _function_calls(events: list[Event]):
    for event in events:
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            if part.function_call:
                yield event, part.function_call


def _ids_respondidos(events: list[Event]) -> set[str]:
    ids: set[str] = set()
    for event in events:
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            if part.function_response and part.function_response.id:
                ids.add(part.function_response.id)
    return ids


def confirmacoes_pendentes(events: list[Event]) -> list[ConfirmacaoPendente]:
    respondidos = _ids_respondidos(events)
    pendentes: list[ConfirmacaoPendente] = []
    for event, call in _function_calls(events):
        if call.name != CONFIRMATION_FUNCTION_NAME or call.id in respondidos:
            continue
        original = (call.args or {}).get("originalFunctionCall") or {}
        pendentes.append(
            ConfirmacaoPendente(
                id=call.id,
                acao=original.get("name", ""),
                detalhes=original.get("args") or {},
                invocation_id=event.invocation_id,
            )
        )
    return pendentes


def encontrar_confirmacao_pendente(events: list[Event], call_id: str) -> ConfirmacaoPendente | None:
    for pendente in confirmacoes_pendentes(events):
        if pendente.id == call_id:
            return pendente
    return None


def montar_resposta_confirmacao(call_id: str, confirmado: bool) -> types.Content:
    return types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=call_id,
                    name=CONFIRMATION_FUNCTION_NAME,
                    response={"confirmed": confirmado},
                )
            )
        ],
    )


async def run_com_retry(runner, **kwargs) -> list[Event]:
    """Coleta todos os eventos de run_async, tentando de novo em caso de 503
    transitório do Gemini (observado no tier gratuito durante o design)."""
    ultimo_erro: Exception | None = None
    for tentativa in range(5):
        try:
            return [event async for event in runner.run_async(**kwargs)]
        except genai_errors.ServerError as exc:
            ultimo_erro = exc
            await asyncio.sleep(5 * (tentativa + 1))
    assert ultimo_erro is not None
    raise ultimo_erro
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_adk_runtime.py -v`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add app/adk_runtime.py tests/test_adk_runtime.py
git commit -m "feat: add ADK confirmation-scanning helpers and retry wrapper"
```

---

### Task 7: ADK App/Runner wiring and the confirmation-resume regression test

**Files:**
- Create: `app/adk_app.py`
- Test: `tests/test_adk_app.py`

**Interfaces:**
- Consumes: `app.config.get_settings`, `app.adk_runtime.run_com_retry/confirmacoes_pendentes/montar_resposta_confirmacao`.
- Produces: `APP_NAME`, `ADK_USER_ID` constants; `make_session_service() -> DatabaseSessionService`; `make_app(root_agent, name=APP_NAME) -> App`; `make_runner(root_agent, session_service) -> Runner`. Consumed by `app/main.py` (Task 12) and `app/agents/root.py`'s end-to-end test (Task 11).

This task's test requires a real `GOOGLE_API_KEY` in `.env` and Postgres running (`docker compose up -d`) — it makes real calls to the Gemini API. It is the permanent regression test for the exact mechanism validated by the throwaway spike during design: without `resumability_config`, the explicit `invocation_id`, and answering with the `adk_request_confirmation` call's own id, this silently does nothing instead of failing loudly.

- [ ] **Step 1: Write the failing test**

Create `tests/test_adk_app.py`:

```python
import uuid

import pytest
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.genai import types

from app import adk_runtime
from app.adk_app import ADK_USER_ID, APP_NAME, make_runner, make_session_service

EXECUTADO: list[str] = []


def _acao_critica(valor: str) -> dict:
    EXECUTADO.append(valor)
    return {"status": "ok", "valor": valor}


def _build_agente_fixture() -> LlmAgent:
    return LlmAgent(
        name="agente_fixture",
        model="gemini-3.5-flash-lite",
        description="Agente de teste com uma tool que exige confirmação.",
        instruction="Quando o usuário pedir pra executar algo, chame acao_critica com o valor pedido.",
        tools=[FunctionTool(_acao_critica, require_confirmation=True)],
    )


@pytest.mark.asyncio
async def test_confirmacao_sobrevive_a_novo_runner_mesmo_banco():
    EXECUTADO.clear()
    session_service = make_session_service()
    session_id = str(uuid.uuid4())
    await session_service.create_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    runner = make_runner(_build_agente_fixture(), session_service)

    msg = types.Content(role="user", parts=[types.Part(text="Execute a ação crítica com o valor 'teste123'")])
    await adk_runtime.run_com_retry(runner, user_id=ADK_USER_ID, session_id=session_id, new_message=msg)

    session = await session_service.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    pendentes = adk_runtime.confirmacoes_pendentes(session.events)
    assert len(pendentes) == 1
    assert not EXECUTADO

    # Simula reinício do processo: nova instância de session_service/runner, mesmo banco.
    session_service2 = make_session_service()
    runner2 = make_runner(_build_agente_fixture(), session_service2)
    pendente = pendentes[0]
    resposta = adk_runtime.montar_resposta_confirmacao(pendente.id, True)
    await adk_runtime.run_com_retry(
        runner2,
        user_id=ADK_USER_ID,
        session_id=session_id,
        invocation_id=pendente.invocation_id,
        new_message=resposta,
    )

    assert EXECUTADO == ["teste123"]

    session_depois = await session_service2.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    assert adk_runtime.confirmacoes_pendentes(session_depois.events) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_adk_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.adk_app'`.

- [ ] **Step 3: Write the implementation**

Create `app/adk_app.py`:

```python
from google.adk.agents import LlmAgent
from google.adk.apps._configs import ResumabilityConfig
from google.adk.apps.app import App
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService

from app.config import get_settings

APP_NAME = "residencial_aurora"
ADK_USER_ID = "residencial-aurora"


def make_session_service() -> DatabaseSessionService:
    settings = get_settings()
    return DatabaseSessionService(db_url=settings.database_url)


def make_app(root_agent: LlmAgent, name: str = APP_NAME) -> App:
    return App(
        name=name,
        root_agent=root_agent,
        resumability_config=ResumabilityConfig(is_resumable=True),
    )


def make_runner(root_agent: LlmAgent, session_service: DatabaseSessionService) -> Runner:
    return Runner(app=make_app(root_agent), session_service=session_service)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_adk_app.py -v`
Expected: `1 passed`. (Requires `GOOGLE_API_KEY` in `.env` and `docker compose up -d` already running — this test makes real Gemini API calls and may take 10-30s.)

- [ ] **Step 5: Commit**

```bash
git add app/adk_app.py tests/test_adk_app.py
git commit -m "feat: wire ADK App/Runner with resumability over Postgres sessions"
```

---

### Task 8: especialista_reservas agent

**Files:**
- Create: `app/agents/__init__.py`
- Create: `app/agents/reservas.py`
- Test: `tests/test_agents_reservas.py`

**Interfaces:**
- Consumes: `app.reference_data.carregar_areas`, `app.repository.*`, `app.db.get_session_factory`.
- Produces: `reservar_area(area, data, tool_context) -> dict`, `cancelar_reserva(codigo, tool_context) -> dict`, `listar_reservas(tool_context) -> dict`, `build_especialista_reservas() -> LlmAgent`. Consumed by `app/agents/root.py` (Task 11).

- [ ] **Step 1: Write the failing tests**

Create `app/agents/__init__.py` (empty file).

Create `tests/test_agents_reservas.py`:

```python
import inspect
from datetime import date

from app import db, repository
from app.agents.reservas import build_especialista_reservas, cancelar_reserva, listar_reservas, reservar_area


class _ToolContextFake:
    def __init__(self, state: dict):
        self.state = state


def test_reservar_area_nao_aceita_apartamento_como_parametro():
    assert "apartamento" not in inspect.signature(reservar_area).parameters


def test_cancelar_reserva_nao_aceita_apartamento_como_parametro():
    assert "apartamento" not in inspect.signature(cancelar_reserva).parameters


async def test_reservar_area_sem_taxa_nao_pede_confirmacao_e_usa_apartamento_da_sessao(session_factory):
    db.configurar_session_factory(session_factory)
    ctx = _ToolContextFake({"apartamento": "101"})
    resultado = await reservar_area(area="quadra", data="2030-04-06", tool_context=ctx)
    assert resultado["status"] == "reservada"

    async with session_factory() as session:
        reservas = await repository.listar_reservas(session, "101")
    assert any(r.area == "quadra" and r.data == date(2030, 4, 6) for r in reservas)


async def test_reservar_area_ocupada_e_recusada_sem_excecao(session_factory):
    db.configurar_session_factory(session_factory)
    ctx1 = _ToolContextFake({"apartamento": "101"})
    ctx2 = _ToolContextFake({"apartamento": "201"})
    await reservar_area(area="churrasqueira", data="2030-06-01", tool_context=ctx1)
    resultado = await reservar_area(area="churrasqueira", data="2030-06-01", tool_context=ctx2)
    assert resultado["status"] == "recusada"


async def test_cancelar_reserva_usa_apartamento_da_sessao(session_factory):
    db.configurar_session_factory(session_factory)
    ctx_101 = _ToolContextFake({"apartamento": "101"})
    criada = await reservar_area(area="quadra", data="2030-04-06", tool_context=ctx_101)

    ctx_302 = _ToolContextFake({"apartamento": "302"})
    resultado_errado = await cancelar_reserva(codigo=criada["codigo"], tool_context=ctx_302)
    assert resultado_errado["status"] == "nao_encontrada"

    resultado_certo = await cancelar_reserva(codigo=criada["codigo"], tool_context=ctx_101)
    assert resultado_certo["status"] == "cancelada"


async def test_listar_reservas_usa_apartamento_da_sessao(session_factory):
    db.configurar_session_factory(session_factory)
    await reservar_area(area="quadra", data="2030-04-06", tool_context=_ToolContextFake({"apartamento": "101"}))
    resultado = await listar_reservas(tool_context=_ToolContextFake({"apartamento": "101"}))
    assert len(resultado["reservas"]) == 1
    resultado_outro = await listar_reservas(tool_context=_ToolContextFake({"apartamento": "302"}))
    assert resultado_outro["reservas"] == []


def test_build_especialista_reservas_tem_as_tres_tools():
    agente = build_especialista_reservas()
    nomes = {tool.name for tool in agente.tools}
    assert nomes == {"reservar_area", "cancelar_reserva", "listar_reservas"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agents_reservas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.reservas'`.

- [ ] **Step 3: Write the implementation**

Create `app/agents/reservas.py`:

```python
from datetime import date

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext

from app import reference_data, repository
from app.db import get_session_factory


def _requer_confirmacao_reserva(area: str, data: str) -> bool:
    info = reference_data.carregar_areas().get(area)
    return bool(info and info.taxa > 0)


async def reservar_area(area: str, data: str, tool_context: ToolContext) -> dict:
    """Reserva uma área comum do condomínio na data informada, para o
    apartamento da sessão atual.

    Args:
        area: id da área comum (ex.: "salao-de-festas", "churrasqueira", "quadra").
        data: data da reserva, no formato AAAA-MM-DD.
    """
    apartamento = tool_context.state["apartamento"]
    info = reference_data.carregar_areas().get(area)
    if info is None:
        return {"erro": f"área '{area}' não existe"}
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            reserva = await repository.criar_reserva(session, apartamento, area, date.fromisoformat(data))
        except repository.AreaOcupadaError:
            return {"status": "recusada", "motivo": "área já reservada nessa data"}
    return {"status": "reservada", "codigo": reserva.codigo, "area": area, "data": data}


async def cancelar_reserva(codigo: str, tool_context: ToolContext) -> dict:
    """Cancela uma reserva do apartamento da sessão atual.

    Args:
        codigo: código da reserva a cancelar.
    """
    apartamento = tool_context.state["apartamento"]
    session_factory = get_session_factory()
    async with session_factory() as session:
        cancelada = await repository.cancelar_reserva(session, apartamento, codigo)
    if not cancelada:
        return {"status": "nao_encontrada"}
    return {"status": "cancelada", "codigo": codigo}


async def listar_reservas(tool_context: ToolContext) -> dict:
    """Lista as reservas ativas do apartamento da sessão atual."""
    apartamento = tool_context.state["apartamento"]
    session_factory = get_session_factory()
    async with session_factory() as session:
        reservas = await repository.listar_reservas(session, apartamento)
    return {"reservas": [{"codigo": r.codigo, "area": r.area, "data": r.data.isoformat()} for r in reservas]}


def build_especialista_reservas() -> LlmAgent:
    return LlmAgent(
        name="especialista_reservas",
        model="gemini-3.5-flash-lite",
        description=(
            "Especialista em reservar e cancelar o uso de áreas comuns "
            "(salão de festas, churrasqueira, quadra) do condomínio."
        ),
        instruction=(
            "Você cuida de reservas de áreas comuns do condomínio para o "
            "apartamento do morador. Use reservar_area para criar uma "
            "reserva, cancelar_reserva para cancelar, e listar_reservas "
            "para consultar as reservas atuais. Nunca peça o número do "
            "apartamento ao morador — ele já é conhecido pelo sistema."
        ),
        tools=[
            FunctionTool(reservar_area, require_confirmation=_requer_confirmacao_reserva),
            FunctionTool(cancelar_reserva),
            FunctionTool(listar_reservas),
        ],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_agents_reservas.py -v`
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add app/agents/__init__.py app/agents/reservas.py tests/test_agents_reservas.py
git commit -m "feat: add especialista_reservas agent and tools"
```

---

### Task 9: especialista_visitantes agent

**Files:**
- Create: `app/agents/visitantes.py`
- Test: `tests/test_agents_visitantes.py`

**Interfaces:**
- Consumes: `app.repository.*`, `app.db.get_session_factory`.
- Produces: `autorizar_visitante(nome, data, tool_context) -> dict`, `listar_visitantes(tool_context) -> dict`, `build_especialista_visitantes() -> LlmAgent`. Consumed by `app/agents/root.py` (Task 11).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agents_visitantes.py`:

```python
import inspect

from app import db
from app.agents.visitantes import autorizar_visitante, build_especialista_visitantes, listar_visitantes


class _ToolContextFake:
    def __init__(self, state: dict):
        self.state = state


def test_autorizar_visitante_nao_aceita_apartamento_como_parametro():
    assert "apartamento" not in inspect.signature(autorizar_visitante).parameters


async def test_autorizar_e_listar_usa_apartamento_da_sessao(session_factory):
    db.configurar_session_factory(session_factory)
    resultado = await autorizar_visitante(
        nome="Joana Ribeiro", data="2030-04-21", tool_context=_ToolContextFake({"apartamento": "101"})
    )
    assert resultado["status"] == "autorizado"

    visitantes_101 = await listar_visitantes(tool_context=_ToolContextFake({"apartamento": "101"}))
    assert visitantes_101["visitantes"] == [{"nome": "Joana Ribeiro", "data": "2030-04-21"}]

    visitantes_302 = await listar_visitantes(tool_context=_ToolContextFake({"apartamento": "302"}))
    assert visitantes_302["visitantes"] == []


def test_build_especialista_visitantes_tem_as_duas_tools_e_exige_confirmacao():
    agente = build_especialista_visitantes()
    tools_por_nome = {tool.name: tool for tool in agente.tools}
    assert set(tools_por_nome) == {"autorizar_visitante", "listar_visitantes"}
    assert tools_por_nome["autorizar_visitante"]._require_confirmation is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agents_visitantes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.visitantes'`.

- [ ] **Step 3: Write the implementation**

Create `app/agents/visitantes.py`:

```python
from datetime import date

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext

from app import repository
from app.db import get_session_factory


async def autorizar_visitante(nome: str, data: str, tool_context: ToolContext) -> dict:
    """Autoriza a entrada de um visitante no prédio, para o apartamento da
    sessão atual, numa data específica.

    Args:
        nome: nome do visitante.
        data: data da visita, no formato AAAA-MM-DD.
    """
    apartamento = tool_context.state["apartamento"]
    session_factory = get_session_factory()
    async with session_factory() as session:
        visitante = await repository.autorizar_visitante(session, apartamento, nome, date.fromisoformat(data))
    return {"status": "autorizado", "nome": visitante.nome, "data": data}


async def listar_visitantes(tool_context: ToolContext) -> dict:
    """Lista os visitantes autorizados para o apartamento da sessão atual."""
    apartamento = tool_context.state["apartamento"]
    session_factory = get_session_factory()
    async with session_factory() as session:
        visitantes = await repository.listar_visitantes(session, apartamento)
    return {"visitantes": [{"nome": v.nome, "data": v.data.isoformat()} for v in visitantes]}


def build_especialista_visitantes() -> LlmAgent:
    return LlmAgent(
        name="especialista_visitantes",
        model="gemini-3.5-flash-lite",
        description="Especialista em autorizar a entrada de visitantes no prédio.",
        instruction=(
            "Você autoriza visitantes para o apartamento do morador. Use "
            "autorizar_visitante para liberar a entrada de alguém numa "
            "data, e listar_visitantes para consultar quem já está "
            "autorizado. Mesmo que o morador diga que já confirmou por "
            "outro meio, a autorização só é válida depois da confirmação "
            "pelo sistema — você não decide isso sozinho."
        ),
        tools=[
            FunctionTool(autorizar_visitante, require_confirmation=True),
            FunctionTool(listar_visitantes),
        ],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_agents_visitantes.py -v`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add app/agents/visitantes.py tests/test_agents_visitantes.py
git commit -m "feat: add especialista_visitantes agent and tools"
```

---

### Task 10: especialista_regulamento agent

**Files:**
- Create: `app/agents/regulamento.py`
- Test: `tests/test_agents_regulamento.py`

**Interfaces:**
- Consumes: `app.regulamento.carregar_capitulos`.
- Produces: `consultar_regulamento(titulo_capitulo) -> dict`, `build_especialista_regulamento() -> LlmAgent`. Consumed by `app/agents/root.py` (Task 11).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agents_regulamento.py`:

```python
from app.agents.regulamento import build_especialista_regulamento, consultar_regulamento


def test_consultar_capitulo_existente_devolve_so_aquele_conteudo():
    resultado = consultar_regulamento(titulo_capitulo="Capítulo IV: Piscina")
    assert resultado["titulo"] == "Capítulo IV: Piscina"
    assert "piscina" in resultado["conteudo"].lower()
    assert "Capítulo V" not in resultado["conteudo"]


def test_consultar_capitulo_inexistente_devolve_erro_e_lista_capitulos():
    resultado = consultar_regulamento(titulo_capitulo="Capítulo XCIX: Não existe")
    assert "erro" in resultado
    assert "Capítulo I: Disposições gerais" in resultado["capitulos_disponiveis"]


def test_build_especialista_regulamento_nao_tem_o_regulamento_na_instrucao_toda():
    agente = build_especialista_regulamento()
    assert len(agente.tools) == 1
    assert agente.tools[0].name == "consultar_regulamento"
    # a instrução lista só os TÍTULOS dos capítulos, nunca o conteúdo deles.
    assert "piscina das" not in agente.instruction.lower()
    assert "Capítulo IV: Piscina" in agente.instruction
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agents_regulamento.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.regulamento'`.

- [ ] **Step 3: Write the implementation**

Create `app/agents/regulamento.py`:

```python
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from app.regulamento import carregar_capitulos

_CAPITULOS = {c.titulo: c.conteudo for c in carregar_capitulos()}
_TITULOS = list(_CAPITULOS.keys())


def consultar_regulamento(titulo_capitulo: str) -> dict:
    """Devolve o conteúdo de um capítulo do regulamento interno do condomínio.

    Args:
        titulo_capitulo: o título exato de um dos capítulos disponíveis.
    """
    conteudo = _CAPITULOS.get(titulo_capitulo)
    if conteudo is None:
        return {"erro": "capítulo não encontrado", "capitulos_disponiveis": _TITULOS}
    return {"titulo": titulo_capitulo, "conteudo": conteudo}


def build_especialista_regulamento() -> LlmAgent:
    lista = "\n".join(f"- {titulo}" for titulo in _TITULOS)
    return LlmAgent(
        name="especialista_regulamento",
        model="gemini-3.5-flash-lite",
        description="Especialista em responder dúvidas sobre o regulamento interno do condomínio.",
        instruction=(
            "Você responde dúvidas sobre o regulamento interno do "
            "condomínio. Os capítulos disponíveis são:\n"
            f"{lista}\n\n"
            "Escolha o título EXATO do capítulo mais relevante pra "
            "pergunta e chame consultar_regulamento com esse título. "
            "Responda de forma completa em relação ao artigo encontrado "
            "(não corte a resposta na primeira frase que bate com a "
            "pergunta). Se o próprio regulamento remeter a outro "
            "documento (como 'a Convenção') para um dado específico, "
            "deixe isso explícito na resposta em vez de parecer uma "
            "resposta completa. Nunca responda com base em capítulos que "
            "você não consultou."
        ),
        tools=[FunctionTool(consultar_regulamento)],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_agents_regulamento.py -v`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add app/agents/regulamento.py tests/test_agents_regulamento.py
git commit -m "feat: add especialista_regulamento agent with per-chapter retrieval"
```

---

### Task 11: root_agent and the business-level confirmation flow test

**Files:**
- Create: `app/agents/root.py`
- Test: `tests/test_root_agent_fluxo.py`

**Interfaces:**
- Consumes: `build_especialista_reservas`, `build_especialista_visitantes`, `build_especialista_regulamento`, `app.adk_app.*`, `app.adk_runtime.*`, `app.db.configurar_session_factory`.
- Produces: `build_root_agent() -> LlmAgent`. Consumed by `app/main.py` (Task 12).

This task's test requires `GOOGLE_API_KEY` and Postgres running. It is the first test exercising the real multi-agent transfer (root → especialista_reservas) together with the confirmation mechanism and the actual repository — i.e. it proves Guarantees 1 and 2 hold through the full agent graph, not just in the isolated pieces tested so far.

- [ ] **Step 1: Write the failing test**

Create `tests/test_root_agent_fluxo.py`:

```python
import uuid
from datetime import date

import pytest

from app import db, repository
from app.adk_app import ADK_USER_ID, APP_NAME, make_runner, make_session_service
from app.adk_runtime import confirmacoes_pendentes, montar_resposta_confirmacao, run_com_retry
from app.agents.root import build_root_agent
from google.genai import types


@pytest.mark.asyncio
async def test_reserva_sem_taxa_nao_gera_confirmacao(session_factory):
    db.configurar_session_factory(session_factory)
    session_service = make_session_service()
    session_id = str(uuid.uuid4())
    await session_service.create_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id, state={"apartamento": "101"})
    runner = make_runner(build_root_agent(), session_service)

    msg = types.Content(role="user", parts=[types.Part(text="Reserve a quadra para 2030-04-06")])
    await run_com_retry(runner, user_id=ADK_USER_ID, session_id=session_id, new_message=msg)

    session = await session_service.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    assert confirmacoes_pendentes(session.events) == []

    async with session_factory() as db_session:
        reservas = await repository.listar_reservas(db_session, "101")
    assert any(r.area == "quadra" and r.data == date(2030, 4, 6) for r in reservas)


@pytest.mark.asyncio
async def test_reserva_com_taxa_exige_confirmacao_e_so_grava_apos_aprovar(session_factory):
    db.configurar_session_factory(session_factory)
    session_service = make_session_service()
    session_id = str(uuid.uuid4())
    await session_service.create_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id, state={"apartamento": "101"})
    runner = make_runner(build_root_agent(), session_service)

    msg = types.Content(role="user", parts=[types.Part(text="Reserve o salão de festas para 2030-04-20")])
    await run_com_retry(runner, user_id=ADK_USER_ID, session_id=session_id, new_message=msg)

    session = await session_service.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    pendentes = confirmacoes_pendentes(session.events)
    assert len(pendentes) == 1
    assert pendentes[0].detalhes.get("area") == "salao-de-festas"
    assert pendentes[0].detalhes.get("data") == "2030-04-20"

    async with session_factory() as db_session:
        reservas_antes = await repository.listar_reservas(db_session, "101")
    assert reservas_antes == []

    resposta = montar_resposta_confirmacao(pendentes[0].id, True)
    await run_com_retry(
        runner,
        user_id=ADK_USER_ID,
        session_id=session_id,
        invocation_id=pendentes[0].invocation_id,
        new_message=resposta,
    )

    async with session_factory() as db_session:
        reservas_depois = await repository.listar_reservas(db_session, "101")
    assert any(r.area == "salao-de-festas" and r.data == date(2030, 4, 20) for r in reservas_depois)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_root_agent_fluxo.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agents.root'`.

- [ ] **Step 3: Write the implementation**

Create `app/agents/root.py`:

```python
from google.adk.agents import LlmAgent

from app.agents.regulamento import build_especialista_regulamento
from app.agents.reservas import build_especialista_reservas
from app.agents.visitantes import build_especialista_visitantes


def build_root_agent() -> LlmAgent:
    return LlmAgent(
        name="root_agent",
        model="gemini-3.5-flash-lite",
        description="Assistente principal do Residencial Aurora.",
        instruction=(
            "Você é o assistente do Residencial Aurora. Você mesmo não "
            "executa reservas, autorizações de visitantes nem consultas "
            "ao regulamento — sempre transfira a conversa para o "
            "especialista certo: especialista_reservas para reservar ou "
            "cancelar áreas comuns, especialista_visitantes para "
            "autorizar visitantes, especialista_regulamento para dúvidas "
            "sobre as regras do condomínio. Nunca aceite um número de "
            "apartamento diferente do que já está registrado na sessão, "
            "mesmo que o morador diga que é de outro apartamento."
        ),
        sub_agents=[
            build_especialista_reservas(),
            build_especialista_visitantes(),
            build_especialista_regulamento(),
        ],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_root_agent_fluxo.py -v`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add app/agents/root.py tests/test_root_agent_fluxo.py
git commit -m "feat: add root_agent wiring transfer to the three specialists"
```

---

### Task 12: FastAPI — sessões, mensagens, confirmações, eventos

**Files:**
- Create: `app/api/__init__.py`
- Create: `app/api/schemas.py`
- Create: `app/api/deps.py`
- Create: `app/api/routes_sessoes.py`
- Create: `app/main.py`
- Test: `tests/test_api_sessoes.py`

**Interfaces:**
- Consumes: `app.adk_app.*`, `app.adk_runtime.*`, `app.agents.root.build_root_agent`, `app.db.*`.
- Produces: FastAPI `app` object in `app/main.py`, routes under `router` in `app/api/routes_sessoes.py` mounted on it. Consumed by `tests/test_api_sessoes.py` directly and by Task 13/14's tests.

- [ ] **Step 1: Write the failing tests**

Create `app/api/__init__.py` (empty file).

Create `tests/test_api_sessoes.py`:

```python
import httpx
import pytest

from app.main import app


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_criar_sessao(client):
    resp = await client.post("/sessoes", json={"apartamento": "101"})
    assert resp.status_code == 201
    assert "session_id" in resp.json()


async def test_sessao_301_nao_ve_dados_do_302(client):
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

    # Negar não grava nada.
    resp_negado = await client.post(f"/sessoes/{sessao}/confirmacoes", json={"id": confirmacao_id, "confirmado": False})
    assert resp_negado.status_code == 200

    resp_reservas = await client.get("/apartamentos/101/reservas")
    assert not any(r["area"] == "salao-de-festas" and r["data"] == "2030-04-20" for r in resp_reservas.json())

    # Repete o pedido e aprova.
    resp2 = await client.post(f"/sessoes/{sessao}/mensagens", json={"texto": "Reserve o salão de festas para 2030-04-20"})
    nova_confirmacao_id = resp2.json()["confirmacoes_pendentes"][0]["id"]
    resp_aprovado = await client.post(f"/sessoes/{sessao}/confirmacoes", json={"id": nova_confirmacao_id, "confirmado": True})
    assert resp_aprovado.status_code == 200

    resp_reservas_depois = await client.get("/apartamentos/101/reservas")
    assert any(r["area"] == "salao-de-festas" and r["data"] == "2030-04-20" for r in resp_reservas_depois.json())

    # Reenviar a mesma confirmação já respondida recebe 409.
    resp_repetido = await client.post(f"/sessoes/{sessao}/confirmacoes", json={"id": nova_confirmacao_id, "confirmado": True})
    assert resp_repetido.status_code == 409


async def test_confirmacao_com_id_inexistente_e_409(client):
    sessao = (await client.post("/sessoes", json={"apartamento": "101"})).json()["session_id"]
    resp = await client.post(f"/sessoes/{sessao}/confirmacoes", json={"id": "id-inexistente", "confirmado": True})
    assert resp.status_code == 409


async def test_eventos_de_sessao_inexistente_e_404(client):
    resp = await client.get("/sessoes/sessao-inexistente/eventos")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_sessoes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`.

- [ ] **Step 3: Write app/api/schemas.py**

```python
from typing import Any

from pydantic import BaseModel


class CriarSessaoRequest(BaseModel):
    apartamento: str


class CriarSessaoResponse(BaseModel):
    session_id: str


class EnviarMensagemRequest(BaseModel):
    texto: str


class ConfirmacaoPendenteResponse(BaseModel):
    id: str
    acao: str
    detalhes: dict[str, Any]


class MensagemResponse(BaseModel):
    resposta: str
    confirmacoes_pendentes: list[ConfirmacaoPendenteResponse]


class ResponderConfirmacaoRequest(BaseModel):
    id: str
    confirmado: bool


class ReservaResponse(BaseModel):
    codigo: str
    area: str
    data: str


class VisitanteResponse(BaseModel):
    nome: str
    data: str
```

- [ ] **Step 4: Write app/api/deps.py**

```python
from fastapi import Request


def get_runner(request: Request):
    return request.app.state.runner


def get_session_service(request: Request):
    return request.app.state.session_service


def get_db_session_factory(request: Request):
    return request.app.state.session_factory
```

- [ ] **Step 5: Write app/api/routes_sessoes.py**

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from google.genai import types

from app import adk_runtime
from app.adk_app import ADK_USER_ID, APP_NAME
from app.api.deps import get_runner, get_session_service
from app.api.schemas import (
    ConfirmacaoPendenteResponse,
    CriarSessaoRequest,
    CriarSessaoResponse,
    EnviarMensagemRequest,
    MensagemResponse,
    ResponderConfirmacaoRequest,
)

router = APIRouter()


def _montar_resposta(events, session) -> MensagemResponse:
    textos = [
        part.text
        for event in events
        if event.content and event.content.parts
        for part in event.content.parts
        if part.text
    ]
    pendentes = adk_runtime.confirmacoes_pendentes(session.events)
    return MensagemResponse(
        resposta="".join(textos),
        confirmacoes_pendentes=[
            ConfirmacaoPendenteResponse(id=p.id, acao=p.acao, detalhes=p.detalhes) for p in pendentes
        ],
    )


@router.post("/sessoes", status_code=201)
async def criar_sessao(body: CriarSessaoRequest, session_service=Depends(get_session_service)) -> CriarSessaoResponse:
    session_id = str(uuid.uuid4())
    await session_service.create_session(
        app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id, state={"apartamento": body.apartamento}
    )
    return CriarSessaoResponse(session_id=session_id)


@router.post("/sessoes/{session_id}/mensagens")
async def enviar_mensagem(
    session_id: str,
    body: EnviarMensagemRequest,
    runner=Depends(get_runner),
    session_service=Depends(get_session_service),
) -> MensagemResponse:
    session = await session_service.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    if session is None:
        raise HTTPException(status_code=404)
    msg = types.Content(role="user", parts=[types.Part(text=body.texto)])
    events = await adk_runtime.run_com_retry(runner, user_id=ADK_USER_ID, session_id=session_id, new_message=msg)
    session = await session_service.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    return _montar_resposta(events, session)


@router.post("/sessoes/{session_id}/confirmacoes")
async def responder_confirmacao(
    session_id: str,
    body: ResponderConfirmacaoRequest,
    runner=Depends(get_runner),
    session_service=Depends(get_session_service),
) -> MensagemResponse:
    session = await session_service.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    if session is None:
        raise HTTPException(status_code=404)
    pendente = adk_runtime.encontrar_confirmacao_pendente(session.events, body.id)
    if pendente is None:
        raise HTTPException(status_code=409)
    resposta = adk_runtime.montar_resposta_confirmacao(body.id, body.confirmado)
    events = await adk_runtime.run_com_retry(
        runner,
        user_id=ADK_USER_ID,
        session_id=session_id,
        invocation_id=pendente.invocation_id,
        new_message=resposta,
    )
    session = await session_service.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    return _montar_resposta(events, session)


@router.get("/sessoes/{session_id}/eventos")
async def listar_eventos(session_id: str, session_service=Depends(get_session_service)):
    session = await session_service.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    if session is None:
        raise HTTPException(status_code=404)
    return [event.model_dump(mode="json", exclude_none=True) for event in session.events]
```

- [ ] **Step 6: Write app/main.py**

```python
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
```

Note: `app/main.py` imports `app.api.routes_verificacao`, which does not exist yet — Task 13 creates it. Create a temporary empty router so this task's tests can run on their own:

Create `app/api/routes_verificacao.py`:

```python
from fastapi import APIRouter

router = APIRouter()
```

(Task 13 replaces this file's contents with the real routes.)

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run pytest tests/test_api_sessoes.py -v`
Expected: `5 passed`. (Requires `docker compose up -d` and a valid `GOOGLE_API_KEY`; makes real Gemini calls, can take 1-2 minutes.)

- [ ] **Step 8: Commit**

```bash
git add app/api/__init__.py app/api/schemas.py app/api/deps.py app/api/routes_sessoes.py app/api/routes_verificacao.py app/main.py tests/test_api_sessoes.py
git commit -m "feat: add FastAPI sessoes/mensagens/confirmacoes/eventos routes"
```

---

### Task 13: FastAPI — rotas de verificação

**Files:**
- Modify: `app/api/routes_verificacao.py`
- Test: `tests/test_api_verificacao.py`

**Interfaces:**
- Consumes: `app.repository.listar_reservas/listar_visitantes`, `app.api.deps.get_db_session_factory`.
- Produces: `GET /apartamentos/{numero}/reservas`, `GET /apartamentos/{numero}/visitantes`, mounted via the `router` already included by `app/main.py` in Task 12.

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_verificacao.py`:

```python
import httpx
import pytest

from app import db
from app.main import app


@pytest.fixture
async def client():
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_verificacao.py -v`
Expected: FAIL — both routes 404 (the router from Task 12 has no routes yet).

- [ ] **Step 3: Write the implementation**

Replace the contents of `app/api/routes_verificacao.py`:

```python
from fastapi import APIRouter, Depends

from app import repository
from app.api.deps import get_db_session_factory
from app.api.schemas import ReservaResponse, VisitanteResponse

router = APIRouter()


@router.get("/apartamentos/{numero}/reservas")
async def reservas_do_apartamento(numero: str, session_factory=Depends(get_db_session_factory)) -> list[ReservaResponse]:
    async with session_factory() as session:
        reservas = await repository.listar_reservas(session, numero)
    return [ReservaResponse(codigo=r.codigo, area=r.area, data=r.data.isoformat()) for r in reservas]


@router.get("/apartamentos/{numero}/visitantes")
async def visitantes_do_apartamento(numero: str, session_factory=Depends(get_db_session_factory)) -> list[VisitanteResponse]:
    async with session_factory() as session:
        visitantes = await repository.listar_visitantes(session, numero)
    return [VisitanteResponse(nome=v.nome, data=v.data.isoformat()) for v in visitantes]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api_verificacao.py -v`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add app/api/routes_verificacao.py tests/test_api_verificacao.py
git commit -m "feat: add GET /apartamentos/{numero}/reservas and /visitantes routes"
```

---

### Task 14: Concurrency (Guarantee 5) and restart persistence (Guarantee 3) at HTTP level

**Files:**
- Test: `tests/test_concorrencia_http.py`
- Test: `tests/test_restart_persistencia.py`

**Interfaces:**
- Consumes: the full `app.main.app` from Tasks 12-13, `app.adk_app.make_session_service/make_runner`, `app.agents.root.build_root_agent`.
- Produces: nothing new — these are pure regression tests proving Guarantees 3 and 5 hold at the HTTP contract level, not just in the unit-tested layers underneath.

- [ ] **Step 1: Write the concurrency test**

Create `tests/test_concorrencia_http.py`:

```python
import asyncio

import httpx
import pytest

from app.main import app


@pytest.fixture
async def client():
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
```

- [ ] **Step 2: Run test to verify it fails initially, then passes**

Run: `uv run pytest tests/test_concorrencia_http.py -v`
Expected: `1 passed`. (If it ever fails with `total == 2`, that is a real Guarantee-5 regression — stop and investigate the `ix_reservas_area_data_ativa` index before continuing.)

- [ ] **Step 3: Write the restart-persistence test**

Create `tests/test_restart_persistencia.py`:

```python
import uuid

import pytest
from google.genai import types

from app import db
from app.adk_app import ADK_USER_ID, APP_NAME, make_runner, make_session_service
from app.adk_runtime import run_com_retry
from app.agents.root import build_root_agent


@pytest.mark.asyncio
async def test_sessao_sobrevive_a_novo_processo_simulado(session_factory):
    db.configurar_session_factory(session_factory)

    session_service_1 = make_session_service()
    session_id = str(uuid.uuid4())
    await session_service_1.create_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id, state={"apartamento": "101"})
    runner_1 = make_runner(build_root_agent(), session_service_1)

    msg1 = types.Content(role="user", parts=[types.Part(text="Reserve a quadra para 2030-04-06")])
    await run_com_retry(runner_1, user_id=ADK_USER_ID, session_id=session_id, new_message=msg1)

    sessao_antes = await session_service_1.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    quantidade_eventos_antes = len(sessao_antes.events)

    # "Reinício": instâncias novas de tudo, mesmo Postgres por baixo.
    session_service_2 = make_session_service()
    runner_2 = make_runner(build_root_agent(), session_service_2)

    sessao_depois_reinicio = await session_service_2.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    assert len(sessao_depois_reinicio.events) == quantidade_eventos_antes

    msg2 = types.Content(role="user", parts=[types.Part(text="Quais são minhas reservas agora?")])
    await run_com_retry(runner_2, user_id=ADK_USER_ID, session_id=session_id, new_message=msg2)

    sessao_final = await session_service_2.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    assert len(sessao_final.events) > quantidade_eventos_antes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_restart_persistencia.py -v`
Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_concorrencia_http.py tests/test_restart_persistencia.py
git commit -m "test: add HTTP-level concurrency and restart-persistence regression tests"
```

---

### Task 15: Restore script, final test run, and README

**Files:**
- Create: `scripts/restore.py`
- Test: `tests/test_restore.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `app.adk_app.make_session_service`, `app.config.get_settings`, `app.db.*`, `app.models.*`, `dados/reservas.json`, `dados/visitantes.json`.
- Produces: `restaurar()` — the single command used both for the first seed and for resetting to the initial state.

- [ ] **Step 1: Write the failing test**

Create `tests/test_restore.py`:

```python
from datetime import date

from scripts.restore import restaurar
from app.db import make_engine, make_session_factory
from app.config import get_settings
from app import repository


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_restore.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts'` (or `scripts.restore`).

- [ ] **Step 3: Write the implementation**

Create `scripts/__init__.py` (empty file).

Create `scripts/restore.py`:

```python
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.adk_app import make_session_service
from app.config import get_settings
from app.db import Base, make_engine, make_session_factory
from app.models import ReservaModel, VisitanteModel

DADOS_DIR = ROOT / "dados"


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

    # Recria o schema próprio do ADK (sessões/eventos) num banco limpo.
    make_session_service()

    print(f"Restaurado: {len(reservas)} reservas, {len(visitantes)} visitantes.")


if __name__ == "__main__":
    settings = get_settings()
    asyncio.run(restaurar(settings.database_url))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_restore.py -v`
Expected: `1 passed`. This test runs against the real `DATABASE_URL` from `.env` (the dev database, not `aurora_test`) — it is destructive by design, matching what the restore command does in production use.

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest -v`
Expected: all tests across Tasks 1-15 pass.

- [ ] **Step 6: Write the final README.md**

Replace `README.md` with:

```markdown
# Assistente do Residencial Aurora

Assistente virtual do condomínio Residencial Aurora: reserva de áreas comuns,
autorização de visitantes e dúvidas sobre o regulamento interno, por chat,
construído com Google ADK e exposto por uma API FastAPI.

## Arquitetura

Um agente principal (`root_agent`) atende o morador e transfere a conversa
(via `transfer_to_agent` nativo do ADK) para um de três especialistas:

- **`especialista_reservas`** (`app/agents/reservas.py`) — reserva e cancela
  áreas comuns. Acionado para qualquer pedido de reserva/cancelamento.
- **`especialista_visitantes`** (`app/agents/visitantes.py`) — autoriza
  visitantes. Acionado para liberar entrada de alguém no prédio.
- **`especialista_regulamento`** (`app/agents/regulamento.py`) — responde
  dúvidas sobre o regulamento interno, consultando um capítulo por vez.

Cada especialista corresponde a um domínio de dados e regra de negócio
distinto, o que mantém isolados os limites de confirmação (Garantia 1) e de
leitura do regulamento (Garantia 4). O `root_agent` nunca lê nem escreve
dados — só decide pra qual especialista transferir.

Armazenamento: um único Postgres, com dois papéis. `DatabaseSessionService`
do próprio ADK guarda sessões/eventos/state. As tabelas `reservas` e
`visitantes` (`app/models.py`) guardam o que muda em tempo de execução.
`dados/areas.json` e `dados/apartamentos.json` nunca mudam, então ficam só em
memória (`app/reference_data.py`), sem tabela.

Toda escrita em `reservas`/`visitantes` passa por `app/repository.py` —
nunca por um agente de IA intermediário. Ver seção Garantias abaixo pro
porquê.

## Garantias

**1. Cobrança/acesso só com confirmação** — `app/adk_runtime.py`
(`confirmacoes_pendentes`, `encontrar_confirmacao_pendente`,
`montar_resposta_confirmacao`) e `app/api/routes_sessoes.py`
(`responder_confirmacao`). `reservar_area` (taxa > 0) e `autorizar_visitante`
(sempre) são declaradas com `require_confirmation` em
`app/agents/reservas.py` e `app/agents/visitantes.py`. A tool nunca executa
sem uma resposta explícita na rota `POST /sessoes/{id}/confirmacoes`; nada
na conversa ("já confirmei por aqui") faz isso acontecer, porque a
confirmação é lida do histórico de eventos da sessão, não do texto da
mensagem. Reenviar um id já respondido, ou um id que nunca existiu, recebe
409 (mesma função `encontrar_confirmacao_pendente`).

**2. Cada sessão pertence a um apartamento** — `app/api/routes_sessoes.py`
(`criar_sessao`) grava `apartamento` no `state` da sessão ADK na criação.
Toda tool de escrita/leitura (`app/agents/reservas.py`,
`app/agents/visitantes.py`) lê `tool_context.state["apartamento"]` — nenhuma
delas tem um parâmetro `apartamento` na assinatura (ver
`tests/test_agents_reservas.py::test_reservar_area_nao_aceita_apartamento_como_parametro`
e equivalentes), então não existe valor que o modelo possa escolher no
lugar.

**3. Nada se perde no reinício** — `app/adk_app.py`
(`DatabaseSessionService` + `ResumabilityConfig(is_resumable=True)`), sobre o
mesmo Postgres das tabelas de negócio. Validado em
`tests/test_restart_persistencia.py` e `tests/test_adk_app.py`, que simulam
reinício criando novas instâncias de `Runner`/`DatabaseSessionService`
apontando pro mesmo banco.

**4. Regulamento é consultado, não carregado** — `app/regulamento.py` divide
`dados/regulamento.md` em capítulos na importação do módulo.
`app/agents/regulamento.py` expõe só os TÍTULOS na instrução do especialista
(nunca o conteúdo), e a tool `consultar_regulamento` devolve o conteúdo de
um único capítulo por vez. O `root_agent` (`app/agents/root.py`) não recebe
o regulamento em nenhuma instrução.

**5. Dois moradores, uma reserva** — índice `ix_reservas_area_data_ativa`
em `app/models.py`, um UNIQUE parcial em `(area, data) WHERE status =
'ativa'`. `app/repository.py::criar_reserva` tenta o `INSERT` e captura a
violação de unicidade do Postgres, devolvendo "recusada" em vez de deixar
propagar como erro. Validado sob concorrência real em
`tests/test_repository.py::test_duas_reservas_concorrentes_so_uma_vence` e
`tests/test_concorrencia_http.py`.

## Como rodar

Pré-requisitos: Python 3.12+, [`uv`](https://docs.astral.sh/uv/), Docker.

1. Copie `.env.example` para `.env` e preencha `GOOGLE_API_KEY` (chave do
   Google AI Studio) e `DATABASE_URL` (padrão já funciona com o
   `docker-compose.yml` deste repo).
2. `docker compose up -d` — sobe o Postgres.
3. `uv sync` — instala as dependências.
4. `uv run python scripts/restore.py` — cria as tabelas e carrega os dados
   iniciais de `dados/*.json`. Esse é também o comando de **restauração**:
   rodá-lo de novo a qualquer momento volta tudo ao estado inicial.
5. `uv run uvicorn app.main:app --port 8000` — sobe a API em
   `http://localhost:8000`.

Rodar os testes (requer Postgres rodando e `GOOGLE_API_KEY` válido, já que
parte dos testes chama a API do Gemini de verdade):

```bash
uv run pytest -v
```
```

- [ ] **Step 7: Commit**

```bash
git add scripts/__init__.py scripts/restore.py tests/test_restore.py README.md
git commit -m "feat: add restore script and write the final README"
```

---

## Self-Review Notes

- **Spec coverage:** every spec section has a task — reference data (Task 2), regulamento (Task 3, 10), storage split and repository (Task 4, 5), write layer / no orchestrator agent (Task 5, 8, 9 — enforced by signatures, not an agent), Guarantee 1 (Task 6, 7, 11, 12), Guarantee 2 (Task 8, 9, tested via signature inspection), Guarantee 3 (Task 7, 14), Guarantee 4 (Task 3, 10), Guarantee 5 (Task 4, 5, 14), API contract (Task 12, 13), Como rodar / restore (Task 15).
- **Type/name consistency checked across tasks:** `repository.criar_reserva/cancelar_reserva/listar_reservas/data_disponivel/autorizar_visitante/listar_visitantes` signatures match between Task 5's definition and every later caller (Tasks 8, 9, 15). `adk_runtime.ConfirmacaoPendente` fields (`id`, `acao`, `detalhes`, `invocation_id`) match every usage in Tasks 7, 11, 12. `ADK_USER_ID`/`APP_NAME` from Task 7 used identically in Tasks 11, 12, 14.
- **Field names for `detalhes`/`acao`** (`originalFunctionCall.name`/`.args`) were verified directly against the installed ADK 2.11.0 source (`flows/llm_flows/tools/_functions.py`) before writing Task 6, not guessed.
