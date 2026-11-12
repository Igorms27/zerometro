"""Mapa de jogos pelas conquistas (games.json): dado puro, que pode ser atualizado sem lançar um exe novo.

Ordem de uso: cópia que vai dentro do exe (app/games.json) -> cópia baixada da última vez (cache em
%APPDATA%\\Zerometro) -> o que a internet devolver agora. Tudo passa pela mesma validação; entrada
inválida é ignorada e o resto continua valendo. Só se baixa dado (JSON); nunca código.
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
URL = "https://raw.githubusercontent.com/Igorms27/zerometro/main/app/games.json"
MAX_BYTES = 256 * 1024
TIMEOUT = 10
# limites: um arquivo estragado não pode travar o app nem encher a tela
MAX_GAMES, MAX_CONTENTS, MAX_SEGS, MAX_ACH = 200, 8, 80, 12
_APPID = re.compile(r"^\d{1,10}$")
_ID = re.compile(r"^[a-z0-9_-]{1,32}$")
_KEY = re.compile(r"^[a-z0-9_-]{1,24}$")
_ACH = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")


def _str(v, n):
    return isinstance(v, str) and 0 < len(v.strip()) <= n and "\x00" not in v


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v <= 500


def _segment(d):
    if not isinstance(d, dict) or not _str(d.get("title"), 80) or not _num(d.get("h")):
        return None
    ach = d.get("ach")
    if not isinstance(ach, list) or not (0 < len(ach) <= MAX_ACH) or not all(isinstance(a, str) and _ACH.match(a) for a in ach):
        return None
    return dict(title=d["title"].strip(), h=d["h"], ach=list(ach))


def _game(g):
    """Jogo válido no formato interno de by_achievements.GAMES, ou None."""
    if not isinstance(g, dict) or not _ID.match(str(g.get("id", ""))) or not _str(g.get("name"), 80):
        return None
    platform = g.get("platform", "PC · Steam")
    if not _str(platform, 40):
        return None
    labels, raw_contents = g.get("labels"), g.get("contents")
    if not isinstance(labels, dict) or not isinstance(raw_contents, list) or not (0 < len(raw_contents) <= MAX_CONTENTS):
        return None
    contents, seen = [], set()
    for c in raw_contents:
        if not isinstance(c, dict) or not _KEY.match(str(c.get("key", ""))) or c["key"] in seen:
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
        ok = _game(g) if isinstance(appid, str) and _APPID.match(appid) else None
        if not ok or ok["id"] in ids:
            log.warning("games.json: entrada %r ignorada (inválida)", str(appid)[:20])
            continue
        ids.add(ok["id"])
        out[appid] = ok
    return out


def _parse(raw):
    try:
        return validate(json.loads(raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw))
    except (ValueError, UnicodeDecodeError, RecursionError):
        return {}


def _read(path):
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return {}
        with open(path, "rb") as f:
            return _parse(f.read())
    except OSError:
        return {}


def embedded_path():
    return os.path.join(getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")), "games.json")


def cache_path():
    return paths.data_path("games.json")


def load():
    """Embutido + cache local (o cache vence em caso de mesmo appid). Funciona sem internet."""
    games = _read(embedded_path())
    games.update(_read(cache_path()))
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
    games = _parse(raw)
    return games, (raw if games else None)


def refresh(url=URL, timeout=TIMEOUT):
    """Baixa o mapa e, se vier válido, guarda no cache e devolve o mapa completo (embutido + novo). Senão None."""
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
