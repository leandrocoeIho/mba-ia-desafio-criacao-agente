import json
from dataclasses import dataclass
from pathlib import Path

DADOS_DIR = Path(__file__).resolve().parent.parent / "dados"


@dataclass(frozen=True)
class Area:
    id: str
    nome: str
    taxa: float


def carregar_areas(dados_dir: Path = DADOS_DIR) -> dict[str, Area]:
    data = json.loads((dados_dir / "areas.json").read_text(encoding="utf-8"))
    return {item["id"]: Area(id=item["id"], nome=item["nome"], taxa=float(item["taxa"])) for item in data}
