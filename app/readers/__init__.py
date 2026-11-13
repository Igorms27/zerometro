"""Todos os jogos que o Zerômetro sabe ler. Primeiro o save; se não der, as conquistas da Steam.

Para um jogo cujo save existe mas não pôde ser lido, scan() devolve {id, name, platform, appid, erro}
(sem "contents") no lugar do jogo, para a tela avisar em vez de o jogo sumir.
"""
import logging

from . import base, botw, by_achievements, covers, horizon_fw, rv_there_yet, steam, talos2, witcher3

SAVE_READERS = [witcher3, botw, horizon_fw, talos2, rv_there_yet]
_cache = {}
log = logging.getLogger("zerometro")


def scan():
    games, done_ids, errors = [], set(), {}
    for mod in SAVE_READERS:
        try:
            r = mod.latest(_cache)
        except Exception as e:  # save estragado ou formato novo: não derruba os outros jogos
            log.exception("erro lendo %s", mod.ID)
            errors[mod.ID] = base.error_entry(mod, e)
            r = None
        if r:
            if not r.get("cover"):  # save sem foto: capa do jogo na Steam
                r = dict(r, cover=covers.url(getattr(mod, "STEAM_APPID", None)))
            games.append(dict(r, id=mod.ID, name=mod.NAME, platform=mod.PLATFORM, labels=mod.LABELS))
            done_ids.add(mod.ID)
    for appid, g in list(by_achievements.GAMES.items()):
        if g["id"] in done_ids:
            continue
        try:
            r = by_achievements.analyze(appid)
        except Exception:
            log.exception("erro lendo conquistas %s", appid)
            r = None
        if r and r["contents"] and any(c["status"] != "nao_iniciado" for c in r["contents"]):
            games.append(dict(r, cover=r.get("cover") or covers.url(appid)))
            errors.pop(g["id"], None)  # as conquistas cobriram o jogo: não precisa de aviso
    return games + list(errors.values())
