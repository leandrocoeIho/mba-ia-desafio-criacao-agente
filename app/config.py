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