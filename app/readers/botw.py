"""Zelda: Breath of the Wild no Savage Wind Recomp (PC): lê as flags do game_data.sav."""
import os
import struct
import zlib

from . import base as common
from . import paths

ID, NAME, PLATFORM = "botw", "Zelda: Breath of the Wild", "PC · Savage Wind"
STEAM_APPID = None
LABELS = {"zbase": "História principal", "ballad": "A Balada dos Campeões"}


def save_dirs():
    out = []
    root = os.environ.get("SAVAGEWIND_DATA_ROOT")
    if root:
        out.append(os.path.join(root, "save", "save_0"))
    out.append(r"C:\dev\savagewindrecomp\save\save_0")
    out += [os.path.join(d, "save", "save_0") for d in paths.extra_dirs("botw")]
    return out

# ---------- Zelda: Breath of the Wild (Savage Wind Recomp) ----------

# cada parte: horas médias, flag que fecha, flags que mostram que começou, flags de meio do caminho
BOTW_CONTENT = [
    ("zbase", [
        dict(title="O Planalto Isolado", h=3, done=["IsGet_PlayerStole2"], start=["FirstTower_Finish", "FindDungeon_Activated"]),
        dict(title="Encontre a Impa", h=2, done=["Find_Impa_Finish"], start=["Find_Impa_Activated"]),
        dict(title="Memórias trancadas", h=2, done=["Hateno_SheikPad_PowerUp_Finish"], start=["Hateno_SheikPad_PowerUp_Activated"]),
        dict(title="Besta Divina Vah Ruta", h=7, done=["Clear_RemainsWater"], start=["GotoZoraVillage_Activated", "Water_Relic_Activated"], mid=["GotoZoraVillage_Finish", "Water_Relic_Step1"]),
        dict(title="Besta Divina Vah Rudania", h=6, done=["Clear_RemainsFire"], start=["Fire_Relic_Activated"], mid=["Fire_Relic_Step1"]),
        dict(title="Besta Divina Vah Naboris", h=7, done=["Clear_RemainsElectric"], start=["Thunder_Sword_Activated", "Electric_Relic_Activated"], mid=["Thunder_Sword_Finish", "Gerudo_Ch_Helmet_Finish"]),
        dict(title="Besta Divina Vah Medoh", h=6, done=["Clear_RemainsWind"], start=["Wind_Relic_Activated"], mid=["Wind_Relic_Step1"]),
        dict(title="A Espada Mestra", h=3, done=["Get_MasterSword_Finish"], start=["Get_MasterSword_Activated"]),
        dict(title="Derrotar Ganon", h=4, done=["GanonQuest_Finished", "GameClear"], start=["IsHyruleCastlePGanonWaterDead", "IsHyruleCastlePGanonFireDead", "IsHyruleCastlePGanonElectricDead", "IsHyruleCastlePGanonWindDead"]),
    ]),
    ("ballad", [
        dict(title="Prova do Planalto", h=2, done=["BalladOfHeroZora_Activated", "BalladOfHeroGoron_Activated", "BalladOfHeroGerudo_Activated", "BalladOfHeroRito_Activated"], start=["BalladOfHeroes_Activated"]),
        dict(title="A canção de Mipha", h=2.5, done=["BalladOfHeroZora_Finish"], start=["BalladOfHeroZora_Activated"]),
        dict(title="A canção de Daruk", h=2.5, done=["BalladOfHeroGoron_Finish"], start=["BalladOfHeroGoron_Activated"]),
        dict(title="A canção de Urbosa", h=2.5, done=["BalladOfHeroGerudo_Finish"], start=["BalladOfHeroGerudo_Activated"]),
        dict(title="A canção de Revali", h=2.5, done=["BalladOfHeroRito_Finish"], start=["BalladOfHeroRito_Activated"]),
        dict(title="A Besta Divina final", h=2, done=["BalladOfHeroes_Finish"], start=["BalladOfHeroes_FourRemains_Clear"]),
    ]),
]


def botw_flags(data):
    """game_data.sav do Switch: cabeçalho de 12 bytes, pares (crc32 do nome, valor), rodapé FFFFFFFF."""
    if len(data) < 16 or data[-4:] != b"\xff\xff\xff\xff" or struct.unpack_from("<I", data, 4)[0] != 0xFFFFFFFF:
        raise ValueError("not_botw_save")
    vals = {}
    for off in range(12, len(data) - 4 - 7, 8):
        h, v = struct.unpack_from("<II", data, off)
        vals.setdefault(h, v)  # arrays repetem o hash; o 1º valor basta
    return vals


def botw_analyze(raw):
    vals = botw_flags(raw)
    get = lambda n: vals.get(zlib.crc32(n.encode()) & 0xFFFFFFFF, 0)
    on = lambda n: get(n) not in (0, 0xFFFFFFFF)
    contents = []
    for key, defs in BOTW_CONTENT:
        segs = []
        for d in defs:
            done = any(on(n) for n in d["done"])
            started = done or any(on(n) for n in d.get("start", []))
            frac = 1.0 if done else (0.0 if not started else (0.6 if any(on(n) for n in d.get("mid", [])) else 0.25))
            segs.append(dict(title=d["title"], h=d["h"], frac=frac, done=done, started=started))
        contents.append(common.build_content(key, segs, finished=all(x["done"] for x in segs),
                                             started=any(x["started"] for x in segs)))
    cur = next((c for c in reversed(contents) if c["status"] == "andamento"), None) or contents[0]
    return dict(current=cur["key"], playH=round(get("PlayReport_PlayTime") / 3600, 1), contents=contents)


def latest(cache):
    found = common.find_latest(save_dirs(), os.path.join("*", "game_data.sav"))
    if not found:
        return None
    path, mtime = found

    def compute():
        with open(path, "rb") as f:
            res = botw_analyze(f.read())
        res.update(saveFile="slot " + os.path.basename(os.path.dirname(path)), saveDate=int(mtime * 1000),
                   cover=common.cover_from(os.path.join(os.path.dirname(path), "caption.jpg")), source="save")
        return res
    return common.cached(cache, (ID, path, mtime), compute)
