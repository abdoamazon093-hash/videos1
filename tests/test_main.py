import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db

@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()

@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client

def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app_name"] == "Videos1"
    assert "database" in data
    assert data["database"]["engine"] == "SQLite"

def test_app_info(client):
    response = client.get("/api/info")
    assert response.status_code == 200
    data = response.json()
    assert data["app_name"] == "Videos1"
    assert data["version"] == "1.0.0"
    assert "environment" in data

def test_cache_lifecycle(client):
    test_key = "test_unit_key"
    test_val = "test_unit_value"

    # Set cache
    res_set = client.post("/api/cache", json={"key": test_key, "value": test_val})
    assert res_set.status_code == 201
    assert res_set.json()["key"] == test_key

    # Get cache
    res_get = client.get(f"/api/cache/{test_key}")
    assert res_get.status_code == 200
    assert res_get.json()["value"] == test_val

    # List cache
    res_list = client.get("/api/cache")
    assert res_list.status_code == 200
    keys = [item["key"] for item in res_list.json()]
    assert test_key in keys

    # Delete cache
    res_del = client.delete(f"/api/cache/{test_key}")
    assert res_del.status_code == 200
    assert res_del.json()["success"] is True

    # Confirm deleted
    res_get_del = client.get(f"/api/cache/{test_key}")
    assert res_get_del.status_code == 404

def test_static_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Videos1" in response.text
