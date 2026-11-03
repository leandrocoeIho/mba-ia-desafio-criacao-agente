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
