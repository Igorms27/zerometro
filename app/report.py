"""Relatório para jogos que o Zerômetro ainda não lê: junta os saves e as conquistas num .zip.

A pessoa manda o .zip; com ele dá para entender o formato do save e adicionar o jogo numa versão nova.
"""
import datetime
import json
import os
import platform
import re
import time
import zipfile

import anonymize
from readers import paths, steam

MAX_TOTAL = 60 * 1024 * 1024     # tamanho máximo dos saves dentro do .zip
MAX_FILE = 30 * 1024 * 1024
SKIP_EXT = {".exe", ".dll", ".pak", ".bk2", ".bik", ".mp4", ".webm", ".pdb", ".lnk", ".url",
            ".ushaderprecache", ".upipelinecache", ".dmp", ".mdmp"}
SKIP_DIRS = {"cache", "shadercache", "shadercaches", "crashes", "crashreportclient", "logs", "webcache", "gpucache", "code cache"}


def _words(s):
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    return [w for w in re.split(r"[^a-z0-9]+", s.lower()) if (len(w) > 1 or w.isdigit()) and w not in ("the", "of", "and", "edition", "complete", "definitive", "remastered", "goty")]


def _roots(appid):
    home = os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
    roots = []
    for d in paths.documents_dirs():
        roots += [d, os.path.join(d, "My Games")]
    roots += [os.path.join(home, "Saved Games"), local, local + "Low", os.environ.get("APPDATA") or "",
              os.path.join(home, "AppData", "LocalLow")]
    return [r for r in dict.fromkeys(roots) if r and os.path.isdir(r)]


GENERIC = {"game", "games", "studio", "studios", "simulator", "online", "world", "edition", "remake", "collection"}
SAVE_DIR_RE = re.compile(r"^(save|saves|savegame|savegames|saved ?games|savedata|save ?data|profiles?|userdata|player ?prefs)$", re.I)


def _by_name(want, found):
    """Pastas com o nome do jogo em Documentos, AppData, Jogos Salvos..."""
    strong = {w for w in want if len(w) >= 5 and w not in GENERIC}
    for root in _roots(None):
        try:
            lvl1 = [os.path.join(root, x) for x in os.listdir(root)]
        except OSError:
            continue
        cands = []
        for d in lvl1:
            if not os.path.isdir(d):
                continue
            cands.append(d)
            try:  # empresa/jogo, ex.: LocalLow\Studio\Jogo
                cands += [os.path.join(d, y) for y in os.listdir(d) if os.path.isdir(os.path.join(d, y))]
            except OSError:
                pass
        for d in cands:
            got = set(_words(os.path.basename(d)))
            hit = want & got
            if not hit or not (len(hit) >= 2 or hit & strong):
                continue
            # nome inteiro: palavras que sobram de um lado ou do outro tiram pontos
            # ("Horizon Zero Dawn" não é "Horizon Forbidden West"; "Talos" ainda vale para "The Talos Principle")
            score = len(hit) / len(want | got)
            nums_w = {w for w in want if w.isdigit()}
            nums_g = {w for w in got if w.isdigit()}
            if nums_w != nums_g:  # "Talos Principle" x "Talos Principle 2": jogos diferentes
                score *= 0.6
            if score < 0.3 or _is_program_dir(d):
                continue
            found[d] = max(found.get(d, 0), round(score, 2))


PROGRAM_MARKERS = {"local storage", "code cache", "gpucache", "session storage", "indexeddb", "blob_storage", "dawncache", "crashpad", "service worker"}


def _is_program_dir(d):
    """Pasta de um programa (launcher, app em Electron/Chromium), não de saves."""
    try:
        names = {x.lower() for x in os.listdir(d)}
    except OSError:
        return False
    if names & PROGRAM_MARKERS or any(n.endswith(".asar") for n in names):
        return True
    return False


