"""Every response carries a support ID; an unexpected failure exposes nothing else."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import request_context


def _app() -> FastAPI:
    app = FastAPI()
    request_context.install(app)

    @app.get("/ok")
    def ok():
        return {"ok": True}

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret connection string postgresql://user:pass@db")

    return app


def test_every_response_carries_a_request_id():
    response = TestClient(_app()).get("/ok")
    assert response.status_code == 200
    assert len(response.headers[request_context.HEADER]) >= 8


def test_a_sane_incoming_id_is_kept_and_a_hostile_one_replaced():
    client = TestClient(_app())
    assert client.get("/ok", headers={"X-Request-ID": "trace-12345678"}).headers["X-Request-ID"] == "trace-12345678"
    replaced = client.get("/ok", headers={"X-Request-ID": "<script>alert(1)</script>"}).headers["X-Request-ID"]
    assert "<" not in replaced


def test_an_unexpected_failure_answers_with_the_support_id_and_no_internals(caplog):
    client = TestClient(_app(), raise_server_exceptions=False)
    with caplog.at_level("ERROR", logger="app.request"):
        response = client.get("/boom")
    assert response.status_code == 500
    body = response.json()["detail"]
    support_id = response.headers["X-Request-ID"]
    assert body["supportId"] == support_id
    assert "postgresql" not in response.text and "RuntimeError" not in response.text
    # …while the log line it points to has what an engineer needs.
    assert any(support_id in record.getMessage() and "/boom" in record.getMessage() for record in caplog.records)
