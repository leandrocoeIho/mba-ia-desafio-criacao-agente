from fastapi import Request


def get_runner(request: Request):
    return request.app.state.runner


def get_session_service(request: Request):
    return request.app.state.session_service


def get_db_session_factory(request: Request):
    return request.app.state.session_factory
