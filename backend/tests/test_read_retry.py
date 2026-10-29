"""
A read whose database connection drops once is retried on a fresh connection and succeeds; writes,
GETs that start work and ordinary errors are never retried.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.read_retry import ReadRetryMiddleware


def _app():
    calls = {"n": 0}
    app = FastAPI()
    app.add_middleware(ReadRetryMiddleware)

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise OperationalError("SELECT 1", {}, Exception("connection was closed in the middle of operation"))
        return {"ok": True, "calls": calls["n"]}

    @app.get("/api/v1/things")
    def read_things():
        return flaky()

    @app.post("/api/v1/things")
    def write_things():
        return flaky()

    @app.get("/api/v1/documents/abc/extract")
    def start_extraction():
        return flaky()

    @app.get("/api/v1/broken")
    def broken():
        calls["n"] += 1
        raise ValueError("a real bug")

    return app, calls


def test_a_read_is_retried_once_after_a_dropped_connection():
    app, calls = _app()
    res = TestClient(app).get("/api/v1/things")
    assert res.status_code == 200 and res.json() == {"ok": True, "calls": 2}


def test_writes_and_work_starting_reads_are_not_retried():
    app, calls = _app()
    assert TestClient(app, raise_server_exceptions=False).post("/api/v1/things").status_code == 500
    assert calls["n"] == 1
    app, calls = _app()
    assert TestClient(app, raise_server_exceptions=False).get("/api/v1/documents/abc/extract").status_code == 500
    assert calls["n"] == 1


def test_the_retry_runs_before_errors_become_a_503_response():
    from app.main import app
    names = [m.cls.__name__ for m in app.user_middleware]  # outermost first
    assert names.index("ReadRetryMiddleware") > names.index("BaseHTTPMiddleware")


def test_ordinary_errors_are_not_retried():
    app, calls = _app()
    assert TestClient(app, raise_server_exceptions=False).get("/api/v1/broken").status_code == 500
    assert calls["n"] == 1
