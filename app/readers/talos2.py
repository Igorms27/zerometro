"""The Talos Principle 2 (PC, Steam).

O save (Unreal, formato GVAS) guarda várias cópias do estado; usamos a de maior tempo de jogo.
Dentro dela, a lista SetBooleanVariables tem uma marca para cada enigma resolvido ("E1:Puzzle3"),
cada torre ativada ("E1:TowerActive") e cada etapa das megaestruturas.
"""
import glob
import os
import re
import struct

ID, NAME, PLATFORM = "talos2", "The Talos Principle 2", "PC · Steam"
STEAM_APPID = "835960"
LABELS = {"base": "História principal"}

AREAS = [  # código da área no save -> nome no jogo
    ("E1", "Anel do Campo"), ("E2", "Platô Arborizado"), ("E3", "Pântanos Orientais"),
    ("N1", "Ilha Desolada"), ("N2", "Vale Inundado"), ("N3", "Brejos Perdidos"),
    ("S1", "Costa Sul"), ("S2", "Cânion Verdejante"), ("S3", "Oásis Circular"),
    ("W1", "Delta Ocidental"), ("W2", "Montes Antrópicos"), ("W3", "Planície Elevada"),
]
MEGA = {  # megaestrutura no fim de cada direção: marca de concluída, prefixo das marcas de progresso
    "E": ("Megaestrutura Leste", "Objective:PyramidE_Depart_Completed", ("General.ME:", "Pyramid_Interior_E")),
    "N": ("Megaestrutura Norte", "Objective:PyramidN_GetOut_Completed", ("MN:", "Pyramid_Interior_N", "General.InteriorNorth")),
    "S": ("Megaestrutura Sul", "Objective:PyramidS_Depart_Completed", ("MS:", "Objective:PrometheusChains", "Objective:PyramidS_")),
}
ENDINGS = ("BreakTheLoop", "TheFuture")
H_PROLOGO, H_AREA, H_MEGA, H_FINAL = 2.0, 1.4, 0.6, 2.0


def save_dirs():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return [os.path.join(base, "Talos2", "Saved", "SaveGames")]


def _fstring(b, i):
    n = struct.unpack_from("<i", b, i)[0]; i += 4
    if n < 0:
        s = b[i:i - 2 * n].decode("utf-16-le", "replace"); i -= 2 * n
    else:
        s = b[i:i + n].decode("utf-8", "replace"); i += n
    return s.rstrip("\0"), i


def _str_array(b, name, start, end):
    """Lê um ArrayProperty de strings (nome, tipo, tamanho, tipo interno, contagem, itens)."""
    i = b.find(name.encode() + b"\0", start, end)
    if i < 0:
        return []
    i = b.index(b"ArrayProperty\0", i) + len(b"ArrayProperty\0") + 8
    _inner, i = _fstring(b, i)
    i += 1
    count = struct.unpack_from("<i", b, i)[0]; i += 4
    out = []
    for _ in range(max(0, min(count, 100000))):
        s, i = _fstring(b, i)
        out.append(s)
    return out


def read_save(path):
    with open(path, "rb") as f:
        b = f.read()
    if b[:4] != b"GVAS":
        raise ValueError("not_talos2_save")
    snaps = [(struct.unpack("<f", m.group(1))[0], m.start())
             for m in re.finditer(rb"TimePlayed\x00\x0e\x00\x00\x00FloatProperty\x00.{8}\x00(.{4})", b, re.S)]
    if not snaps:
        raise ValueError("sem_tempo_de_jogo")
    starts = sorted(p for _t, p in snaps)
    secs, pos = max(snaps)
    end = next((p for p in starts if p > pos), len(b))
    world = re.findall(rb"LastPlayedWorld\x00\x0c\x00\x00\x00StrProperty\x00.{9}.{4}([A-Za-z0-9_]+)\x00", b[max(0, pos - 300):pos], re.S)
    flags = set(_str_array(b, "SetBooleanVariables", pos, end))
    ach = set(_str_array(b, "UnlockedAchievements", 0, len(b)))
    return dict(playH=round(secs / 3600, 1), flags=flags, ach=ach, world=(world[-1].decode() if world else ""))


def analyze(st):
    flags, ach, world = st["flags"], st["ach"], st["world"].split("_")[0]
    segs = []
    began = "Wanderers" in ach or any(f.startswith("E1:") for f in flags)
    segs.append(dict(title="Prólogo e Nova Jerusalém", h=H_PROLOGO, frac=1.0 if began else 0.5, here=False))
    for idx, (code, name) in enumerate(AREAS):
        solved = sum(1 for k in range(8) if "%s:Puzzle%d" % (code, k) in flags)
        done = "%s:TowerActive" % code in flags
        segs.append(dict(title=name, h=H_AREA, frac=1.0 if done else min(solved / 8, 0.9), here=(world == code)))
        if idx % 3 == 2 and code[0] in MEGA:
            title, mark, prefixes = MEGA[code[0]]
            partial = any(f.startswith(prefixes) for f in flags)
            segs.append(dict(title=title, h=H_MEGA, frac=1.0 if mark in flags else (0.5 if partial else 0.0), here=False))
    final = any(a in ach for a in ENDINGS)
    w_mega = any(f.startswith(("MW:", "Pyramid_Interior_W", "Objective:PyramidW")) for f in flags)
    segs.append(dict(title="Megaestrutura Oeste e final", h=H_FINAL, frac=1.0 if final else (0.5 if w_mega else 0.0), here=False))
    # se uma parte foi concluída, as anteriores obrigatórias também foram (torres de cada direção levam à megaestrutura)
    for s in segs:
        s["done"] = s["frac"] >= 1.0
    # parte atual sem enigma resolvido ainda conta um pouco
    for s in segs:
        if s["here"] and not s["done"] and s["frac"] == 0:
            s["frac"] = 0.1
    total = sum(s["h"] for s in segs)
    got = sum(s["h"] * s["frac"] for s in segs)
    fin = final
    started = got > 0
    c = dict(key="base", status="zerado" if fin else ("andamento" if started else "nao_iniciado"),
             pct=round(100.0 if fin else got / total * 100, 1), total=total, left=round(total - got, 2),
             pace=1.0, paceKnown=False,
             segs=[dict(title=s["title"], h=s["h"], frac=round(s["frac"], 2), done=s["done"]) for s in segs])
    return dict(current="base", contents=[c])


def latest(cache):
    files = []
    for d in save_dirs():
        files += glob.glob(os.path.join(d, "savedata_*.sav"))
    if not files:
        return None
    path = max(files, key=os.path.getmtime)
    mtime = os.path.getmtime(path)
    key = (ID, path, mtime)
    if key not in cache:
        st = read_save(path)
        res = analyze(st)
        area = dict(AREAS).get(st["world"].split("_")[0])
        res.update(playH=st["playH"], saveFile=("Em " + area) if area else os.path.basename(path),
                   saveDate=int(mtime * 1000), cover=None, source="save")
        for k in [k for k in cache if k[0] == ID]:
            del cache[k]
        cache[key] = res
    return cache[key]
