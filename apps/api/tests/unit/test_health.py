from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_returns_ok_status_with_no_dependencies_checked() -> None:
    # Arrange
    client = TestClient(app)

    # Act
    response = client.get("/health")

    # Assert
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
