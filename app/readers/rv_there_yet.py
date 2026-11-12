"""RV There Yet? (PC, Steam).

Cada sessão tem um "<nome>.meta.sav" (Unreal) com o mapa, o último checkpoint e o tempo de jogo.
Como o jogo é cooperativo, quem joga na sessão de um amigo não tem o save: aí valem as conquistas
da Steam, que têm uma para cada checkpoint de cada mapa. Usamos o mais avançado dos dois.
"""
import glob
import os
import re
import struct

from . import base as common
from . import steam

ID, NAME, PLATFORM = "rvty", "RV There Yet?", "PC · Steam"
STEAM_APPID = "3949040"

# mapa: (chave, nome, nº de checkpoints, horas médias estimadas, prefixo das conquistas, conquista dos créditos)
MAPS = [
    ("base", "Mabutts Valley", 16, 5.0, "ACH_REACH_CHECKPOINT_", "ACH_REACH_CREDITS"),
    ("snow", "Mt. Yurbuttsk", 13, 4.0, "ACH_REACH_CHECKPOINT_SNOW_", "ACH_REACH_CREDITS_SNOW"),
    ("bay", "St. Büttin Bay", 22, 5.0, "ACH_REACH_CHECKPOINT_LEVEL3_", "ACH_REACH_CREDITS_LEVEL3"),
]
LABELS = {k: name for k, name, *_ in MAPS}
LEVEL_KEY = {"ridemap": "base", "snowlevel": "snow"}  # o terceiro mapa cai em "bay"


def save_dirs():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    root = os.path.join(base, "Ride", "Saved", "SaveGames")
    return [root] + [d for d in glob.glob(os.path.join(root, "*")) if os.path.isdir(d)]


def read_meta(path):
    with open(path, "rb") as f:
        b = f.read()
    if b[:4] != b"GVAS":
        raise ValueError("not_rv_save")
    m = re.search(rb"Checkpoint\x00\x0c\x00\x00\x00IntProperty\x00.{9}(.{4})", b, re.S)
    cp = struct.unpack("<i", m.group(1))[0] if m else 0
    m = re.search(rb"Playtime\x00.{0,120}?/Script/CoreUObject\x00.{9}(.{8})", b, re.S)
    secs = struct.unpack("<q", m.group(1))[0] / 1e7 if m else 0
    m = re.search(rb"/Game/Ride/Maps/([A-Za-z0-9_]+)", b)
    level = m.group(1).decode() if m else ""
    key = LEVEL_KEY.get(level.lower(), "bay" if level else None)
    return dict(key=key, cp=cp, secs=max(0.0, secs), mtime=os.path.getmtime(path))


def analyze(metas, ach):
    best = {}
    for m in metas:
        if m["key"]:
            best[m["key"]] = max(best.get(m["key"], 0), m["cp"])
    contents, last = [], {}
    for key, name, n, hours, prefix, credits in MAPS:
        cp = best.get(key, 0)
        for a, v in ach.items():
            mm = re.match(re.escape(prefix) + r"(\d+)$", a)
            if mm and v["unlocked"]:
                cp = max(cp, int(mm.group(1)))
                last[key] = max(last.get(key, 0), v["time"])
        fin = bool(ach.get(credits, {}).get("unlocked"))
        if fin:
            last[key] = max(last.get(key, 0), ach[credits]["time"])
        for m in metas:
            if m["key"] == key:
                last[key] = max(last.get(key, 0), m["mtime"])
        h = hours / (n + 1)
        segs = [dict(title="Checkpoint %d" % (i + 1), h=h, frac=1.0 if (fin or cp >= i + 1) else 0.0) for i in range(n)]
        segs.append(dict(title="Créditos", h=h, frac=1.0 if fin else 0.0))
        started = fin or cp > 0 or key in best
        if not fin and started:  # trecho atual: a caminho do próximo checkpoint
            nxt = next((s for s in segs if s["frac"] == 0), None)
            if nxt:
                nxt["frac"] = 0.3
        contents.append(common.build_content(key, segs, finished=fin, started=started, ndigits=2))
    playing = [c for c in contents if c["status"] == "andamento"]
    cur = max(playing, key=lambda c: last.get(c["key"], 0)) if playing else max(contents, key=lambda c: last.get(c["key"], 0))
    return dict(current=cur["key"], contents=contents)


def latest(cache):
    files = common.find_files(save_dirs(), "*.meta.sav")
    schema, users = steam.stats_files(STEAM_APPID)
    if not files and not schema:
        return None
    stamp = tuple(sorted((p, os.path.getmtime(p)) for p in files)) + tuple(os.path.getmtime(u) for u in users)

    def compute():
        metas = []
        for p in files:
            try:
                metas.append(read_meta(p))
            except (OSError, ValueError):
                pass
        ach = steam.achievements(STEAM_APPID) or {}
        has_ach = any(v["unlocked"] for v in ach.values())
        if files and not metas and not has_ach:
            raise ValueError("nenhum save legível")  # há saves, mas nenhum foi lido: aparece como aviso
        if not metas and not has_ach:
            return None
        res = analyze(metas, ach)
        newest = max(metas, key=lambda m: m["mtime"]) if metas else None
        res.update(playH=round(sum(m["secs"] for m in metas) / 3600, 1),
                   saveFile=LABELS.get(res["current"], ""),
                   saveDate=int((newest["mtime"] if newest else max([os.path.getmtime(u) for u in users] + [0])) * 1000),
                   cover=None, source="save" if metas else "steam")
        return res
    return common.cached(cache, (ID, stamp), compute)
