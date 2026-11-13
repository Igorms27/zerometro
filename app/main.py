"""Zerômetro: app de PC que lê os saves e mostra quanto falta para zerar.

Roda um servidor só neste PC (127.0.0.1) e abre a tela numa janela do Edge em modo app.
Fecha sozinho quando a janela é fechada.
"""
import hmac
import http.cookies
import json
import logging
import logging.handlers
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import readers
import report
import updater
from readers import covers, paths, steam

APP_VERSION = "0.5.0"
UPDATE_REPO = "Igorms27/zerometro"  # "dono/repositorio" no GitHub onde as versões são publicadas
BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(BASE, "web")

log = logging.getLogger("zerometro")


def setup_log():
    h = logging.handlers.RotatingFileHandler(paths.data_path("zerometro.log"), maxBytes=300_000, backupCount=1, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)

# ---------- biblioteca (um JSON no AppData) ----------

_lib_lock = threading.Lock()


def lib_load():
    try:
        with open(paths.data_path("library.json"), encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def lib_write(d):
    tmp = paths.data_path("library.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, paths.data_path("library.json"))

# ---------- servidor ----------

last_ping = [time.time()]
GRACE = 15  # segundos sem sinal da janela até o app fechar (a janela dá sinal a cada 5 s)
quit_now = threading.Event()
GAME_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
TOKEN = secrets.token_urlsafe(24)  # novo a cada abertura; a janela recebe na URL e guarda num cookie
PUBLIC_API = ("/api/ping",)  # só diz a versão; a abertura de outra instância precisa disso antes de ter o token


def pick_folder():
    """Janela do Windows para escolher uma pasta."""
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk(); root.withdraw(); root.attributes("-topmost", True)
        d = filedialog.askdirectory(title="Escolha a pasta onde o jogo guarda os saves")
        root.destroy()
        return os.path.normpath(d) if d else None
    except Exception:
        log.exception("escolher pasta")
        return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 5_000_000:
            raise ValueError("grande demais")
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _local_only(self):
        # bloqueia páginas de outros sites tentando falar com este servidor
        host = (self.headers.get("Host") or "").split(":")[0]
        origin = self.headers.get("Origin")
        if host not in ("127.0.0.1", "localhost") or (origin and not re.match(r"^http://(127\.0\.0\.1|localhost):\d+$", origin)):
            self._send(403, {"ok": False, "erro": "proibido"})
            return False
        return True

    def _token_ok(self):
        cookie = "zm_%d" % self.server.server_address[1]  # cookies não separam portas do 127.0.0.1
        sent = self.headers.get("X-ZM-Token")
        if not sent:
            c = http.cookies.SimpleCookie()
            try:
                c.load(self.headers.get("Cookie") or "")
            except http.cookies.CookieError:
                return False
            sent = c[cookie].value if cookie in c else ""
        return hmac.compare_digest(sent.encode(), TOKEN.encode())

    def _guard(self, path=None):
        """Host/Origin locais + token (exceto /api/ping). Responde 403 e devolve False se não passar."""
        if not self._local_only():
            return False
        if (path or self.path.split("?")[0]) in PUBLIC_API or self._token_ok():
            return True
        self._drain()
        self._send(403, {"ok": False, "erro": "sem token"})
        return False

    def _drain(self):
        # lê (e joga fora) o corpo antes de recusar: fechar com corpo não lido faz o cliente receber um reset
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if 0 < n <= 5_000_000:
                self.rfile.read(n)
        except (ValueError, OSError):
            pass

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            # a janela abre com /?t=TOKEN: guarda o token num cookie e recarrega a URL limpa
            if not self._local_only():
                return
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            if q.get("t") and hmac.compare_digest(q["t"][0].encode(), TOKEN.encode()):
                self.send_response(302)
                self.send_header("Set-Cookie", "zm_%d=%s; Path=/; HttpOnly; SameSite=Strict" % (self.server.server_address[1], TOKEN))
                self.send_header("Location", "/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if not self._token_ok():
                return self._send(403, {"ok": False, "erro": "sem token"})
        elif not self._guard(p):
            return
        if p != "/api/ping" or self._token_ok():
            last_ping[0] = time.time()
        try:
            if p in ("/", "/index.html"):
                with open(os.path.join(WEB, "index.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if p == "/icon.svg":
                with open(os.path.join(WEB, "icon.svg"), "rb") as f:
                    return self._send(200, f.read(), "image/svg+xml")
            if p == "/api/ping":
                return self._send(200, {"ok": True, "version": APP_VERSION, "update": updater.state["ready"],
                                        "latest": updater.state["latest"], "updateStatus": updater.state["status"],
                                        "releases": "https://github.com/%s/releases/latest" % UPDATE_REPO})
            if p == "/api/library":
                with _lib_lock:
                    return self._send(200, {"ok": True, "games": lib_load()})
            if p == "/api/scan":
                found = readers.scan()
                return self._send(200, {"ok": True, "games": [g for g in found if "erro" not in g],
                                        "erros": [g for g in found if "erro" in g]})
            if p == "/api/steam-games":
                # todos os jogos da Steam instalados, cada um já com as pastas de save encontradas
                out = []
                for g in steam.installed_games():
                    try:
                        folders = report.find_folders(g["name"], g["appid"])
                    except Exception:
                        log.exception("procurar saves de %s", g["name"])
                        folders = []
                    out.append(dict(appid=g["appid"], name=g["name"], folders=folders))
                out.sort(key=lambda g: (not g["folders"], g["name"].lower()))
                return self._send(200, {"ok": True, "games": out})
            if p.startswith("/api/cover/"):
                data = covers.get(p.rsplit("/", 1)[1])
                if not data:
                    return self._send(404, {"ok": False})
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "max-age=86400")
                self.end_headers()
                self.wfile.write(data)
                return
            if p == "/api/report/pick":
                return self._send(200, {"ok": True, "folder": pick_folder()})
        except Exception as e:
            log.exception("GET %s", p)
            return self._send(500, {"ok": False, "erro": str(e)})
        self._send(404, {"ok": False})

    def do_PUT(self):
        if not self._guard():
            return
        m = re.match(r"^/api/library/([^/]+)$", self.path)
        if not m or not GAME_ID.match(m.group(1)):
            return self._send(404, {"ok": False})
        try:
            body = self._body()
            with _lib_lock:
                d = lib_load(); d[m.group(1)] = body; lib_write(d)
            self._send(200, {"ok": True})
        except Exception as e:
            log.exception("PUT")
            self._send(500, {"ok": False, "erro": str(e)})

    def do_DELETE(self):
        if not self._guard():
            return
        m = re.match(r"^/api/library/([^/]+)$", self.path)
        if not m:
            return self._send(404, {"ok": False})
        with _lib_lock:
            d = lib_load(); d.pop(m.group(1), None); lib_write(d)
        self._send(200, {"ok": True})

    def do_POST(self):
        if not self._guard():
            return
        try:
            body = self._body()
            if self.path == "/api/bye":
                # a janela foi fechada (ou recarregada): fecha em ~4 s, a não ser que ela volte a dar sinal
                last_ping[0] = time.time() - GRACE + 4
                log.info("janela avisou que fechou")
                return self._send(200, {"ok": True})
            if self.path == "/api/quit":
                # outra versão do app está abrindo e pediu a vez
                quit_now.set()
                return self._send(200, {"ok": True})
            if self.path == "/api/report/find":
                return self._send(200, {"ok": True, "folders": report.find_folders(str(body.get("name") or ""), body.get("appid"))})
            if self.path == "/api/report/build":
                folders = [f for f in body.get("folders") or [] if isinstance(f, str) and os.path.isdir(f)]
                if not folders and not body.get("appid"):
                    return self._send(400, {"ok": False, "erro": "escolha pelo menos uma pasta"})
                r = report.build(str(body.get("name") or "jogo"), body.get("appid"), folders, APP_VERSION)
                log.info("relatório criado: %s", r["path"])
                return self._send(200, dict(r, ok=True))
            if self.path == "/api/report/show":
                p = str(body.get("path") or "")
                if os.path.isfile(p) and os.path.basename(p).startswith("Zerometro-relatorio-"):
                    subprocess.Popen(["explorer", "/select,", p])
                return self._send(200, {"ok": True})
        except Exception as e:
            log.exception("POST %s", self.path)
            return self._send(500, {"ok": False, "erro": str(e)})
        self._send(404, {"ok": False})

# ---------- janela ----------

def find_edge():
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if base:
            p = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.exists(p):
                return p
    return shutil.which("msedge")


def open_window(url):
    edge = find_edge()
    if edge:
        prof = paths.data_path("janela")
        subprocess.Popen([edge, "--app=" + url, "--user-data-dir=" + prof, "--no-first-run",
                          "--start-maximized", "--disable-features=Translate",
                          # janela minimizada continua dando sinal (senão o Edge atrasa os timers e o app fecharia)
                          "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
                          "--disable-backgrounding-occluded-windows"])
    else:
        webbrowser.open(url)


def _saved_token():
    try:
        with open(paths.data_path("token.txt"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _url_token():
    return "?t=" + urllib.parse.quote(_saved_token())


def already_running():
    """Se o app já está aberto, só abre outra janela dele."""
    try:
        port = int(open(paths.data_path("porta.txt")).read().strip())
        base = "http://127.0.0.1:%d" % port
        with urllib.request.urlopen(base + "/api/ping", timeout=1) as r:
            old = json.load(r).get("version")
    except (OSError, ValueError):
        return False
    if old != APP_VERSION:
        # o que está aberto é outra versão (ex.: antes de atualizar): pede para ela fechar e abre esta
        try:
            urllib.request.urlopen(urllib.request.Request(base + "/api/quit", data=b"{}", method="POST",
                                                          headers={"X-ZM-Token": _saved_token()}), timeout=1).close()
        except OSError:
            pass  # versões antigas não têm /api/quit; fecham sozinhas quando a janela delas fechar
        log.info("versão %s estava aberta; abrindo a %s", old, APP_VERSION)
        return False
    open_window(base + "/" + _url_token())
    return True


def main():
    setup_log()
    if already_running():
        return
    if updater.startup(APP_VERSION):  # a versão nova caiu duas vezes: voltou para a antiga e abriu ela
        return
    t_start = time.time()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    with open(paths.data_path("porta.txt"), "w") as f:
        f.write(str(port))
    with open(paths.data_path("token.txt"), "w", encoding="utf-8") as f:  # só para uma 2ª abertura do app achar esta
        f.write(TOKEN)
    log.info("Zerômetro %s na porta %d", APP_VERSION, port)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    threading.Thread(target=updater.loop, args=(APP_VERSION, UPDATE_REPO), daemon=True).start()
    threading.Thread(target=readers.by_achievements.refresh, daemon=True).start()  # mapa de jogos (games.json); sem rede, usa o que já tem
    if "--sem-janela" not in sys.argv:
        open_window("http://127.0.0.1:%d/?t=%s" % (port, TOKEN))
    # a tela manda sinal a cada 5 s; sem sinal por GRACE s (janela fechada), o app fecha
    last_ping[0] = time.time() + 30
    while time.time() - last_ping[0] < GRACE and not quit_now.is_set():
        time.sleep(1)
    log.info("janela fechada, saindo")
    srv.shutdown()
    updater.finish(time.time() - t_start)


if __name__ == "__main__":
    main()