def _by_steam_cloud(appid, game, found):
    """A Steam lista os arquivos que cada jogo sincroniza (remotecache.vdf), com a pasta-base de cada um."""
    root = steam.steam_root()
    if not root:
        return
    home = os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
    bases = [os.path.join(home, "Saved Games"), local, local + "Low", os.environ.get("APPDATA") or "",
             os.environ.get("PROGRAMDATA") or ""] + paths.documents_dirs()
    if game and game.get("installpath"):
        bases.append(game["installpath"])
    ud = os.path.join(root, "userdata")
    try:
        users = os.listdir(ud)
    except OSError:
        return
    for u in users:
        app_dir = os.path.join(ud, u, str(appid))
        remote = os.path.join(app_dir, "remote")
        if os.path.isdir(remote) and any(os.scandir(remote)):
            found[remote] = max(found.get(remote, 0), 0.95)
        rc = os.path.join(app_dir, "remotecache.vdf")
        try:
            txt = open(rc, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for rel, rootnum in re.findall(r'^\t"([^"\n]+)"\s*\n\t\{\s*\n\t\t"root"\s+"(\d+)"', txt, re.M):
            rel = rel.replace("/", os.sep)
            if rootnum == "0":
                cand = [os.path.join(remote, rel)]
            else:  # o número da pasta-base varia; vale a que tiver o arquivo de verdade
                cand = [os.path.join(b, rel) for b in bases if b]
            for p in cand:
                if os.path.isfile(p):
                    found[os.path.dirname(p)] = max(found.get(os.path.dirname(p), 0), 1.0)
                    break


def _in_install_dir(game, found):
    """Pastas de save dentro da pasta do jogo (alguns jogos salvam ali)."""
    base = game and game.get("installpath")
    if not base or not os.path.isdir(base):
        return
    start = base.count(os.sep)
    for dp, dn, _fn in os.walk(base):
        if dp.count(os.sep) - start >= 5:
            dn[:] = []
            continue
        for d in dn:
            if SAVE_DIR_RE.match(d):
                found[os.path.join(dp, d)] = max(found.get(os.path.join(dp, d), 0), 0.85)


def find_folders(name, appid=None):
    """Pastas que provavelmente têm os saves do jogo, da mais provável para a menos."""
    game = None
    if appid:
        game = next((g for g in steam.installed_games() if g["appid"] == str(appid)), None)
        if game and not name:
            name = game["name"]
    want = set(_words(name or ""))
    if game:
        want |= set(_words(game.get("installdir", "")))
    found = {}
    if appid:
        _by_steam_cloud(appid, game, found)
        _in_install_dir(game, found)
    if want:
        _by_name(want, found)
    # pasta dentro de outra já encontrada: fica só a de fora (o .zip pega tudo dentro dela)
    keys = sorted(found, key=len)
    for k in keys:
        for parent in keys:
            if parent != k and parent in found and k in found and k.lower().startswith(parent.lower().rstrip(os.sep) + os.sep) and found[parent] >= found[k] - 0.2:
                found[parent] = max(found[parent], found.pop(k, 0))
                break
    out = []
    for d, score in sorted(found.items(), key=lambda x: -x[1]):
        n, size, newest = 0, 0, 0
        for dp, _dn, fn in os.walk(d):
            for f in fn:
                try:
                    st = os.stat(os.path.join(dp, f))
                except OSError:
                    continue
                n += 1; size += st.st_size; newest = max(newest, st.st_mtime)
            if n > 5000:
                break
        if n:
            out.append(dict(path=d, files=n, size=size, newest=int(newest * 1000), score=round(score, 2)))
    return out[:12]


def _desktop():
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf) == 0 and os.path.isdir(buf.value):
            return buf.value
    except Exception:
        pass
    d = os.path.join(os.path.expanduser("~"), "Desktop")
    return d if os.path.isdir(d) else os.path.expanduser("~")


def build(name, appid, folders, app_version):
    safe = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-")[:40] or "jogo"
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    out = os.path.join(_desktop(), "Zerometro-relatorio-%s-%s.zip" % (safe, stamp))
    # dados pessoais saem do relatório: usuário do Windows nos caminhos, ID da conta Steam, log (ver anonymize.py)
    an = anonymize.Anon(account_ids=anonymize.steam_accounts(steam.steam_root()))
    manifest = dict(app_version=app_version, created=stamp, game=name, appid=appid,
                    windows=platform.platform(), folders=[], skipped=[], steam={}, steamid_no_conteudo=[],
                    anonimizado="caminhos do usuario -> %USERPROFILE%; ID Steam trocado por STEAMID_xxxxxx; "
                                "log filtrado; conteudo de saves binarios nao foi alterado")
    total = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for i, folder in enumerate(folders):
            files = []
            for dp, dn, fn in os.walk(folder):
                dn[:] = [d for d in dn if d.lower() not in SKIP_DIRS]
                for f in fn:
                    p = os.path.join(dp, f)
                    try:
                        st = os.stat(p)
                    except OSError:
                        continue
                    files.append((st.st_mtime, st.st_size, p))
            files.sort(reverse=True)  # mais novos primeiro
            listing = []
            for mtime, size, p in files:
                rel = os.path.relpath(p, folder)
                shown = an.path(rel)
                head = ""
                try:
                    with open(p, "rb") as fh:
                        head = an.head_hex(fh.read(64))
                except OSError:
                    pass
                listing.append(dict(file=shown, size=size, mtime=int(mtime), head=head))
                if os.path.splitext(p)[1].lower() in SKIP_EXT or size > MAX_FILE or total + size > MAX_TOTAL:
                    manifest["skipped"].append(dict(folder=i, file=shown, size=size))
                    continue
                try:
                    with open(p, "rb") as fh:
                        data = fh.read()
                    data, _changed = an.file_content(p, data)
                    if _changed is False and an.has_id(data):
                        manifest["steamid_no_conteudo"].append(dict(folder=i, file=shown))
                    zi = zipfile.ZipInfo("saves/%d/%s" % (i, shown.replace("\\", "/")), date_time=max(time.localtime(mtime)[:6], (1980, 1, 1, 0, 0, 0)))
                    zi.compress_type = zipfile.ZIP_DEFLATED  # mantém a data do arquivo, útil para ver qual save é o mais novo
                    z.writestr(zi, data)
                    total += size
                except OSError:
                    manifest["skipped"].append(dict(folder=i, file=shown, size=size, erro="sem acesso"))
            manifest["folders"].append(dict(index=i, path=an.path(folder), files=listing))
        if appid:
            schema, users = steam.stats_files(appid)
            for p in ([schema] if schema else []) + users:
                z.write(p, "steam/" + an.path(os.path.basename(p)))
            try:
                ach = steam.achievements(appid) or {}
                manifest["steam"] = dict(total=len(ach), unlocked=sum(a["unlocked"] for a in ach.values()))
                z.writestr("steam/conquistas.json", json.dumps(ach, ensure_ascii=False, indent=1))
            except Exception as e:
                manifest["steam"] = dict(erro=an.log_line(str(e)))
        log = paths.data_path("zerometro.log")
        if os.path.exists(log):
            try:
                with open(log, encoding="utf-8", errors="replace") as fh:
                    z.writestr("zerometro.log", an.log(fh.read()))
            except OSError:
                pass
        manifest["steam_ids_trocados"] = len(an.seen)
        z.writestr("relatorio.json", json.dumps(manifest, ensure_ascii=False, indent=1))
    return dict(path=out, size=os.path.getsize(out), saved=total, skipped=len(manifest["skipped"]))
