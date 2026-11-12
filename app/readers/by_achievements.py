"""Plano B: progresso pela lista de conquistas da Steam, quando não dá para ler o save.

Cada jogo aqui diz quais conquistas fecham cada parte da história. Uma parte conta como feita
quando qualquer uma das conquistas dela foi desbloqueada.
"""
from . import base as common
from . import steam

# appid -> definição. Para adicionar um jogo: veja o schema no relatório e liste as conquistas de história.
GAMES = {
    "292030": dict(
        id="w3", name="The Witcher 3", platform="PC · Steam",
        labels={"base": "História principal"},
        contents=[("base", [
            dict(title="Pomar Branco", h=4, ach=["LILAC"]),
            dict(title="Velen", h=11, ach=["FAMILY_COUNSELOR"]),
            dict(title="Novigrad", h=13, ach=["FRIEND_IN_NEED"]),
            dict(title="Skellige", h=9, ach=["NECROMANCER"]),
            dict(title="Kaer Morhen", h=6, ach=["SOMETHING_MORE"]),
            dict(title="Reta final", h=8.5, ach=["THE_KING", "PASSED_THE_TRIAL"]),
        ])],
    ),
}


def analyze(appid):
    g = GAMES.get(str(appid))
    if not g:
        return None
    ach = steam.achievements(appid)
    if not ach:
        return None
    contents, last = [], {}
    for key, defs in g["contents"]:
        segs = []
        for d in defs:
            hits = [ach[a] for a in d["ach"] if a in ach and ach[a]["unlocked"]]
            segs.append(dict(title=d["title"], h=d["h"], frac=1.0 if hits else 0.0, done=bool(hits)))
            if hits:
                last[key] = max(last.get(key, 0), max(x["time"] for x in hits))
        # partes antes de uma parte feita também contam como feitas (a história é em ordem)
        for i in range(len(segs) - 1, -1, -1):
            if segs[i]["done"]:
                for s in segs[:i]:
                    s["done"], s["frac"] = True, 1.0
                break
        contents.append(common.build_content(key, segs))
    cur = max(contents, key=lambda c: (c["status"] == "andamento", last.get(c["key"], 0)))
    stamp = max(last.values()) if last else 0
    return dict(current=cur["key"], playH=0, contents=contents, saveFile="conquistas da Steam",
                saveDate=stamp * 1000, cover=None, source="steam",
                id=g["id"], name=g["name"], platform=g["platform"], labels=g["labels"])
