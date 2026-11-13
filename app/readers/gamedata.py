"""Mapa de jogos pelas conquistas (games.json): dado puro, que pode ser atualizado sem lançar um exe novo.

Ordem de uso: cópia que vai dentro do exe (app/games.json) -> cópia baixada da última vez (cache em
%APPDATA%\\Zerometro) -> o que a internet devolver agora. Tudo passa pela mesma validação; entrada
inválida é ignorada e o resto continua valendo. O campo "rev" diz qual cópia é mais nova: uma cópia
baixada com rev menor que a do exe é ignorada (o exe novo trouxe correção). Só se baixa dado (JSON); nunca código.
"""
import json
import logging
import os
import re
import sys
import urllib.request

from . import paths

log = logging.getLogger("zerometro")

SCHEMA = 1  # versão do formato; arquivo com "schema" maior que isso é ignorado (app antigo não entende)
URL = "https://raw.githubusercontent.com/Igorms27/zerometro/mapa/app/games.json"  # etiqueta "mapa": só o publicar-mapa.ps1 move
MAX_BYTES = 256 * 1024
TIMEOUT = 10
# limites: um arquivo estragado não pode travar o app nem encher a tela
MAX_GAMES, MAX_CONTENTS, MAX_SEGS, MAX_ACH = 200, 8, 80, 12
_APPID = re.compile(r"[0-9]{1,10}")
_ID = re.compile(r"[a-z0-9_-]{1,32}")
_KEY = re.compile(r"[a-z0-9_-]{1,24}")
_ACH = re.compile(r"[A-Za-z0-9_.:-]{1,80}")  # sempre com fullmatch ("$" aceitaria um \n no fim)


def _str(v, n):
    return isinstance(v, str) and 0 < len(v.strip()) <= n and "\x00" not in v


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v <= 500


def _segment(d):
    if not isinstance(d, dict) or not _str(d.get("title"), 80) or not _num(d.get("h")):
        return None
    ach = d.get("ach")
    if not isinstance(ach, list) or not (0 < len(ach) <= MAX_ACH) or not all(isinstance(a, str) and _ACH.fullmatch(a) for a in ach):
        return None
    return dict(title=d["title"].strip(), h=d["h"], ach=list(ach))


def _game(g):
    """Jogo válido no formato interno de by_achievements.GAMES, ou None."""
    if not isinstance(g, dict) or not isinstance(g.get("id"), str) or not _ID.fullmatch(g["id"]) or not _str(g.get("name"), 80):
        return None
    platform = g.get("platform", "PC · Steam")
    if not _str(platform, 40):
        return None
    labels, raw_contents = g.get("labels"), g.get("contents")
    if not isinstance(labels, dict) or not isinstance(raw_contents, list) or not (0 < len(raw_contents) <= MAX_CONTENTS):
        return None
    contents, seen = [], set()
    for c in raw_contents:
        if not isinstance(c, dict) or not isinstance(c.get("key"), str) or not _KEY.fullmatch(c["key"]) or c["key"] in seen:
            return None
        segs = c.get("segs")
        if not isinstance(segs, list) or not (0 < len(segs) <= MAX_SEGS):
            return None
        good = [_segment(s) for s in segs]
        if None in good:  # parte estragada: o jogo todo fica de fora (a ordem das partes importa)
            return None
        seen.add(c["key"])
        contents.append((c["key"], good))
    if set(labels) != seen or not all(_str(v, 60) for v in labels.values()):
        return None
    return dict(id=g["id"], name=g["name"].strip(), platform=platform.strip(), labels=dict(labels), contents=contents)


def validate(data):
    """{appid: jogo} só com as entradas válidas. Documento inteiro inválido -> {}."""
    if not isinstance(data, dict) or not isinstance(data.get("schema"), int) or isinstance(data["schema"], bool) \
            or not (1 <= data["schema"] <= SCHEMA):
        return {}
    games = data.get("games")
    if not isinstance(games, dict):
        return {}
    out, ids = {}, set()
    for appid, g in list(games.items())[:MAX_GAMES]:
        ok = _game(g) if isinstance(appid, str) and _APPID.fullmatch(appid) else None
        if not ok or ok["id"] in ids:
            log.warning("games.json: entrada %r ignorada (inválida)", str(appid)[:20])
            continue
        ids.add(ok["id"])
        out[appid] = ok
    return out


def _rev(data):
    r = data.get("rev", 0) if isinstance(data, dict) else 0
    return r if isinstance(r, int) and not isinstance(r, bool) and r >= 0 else 0


def _parse(raw, with_rev=False):
    try:
        data = json.loads(raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return ({}, 0) if with_rev else {}
    games = validate(data)
    return (games, _rev(data)) if with_rev else games


def _read(path, with_rev=False):
    try:
        if os.path.getsize(path) > MAX_BYTES:
            raise OSError("grande demais")
        with open(path, "rb") as f:
            return _parse(f.read(), with_rev)
    except OSError:
        return ({}, 0) if with_rev else {}


def embedded_path():
    return os.path.join(getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")), "games.json")


def cache_path():
    return paths.data_path("games.json")


def load():
    """Embutido + cache local (o cache vence em caso de mesmo appid). Funciona sem internet."""
    games, rev = _read(embedded_path(), True)
    cached, cached_rev = _read(cache_path(), True)
    if cached_rev >= rev:  # cópia baixada mais velha que a do exe: o exe novo trouxe correção
        games.update(cached)
    return games


def fetch(url=URL, timeout=TIMEOUT):
    """Baixa e valida. Devolve (jogos, bytes) ou ({}, None) em qualquer falha."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Zerometro"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(MAX_BYTES + 1)
    except Exception as e:  # sem rede, timeout, 404...
        log.info("mapa de jogos não atualizado: %s", e)
        return {}, None
    if len(raw) > MAX_BYTES:
        log.warning("games.json remoto grande demais; ignorado")
        return {}, None
    games, rev = _parse(raw, True)
    if games and rev < _read(embedded_path(), True)[1]:
        log.info("games.json remoto mais velho que o do exe; ignorado")
        return {}, None
    return games, (raw if games else None)


def download_enabled():
    """A pessoa desliga o download com {"baixar_mapa": false} em %APPDATA%\\Zerometro\\settings.json."""
    s = paths.settings()
    return not (isinstance(s, dict) and s.get("baixar_mapa") is False)


def refresh(url=URL, timeout=TIMEOUT):
    """Baixa o mapa e, se vier válido, guarda no cache e devolve o mapa completo (embutido + novo). Senão None."""
    if not download_enabled():
        return None
    games, raw = fetch(url, timeout)
    if not raw:
        return None
    try:
        tmp = cache_path() + ".tmp"
        with open(tmp, "wb") as f:
            f.write(raw)
        os.replace(tmp, cache_path())
    except OSError as e:
        log.warning("não consegui guardar o mapa de jogos: %s", e)
    merged = _read(embedded_path())
    merged.update(games)
    return merged
