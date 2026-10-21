def test_ui_is_served_from_the_same_app(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "/static/app.js" in page.text

    for asset in ("/static/app.js", "/static/styles.css"):
        assert client.get(asset).status_code == 200


def test_missing_static_file_is_404(client):
    assert client.get("/static/nope.js").status_code == 404
