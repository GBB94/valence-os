from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import SPAStaticFiles


def test_spa_static_files_falls_back_only_for_navigation_paths(tmp_path):
    (tmp_path / "index.html").write_text("<main>Valence OS</main>", encoding="utf-8")
    application = FastAPI()
    application.mount("/", SPAStaticFiles(directory=tmp_path, html=True), name="frontend")
    client = TestClient(application)

    deep_link = client.get("/accounts/mock-account/commercial?program=mock-program")
    assert deep_link.status_code == 200
    assert "Valence OS" in deep_link.text

    assert client.get("/missing.js").status_code == 404
    assert client.get("/api/not-a-real-endpoint").status_code == 404
