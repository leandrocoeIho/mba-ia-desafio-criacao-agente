import re
from dataclasses import dataclass
from pathlib import Path

from app.reference_data import DADOS_DIR

REGULAMENTO_PATH = DADOS_DIR / "regulamento.md"


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
