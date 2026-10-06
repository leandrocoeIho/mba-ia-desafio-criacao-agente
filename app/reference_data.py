import json
from dataclasses import dataclass
from pathlib import Path

#CRIA CAMINHO DA PASTA DA PASTA RAIZ DO PROJETO
PROJECT_ROOT = Path(__file__).resolve().parent.parent
#PEGA A O CAMINHO RAIZ DO PROJETO E DEFINE DADOS_DIR COMO A PASTA "dados" DENTRO DO PROJETO
DADOS_DIR = PROJECT_ROOT / "dados"

@dataclass(frozen=True)
class Area:
    id: str
    nome: str
    taxa: float

def carregar_areas(dados_dir: Path = DADOS_DIR) -> dict[str, Area]:
    data = json.loads((dados_dir / "areas.json").read_text(encoding="utf-8"))
    return {item["id"]: Area(id=item["id"], nome=item["nome"], taxa=float(item["taxa"])) 
    for item in data
}

@dataclass(frozen=True)
class Apartamento:
    numero: str
    morador: str

def carregar_apartamentos(dados_dir: Path = DADOS_DIR) -> dict[str, Apartamento]:
    data = json.loads((dados_dir / "apartamentos.json").read_text(encoding="utf-8"))
    return {
        item["numero"]: Apartamento(numero=item["numero"], morador=item["morador"])
        for item in data
    }