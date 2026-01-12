from fastapi.testclient import TestClient
import yaml
import pytest
from multirig.app import create_app
from multirig.config import AppConfig

@pytest.fixture
def client(tmp_path):
    # Set test mode via env var is one way, but TestClient runs in process.
    # We can pass a dummy config path.
    config_file = tmp_path / "test_multirig.yaml"
    app = create_app(config_file)
    with TestClient(app) as c:
        yield c

def test_export_import(client):
    # 1. Export default config
    resp = client.get("/api/config/export")
    assert resp.status_code == 200
    assert "text/yaml" in resp.headers["content-type"]
    
    yaml_content = resp.text
    data = yaml.safe_load(yaml_content)
    assert "poll_interval_ms" in data
    assert data["poll_interval_ms"] == 1000

    # 2. Modify YAML
    data["poll_interval_ms"] = 555
    new_yaml = yaml.dump(data)

    # 3. Import new config
    resp = client.post("/api/config/import", content=new_yaml)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # 4. Verify change via API
    resp = client.get("/api/config")
    assert resp.json()["poll_interval_ms"] == 555
