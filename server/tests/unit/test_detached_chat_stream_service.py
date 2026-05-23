from app.services import detached_chat_stream_service as svc


def _clear_worker_env(monkeypatch):
    for key in (
        "WEB_CONCURRENCY",
        "UVICORN_WORKERS",
        "GUNICORN_WORKERS",
        "GUNICORN_CMD_ARGS",
    ):
        monkeypatch.delenv(key, raising=False)


def test_configured_worker_count_defaults_to_single(monkeypatch):
    _clear_worker_env(monkeypatch)
    monkeypatch.setattr(svc.sys, "argv", ["uvicorn", "app.main:app"])

    assert svc._configured_worker_count() == 1


def test_configured_worker_count_detects_worker_env(monkeypatch):
    _clear_worker_env(monkeypatch)
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    monkeypatch.setattr(svc.sys, "argv", ["uvicorn", "app.main:app"])

    assert svc._configured_worker_count() == 2


def test_configured_worker_count_detects_worker_args(monkeypatch):
    _clear_worker_env(monkeypatch)
    monkeypatch.setattr(
        svc.sys,
        "argv",
        ["uvicorn", "app.main:app", "--workers", "3"],
    )

    assert svc._configured_worker_count() == 3
