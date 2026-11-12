"""Peças comuns dos leitores de jogo.

Um leitor de save só precisa dizer onde o save fica (save_dirs), como ler (analyze) e montar a lista de
partes da história; achar o save mais novo, usar o cache, juntar a capa e calcular a % ficam aqui.
"""
import base64
import glob
import os

_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def find_files(dirs, pattern, exclude=None):
    """Todos os arquivos que casam com `pattern` dentro de cada pasta de `dirs` (pastas que não existem são ignoradas).
    `exclude`: nomes de arquivo (sem maiúsculas/minúsculas) a deixar de fora."""
    skip = {x.lower() for x in (exclude or ())}
    out = []
    for d in dirs:
        if d and os.path.isdir(d):
            out += [p for p in glob.glob(os.path.join(d, pattern)) if os.path.basename(p).lower() not in skip]
    return out


def find_latest(dirs, pattern, exclude=None):
    """(caminho, data de modificação) do arquivo mais novo, ou None se não houver nenhum."""
    files = find_files(dirs, pattern, exclude)
    if not files:
        return None
    path = max(files, key=os.path.getmtime)
    return path, os.path.getmtime(path)


def cached(cache, key, compute):
    """Devolve cache[key]; se não houver, chama compute() e guarda. Só a entrada mais nova de cada jogo
    (key[0] = id do jogo) fica na memória."""
    if key not in cache:
        res = compute()
        if res is None:  # nada a mostrar: não guarda, tenta de novo na próxima
            return None
        for k in [k for k in cache if k[0] == key[0]]:
            del cache[k]
        cache[key] = res
    return cache[key]


def cover_from(path, limit=180000):
    """Foto de um arquivo (png/jpg) como data URI, ou None se não existir ou for grande demais."""
    mime = _MIME.get(os.path.splitext(path)[1].lower())
    if not mime or not os.path.exists(path) or os.path.getsize(path) >= limit:
        return None
    with open(path, "rb") as f:
        return "data:%s;base64,%s" % (mime, base64.b64encode(f.read()).decode())


def build_content(key, segs, finished=None, started=None, pace=1.0, pace_known=False, ndigits=None, **extra):
    """Monta uma campanha a partir das partes (cada uma com title, h = horas, frac = 0..1 e, opcional, done).
    pct, total e left saem das horas. `finished`/`started` valem se o leitor tiver regra própria; senão
    zerado = todas as partes feitas e começou = alguma fração. `pace_known=None` omite o campo.
    `ndigits` arredonda as horas das partes e o total."""
    segs = list(segs)
    total = sum(s["h"] for s in segs)
    got = sum(s["h"] * s["frac"] for s in segs)
    if finished is None:
        finished = all(s.get("done", s["frac"] >= 1.0) for s in segs)
    if started is None:
        started = got > 0
    rnd = (lambda x: round(x, ndigits)) if ndigits is not None else (lambda x: x)
    out = dict(key=key, status="zerado" if finished else ("andamento" if started else "nao_iniciado"),
               pct=round(100.0 if finished else got / total * 100, 1), total=rnd(total),
               left=round(total - got, 2), pace=pace)
    if pace_known is not None:
        out["paceKnown"] = pace_known
    out.update(extra)
    out["segs"] = [dict(title=s["title"], h=rnd(s["h"]), frac=round(s["frac"], 2), done=bool(s.get("done", s["frac"] >= 1.0)))
                   for s in segs]
    return out


def error_entry(mod, exc):
    """O save existe mas não foi lido: o que mostrar no lugar do jogo."""
    if isinstance(exc, OSError):
        msg = "Achei o save, mas não consegui abrir o arquivo (ele pode estar em uso ou sem permissão)."
    elif isinstance(exc, ValueError):
        msg = "Achei o save, mas não reconheci o formato. O jogo pode ter atualizado."
    else:
        msg = "Achei o save, mas deu erro ao ler."
    return dict(id=mod.ID, name=mod.NAME, platform=mod.PLATFORM, appid=getattr(mod, "STEAM_APPID", None), erro=msg)
