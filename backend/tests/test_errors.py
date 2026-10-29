def test_404_con_formato_de_error_uniforme(client):
    resp = client.get("/api/v1/no-existe")
    assert resp.status_code == 404
    assert resp.json() == {"error": {"code": "not_found", "message": "Not Found", "field": None}}


def test_405_con_formato_de_error_uniforme(client):
    resp = client.post("/api/v1/health")
    assert resp.status_code == 405
    assert resp.json()["error"]["code"] == "method_not_allowed"
