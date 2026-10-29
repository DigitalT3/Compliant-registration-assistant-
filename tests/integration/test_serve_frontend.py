"""Hosted deployment: the backend also serves the built front end, without shadowing the API."""
import pytest


@pytest.fixture()
def served(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>INDEX</html>")
    (dist / "assets" / "app-abc123.js").write_text("console.log('app')")
    (tmp_path / "secret.txt").write_text("do not serve")                 # outside the built folder
    monkeypatch.setenv("SERVE_FRONTEND", "1")
    monkeypatch.setenv("FRONTEND_DIST", str(dist))


def test_pages_assets_and_reloads_are_served(served, client):
    home = client.get("/")
    assert home.status_code == 200 and "INDEX" in home.text and home.headers["cache-control"] == "no-cache"
    assert "INDEX" in client.get("/dashboard/anything").text                    # a reload on any screen opens the app
    asset = client.get("/assets/app-abc123.js")
    assert asset.status_code == 200 and "immutable" in asset.headers["cache-control"]


def test_the_api_is_not_shadowed(served, client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/api/auth/options").status_code == 200
    missing = client.get("/api/does-not-exist")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"     # JSON, not the index page
    assert client.get("/api/analytics/summary").status_code == 401                            # still protected


def test_files_outside_the_built_folder_are_not_served(served, client):
    for path in ("../secret.txt", "..%2Fsecret.txt", "assets/../../secret.txt"):
        r = client.get("/" + path)
        assert "do not serve" not in r.text, path


def test_off_by_default(client):
    assert client.get("/").status_code == 404                                    # local development: the Vite server serves pages
