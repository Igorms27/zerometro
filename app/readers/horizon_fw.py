"""Horizon Forbidden West (PC, Steam).

O corpo do save é binário (motor Decima, sem nomes de missão), então juntamos as duas fontes:
- cabeçalho do save: missão ativa, nível e tempo de jogo ("Singularidade - Nível 31 - 28:15:45");
- conquistas da Steam: cada missão principal grande tem uma conquista.
"""
import glob
import os
import re

from . import base as common
from . import paths, steam

ID, NAME, PLATFORM = "hfw", "Horizon Forbidden West", "PC · Steam"
STEAM_APPID = "2420110"
LABELS = {"base": "História principal", "bs": "Burning Shores"}

# gate=True: essa parte só acontece depois de todas as anteriores (ÉTER/POSEIDON/DEMÉTER/Beta são em qualquer ordem)
CONTENT = [
    ("base", [
        dict(title="O Vão", h=3, ach=["Trophy004"]),
        dict(title="Reabrir o Vão", h=2.5, ach=["Trophy005"], gate=True),
        dict(title="A Embaixada", h=2, ach=["Trophy006"], gate=True),
        dict(title="A Base e GAIA", h=2.5, ach=["Trophy007"], gate=True),
        dict(title="Recuperar ÉTER", h=3, ach=["Trophy008"]),
        dict(title="Recuperar POSEIDON", h=3, ach=["Trophy009"]),
        dict(title="Recuperar DEMÉTER", h=3, ach=["Trophy010"]),
        dict(title="Recuperar Beta", h=2, ach=["Trophy011"]),
        dict(title="Tebas e o destino de Faro", h=3, ach=["Trophy012"], gate=True),
        dict(title="As Asas dos Dez", h=3, ach=["Trophy013"], gate=True),
        dict(title="Singularidade", h=3, ach=["Trophy014"], gate=True, quests=["singularidade", "singularity"]),
    ]),
    ("bs", [
        dict(title="A Ascensão", h=3, ach=["Trophy063"]),
        dict(title="Confrontar Londra", h=3, ach=["Trophy064"], gate=True),
        dict(title="Derrotar o Hórus", h=2.5, ach=["Trophy066"], gate=True),
    ]),
]

HEADER_RE = re.compile(r"^(?P<quest>.*?)(?: - N\w+vel (?P<lvl>\d+))? - (?P<h>\d+):(?P<m>\d\d):(?P<s>\d\d)$")


def save_dirs():
    out = []
    for docs in paths.documents_dirs():
        base = os.path.join(docs, "Horizon Forbidden West Complete Edition")
        out += [d for d in glob.glob(os.path.join(base, "*")) if os.path.isdir(d)]
    return out


def read_header(path):
    with open(path, "rb") as f:
        b = f.read(0x80)
    if b[:4] != b"GGDS":
        raise ValueError("not_hfw_save")
    title = b[0x14:0x80].split(b"\0")[0].decode("utf-8", "replace").strip()
    m = HEADER_RE.match(title)
    if not m:
        return dict(title=title, quest=title, level=None, playH=0)
    quest = re.sub(r"^Salvamento autom\w+ d[aeo]s? ", "", m.group("quest"))
    play = int(m.group("h")) + int(m.group("m")) / 60 + int(m.group("s")) / 3600
    return dict(title=title, quest=quest, level=int(m.group("lvl")) if m.group("lvl") else None, playH=round(play, 1))


def read_cover(path):
    """Cada save traz a foto da tela de carregar (PNG 480x270) dentro do próprio arquivo."""
    try:
        with open(path, "rb") as f:
            b = f.read()
    except OSError:
        return None
    i = b.find(b"\x89PNG\r\n\x1a\n")
    j = b.find(b"IEND", i) if i >= 0 else -1
    if i < 0 or j < 0 or j + 8 - i > 400_000:
        return None
    import base64
    return "data:image/png;base64," + base64.b64encode(b[i:j + 8]).decode()


def analyze(header, ach):
    quest = (header.get("quest") or "").lower()
    contents, last = [], {}
    for key, defs in CONTENT:
        segs = []
        for d in defs:
            hits = [ach[a] for a in d["ach"] if a in ach and ach[a]["unlocked"]]
            segs.append(dict(title=d["title"], h=d["h"], done=bool(hits), frac=1.0 if hits else 0.0, gate=d.get("gate", False),
                             here=any(q in quest for q in d.get("quests", []))))
            if hits:
                last[key] = max(last.get(key, 0), max(x["time"] for x in hits))
        # parte "porteira" feita: tudo antes dela também foi feito
        for i in range(len(segs) - 1, -1, -1):
            if segs[i]["done"] and segs[i]["gate"]:
                for s in segs[:i]:
                    s["done"], s["frac"] = True, 1.0
                break
        started = any(s["done"] for s in segs) or any(s["here"] for s in segs)
        # parte atual: a missão do save, ou a primeira que falta
        cur = next((s for s in segs if s["here"] and not s["done"]), None) or (next((s for s in segs if not s["done"]), None) if started else None)
        if cur:
            cur["frac"] = 0.5 if cur["here"] else 0.25
        contents.append(common.build_content(key, segs, finished=all(s["done"] for s in segs), started=started))
    andamento = [c for c in contents if c["status"] == "andamento"]
    cur = max(andamento, key=lambda c: last.get(c["key"], 0)) if andamento else contents[0]
    return dict(current=cur["key"], contents=contents)


def latest(cache):
    dirs = save_dirs()
    found = common.find_latest(dirs, "*.dat", exclude=["profile.dat"])
    if not found:
        return None
    path, mtime = found
    files = common.find_files(dirs, "*.dat", exclude=["profile.dat"])
    schema, users = steam.stats_files(STEAM_APPID)
    stamp = max([os.path.getmtime(u) for u in users] + [0])

    def compute():
        headers = []
        for p in files:
            try:
                headers.append(read_header(p))
            except (OSError, ValueError):
                pass
        if not headers:
            raise ValueError("nenhum save legível")  # há saves, mas nenhum foi lido: aparece como aviso
        # o save mais avançado (mais tempo de jogo) é o atual
        headers.sort(key=lambda h: -h["playH"])
        newest = headers[0]
        # missão principal: a do save mais avançado que esteja numa missão da história
        # (o mais novo pode ser de uma atividade paralela, como um Caldeirão)
        known = [q for _k, defs in CONTENT for d in defs for q in d.get("quests", [])]
        story = next((h for h in headers if any(q in h["quest"].lower() for q in known)), newest)
        ach = steam.achievements(STEAM_APPID) or {}
        res = analyze(story, ach)
        res.update(playH=newest["playH"], saveFile=newest["title"] or os.path.basename(path),
                   saveDate=int(mtime * 1000), cover=read_cover(path), source="save")
        return res
    return common.cached(cache, (ID, path, mtime, stamp), compute)
