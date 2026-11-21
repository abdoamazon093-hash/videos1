import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client

def test_unified_portal_home(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "المنصة الألمانية الشاملة" in response.text
    assert "tab-btn-vocab" in response.text
    assert "tab-btn-coach" in response.text

def test_vocab_view(client):
    response = client.get("/vocab/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Vocab Tutor" in response.text

def test_coach_static_assets(client):
    res_css = client.get("/static/styles.css")
    assert res_css.status_code == 200
    assert "text/css" in res_css.headers["content-type"]
    assert "diff-corrected-highlight" in res_css.text
    assert "btn-mic-stop" in res_css.text

    res_js = client.get("/static/app.js")
    assert res_js.status_code == 200
    assert "javascript" in res_js.headers["content-type"]
    assert "diff-corrected-highlight" in res_js.text
    assert "resetMicSilenceTimer" in res_js.text
    assert "btnMicStop" in res_js.text

def test_coach_view(client):
    response = client.get("/coach/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "German Coach" in response.text
    assert "btn-mic-stop" in response.text

def test_health_endpoints(client):
    res_simple = client.get("/health")
    assert res_simple.status_code == 200
    assert res_simple.json()["status"] == "ok"

    res_version = client.get("/api/version")
    assert res_version.status_code == 200
    data = res_version.json()
    assert data["vocab_tutor_version"] == "v16"
    assert data["german_coach_version"] == "v18"
