from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_app_boots() -> None:
    assert app.title == "fowoco-ai"
    # 엔드포인트는 아직 없음. OpenAPI 문서만 확인.
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "openapi" in response.json()
