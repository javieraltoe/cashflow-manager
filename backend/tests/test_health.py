from app.db import session as db_session


def test_health_ok_cuando_la_db_responde(client, monkeypatch):
    monkeypatch.setattr(db_session, "check_database", lambda: True)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert "version" in body


def test_health_503_cuando_la_db_no_responde(client, monkeypatch):
    monkeypatch.setattr(db_session, "check_database", lambda: False)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 503
    assert resp.json()["database"] == "unavailable"


def test_health_no_expone_datos_sensibles(client, monkeypatch):
    monkeypatch.setattr(db_session, "check_database", lambda: True)
    texto = client.get("/api/v1/health").text.lower()
    for palabra in ("password", "postgres", "secret", "host"):
        assert palabra not in texto
