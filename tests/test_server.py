"""Servidor local: as rotas /api exigem o token; /api/ping continua aberto (a 2ª abertura do app precisa dele)."""
import http.client
import threading
from http.server import ThreadingHTTPServer

import pytest

import main


@pytest.fixture(scope="module")
def porta():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def req(porta, metodo, path, headers=None, body=None):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=5)
    c.request(metodo, path, body=body, headers=headers or {})
    r = c.getresponse()
    data = r.read()
    c.close()
    return r, data


def test_ping_sem_token(porta):
    r, _ = req(porta, "GET", "/api/ping")
    assert r.status == 200


@pytest.mark.parametrize("metodo,path", [
    ("GET", "/api/library"), ("GET", "/api/scan"), ("GET", "/api/steam-games"),
    ("GET", "/api/report/pick"), ("GET", "/"), ("PUT", "/api/library/x"),
    ("DELETE", "/api/library/x"), ("POST", "/api/quit"), ("POST", "/api/bye"),
])
def test_sem_token_e_proibido(porta, metodo, path):
    r, _ = req(porta, metodo, path, body=b"{}" if metodo in ("PUT", "POST") else None)
    assert r.status == 403
    assert not main.quit_now.is_set()


def test_token_errado(porta):
    r, _ = req(porta, "GET", "/api/library", {"X-ZM-Token": "errado"})
    assert r.status == 403
    r, _ = req(porta, "GET", "/api/library", {"Cookie": "zm_%d=errado" % porta})
    assert r.status == 403


def test_token_no_header(porta):
    r, _ = req(porta, "GET", "/api/library", {"X-ZM-Token": main.TOKEN})
    assert r.status == 200


def test_token_no_cookie_da_porta_certa(porta):
    r, _ = req(porta, "GET", "/api/library", {"Cookie": "zm_%d=%s" % (porta, main.TOKEN)})
    assert r.status == 200
    # cookie de outra porta não vale
    r, _ = req(porta, "GET", "/api/library", {"Cookie": "zm_1=%s" % main.TOKEN})
    assert r.status == 403


def test_abrir_com_t_na_url_poe_cookie_e_limpa_a_url(porta):
    r, _ = req(porta, "GET", "/?t=" + main.TOKEN)
    assert r.status == 302
    assert r.getheader("Location") == "/"
    cookie = r.getheader("Set-Cookie")
    assert cookie.startswith("zm_%d=%s" % (porta, main.TOKEN)) and "HttpOnly" in cookie and "SameSite=Strict" in cookie
    r, body = req(porta, "GET", "/", {"Cookie": "zm_%d=%s" % (porta, main.TOKEN)})
    assert r.status == 200 and b"<html" in body.lower()


def test_t_errado_na_url(porta):
    r, _ = req(porta, "GET", "/?t=errado")
    assert r.status == 403


def test_host_de_fora_continua_bloqueado(porta):
    r, _ = req(porta, "GET", "/api/library", {"Host": "exemplo.com", "X-ZM-Token": main.TOKEN})
    assert r.status == 403
    r, _ = req(porta, "GET", "/api/library", {"Origin": "http://exemplo.com", "X-ZM-Token": main.TOKEN})
    assert r.status == 403
