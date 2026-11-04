import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # google_api_key nunca é lido diretamente do código (o cliente do Gemini
    # pega GOOGLE_API_KEY do ambiente sozinho) — mas fica aqui de propósito,
    # só pra get_settings() falhar rápido e claro na inicialização se a chave
    # não estiver configurada, em vez de falhar tarde e confuso lá no Gemini.
    google_api_key: str
    database_url: str


def get_settings() -> Settings:
    return Settings(
        google_api_key=os.environ["GOOGLE_API_KEY"],
        database_url=os.environ["DATABASE_URL"],
    )
