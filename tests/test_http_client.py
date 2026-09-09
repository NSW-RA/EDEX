import functools
import http.server
import socketserver
import threading

import pytest

from core.http_client import HttpClient, HttpError, _looks_like_login


def test_looks_like_login_detects_microsoft_and_password_page():
    assert _looks_like_login("https://login.microsoftonline.com/x", "") is True
    assert _looks_like_login("https://portal/login", "") is True
    assert _looks_like_login("https://portal/app", '<input type="password">') is True
    assert _looks_like_login("https://manage.smartygrants.com.au/application/1/files", "<h1>Files</h1>") is False


def test_cookie_header_prefix_is_stripped():
    c = HttpClient("cookie: SESSION=abc; x=1")
    assert c._session.headers["Cookie"] == "SESSION=abc; x=1"
    c2 = HttpClient("SESSION=abc")
    assert c2._session.headers["Cookie"] == "SESSION=abc"


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        # Simulate auth: only serve real content if the session cookie is present.
        cookie = self.headers.get("Cookie", "")
        if "SESSION=good" not in cookie:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b'<html><body><input type="password"></body></html>')
            return
        if self.path.endswith("/page"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b'<html><body><a href="/f/1">doc.pdf</a></body></html>')
            return
        if self.path == "/f/1":
            data = b"%PDF-1.4 body"
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="doc.pdf"')
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_response(404)
        self.end_headers()


@pytest.fixture()
def server():
    httpd = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


def test_scrape_and_fetch_with_valid_cookie(server):
    client = HttpClient("SESSION=good")
    res = client.scrape(f"{server}/page")
    assert [t for _, t in res["links"]] == ["doc.pdf"]
    url = res["links"][0][0]
    resp = client.fetch(url)
    assert resp["status"] == 200
    assert resp["body"].startswith(b"%PDF")
    filename = resp["content_disposition"]
    assert filename and "doc.pdf" in filename


def test_bad_cookie_raises_login_error(server):
    client = HttpClient("SESSION=bad")
    with pytest.raises(HttpError):
        client.scrape(f"{server}/page")
