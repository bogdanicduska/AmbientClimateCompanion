from app import create_app


def test_health_status_ok():
    app = create_app()
    client = app.test_client()

    response = client.get("/health")
    assert response.status_code == 200

    data = response.get_json()
    assert data["status"] == "ok"


def test_health_returns_service_and_environment():
    app = create_app()
    client = app.test_client()

    data = client.get("/health").get_json()
    assert "service" in data
    assert "environment" in data
