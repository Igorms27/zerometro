"""Conquistas da Steam, lidas dos arquivos que a própria Steam guarda no PC (plano B quando o save não dá).

appcache/stats/UserGameStatsSchema_<appid>.bin  -> nomes e descrições das conquistas
appcache/stats/UserGameStats_<conta>_<appid>.bin -> quais a pessoa já desbloqueou
"""
import glob
import os
import re
import struct

# ---------- KeyValues binário da Steam ----------

def kv_parse(b, i=0):
    out = {}
    while i < len(b):
        t = b[i]; i += 1
        if t == 0x08 or t == 0x0B:
            return out, i
        end = b.index(b"\0", i)
        key = b[i:end].decode("utf-8", "replace"); i = end + 1
        if t == 0x00:
            out[key], i = kv_parse(b, i)
        elif t == 0x01:
            end = b.index(b"\0", i)
            out[key] = b[i:end].decode("utf-8", "replace"); i = end + 1
        elif t in (0x02, 0x04, 0x06):
            out[key] = struct.unpack_from("<i", b, i)[0]; i += 4
        elif t == 0x03:
            out[key] = struct.unpack_from("<f", b, i)[0]; i += 4
        elif t in (0x07, 0x0A):
            out[key] = struct.unpack_from("<q", b, i)[0]; i += 8
        elif t == 0x05:  # string larga (raro)
            end = i
            while b[end:end + 2] != b"\0\0":
                end += 2
            out[key] = b[i:end].decode("utf-16-le", "replace"); i = end + 2
        else:
            raise ValueError("kv tipo %d" % t)
    return out, i


def kv_load(path):
    with open(path, "rb") as f:
        return kv_parse(f.read())[0]

# ---------- onde está a Steam ----------

def steam_root():
    try:
        import winreg
        for hive, sub in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
            try:
                with winreg.OpenKey(hive, sub) as k:
                    for name in ("SteamPath", "InstallPath"):
                        try:
                            p = winreg.QueryValueEx(k, name)[0]
                            if p and os.path.isdir(p):
                                return os.path.normpath(p)
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass
    p = r"C:\Program Files (x86)\Steam"
    return p if os.path.isdir(p) else None


def library_dirs(root):
    dirs = [root]
    vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
    try:
        txt = open(vdf, encoding="utf-8", errors="replace").read()
        dirs += [p.replace("\\\\", "\\") for p in re.findall(r'"path"\s+"([^"]+)"', txt)]
    except OSError:
        pass
    seen, out = set(), []
    for d in dirs:
        k = os.path.normcase(os.path.normpath(d))
        if k not in seen and os.path.isdir(d):
            seen.add(k); out.append(d)
    return out


def installed_games(root=None):
    """[{appid, name, installdir}] dos jogos instalados em todas as bibliotecas."""
    root = root or steam_root()
    if not root:
        return []
    games = []
    for lib in library_dirs(root):
        for acf in glob.glob(os.path.join(lib, "steamapps", "appmanifest_*.acf")):
            try:
                txt = open(acf, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            g = dict(re.findall(r'"(appid|name|installdir|LastPlayed)"\s+"([^"]*)"', txt))
            if g.get("appid") and g.get("name") and not re.search(r"redistributable|proton|steamworks|runtime", g["name"], re.I):
                g["library"] = lib
                g["installpath"] = os.path.join(lib, "steamapps", "common", g.get("installdir", ""))
                g["lastplayed"] = int(g.pop("LastPlayed", 0) or 0)
                games.append(g)
    # jogado por último primeiro (é quase sempre o jogo do relatório)
    return sorted(games, key=lambda g: (-g["lastplayed"], g["name"].lower()))


def stats_files(appid, root=None):
    root = root or steam_root()
    if not root:
        return None, []
    d = os.path.join(root, "appcache", "stats")
    schema = os.path.join(d, "UserGameStatsSchema_%s.bin" % appid)
    users = glob.glob(os.path.join(d, "UserGameStats_*_%s.bin" % appid))
    return (schema if os.path.exists(schema) else None), users

# ---------- conquistas de um jogo ----------

def achievements(appid, root=None):
    """{api_name: {"name", "desc", "unlocked": bool, "time": int}} ou None se a Steam não tem os arquivos."""
    schema_p, users = stats_files(appid, root)
    if not schema_p:
        return None
    schema = kv_load(schema_p)
    top = next(iter(schema.values())) if len(schema) == 1 else schema
    stats = top.get("stats", {})
    # estado do usuário mais recente (se houver mais de uma conta no PC)
    user = {}
    if users:
        user = kv_load(max(users, key=os.path.getmtime))
        if isinstance(user.get("cache"), dict):  # os dados ficam dentro de "cache"
            user = user["cache"]
    out = {}
    for sid, s in stats.items():
        if not isinstance(s, dict) or str(s.get("type")) not in ("4", "ACHIEVEMENTS"):
            continue
        u = user.get(sid, {}) if isinstance(user.get(sid), dict) else {}
        data = u.get("data", 0) or 0
        times = u.get("AchievementTimes", {}) or {}
        for bit, a in (s.get("bits") or {}).items():
            disp = a.get("display", {}) or {}
            nm = disp.get("name", {}) or {}
            ds = disp.get("desc", {}) or {}
            pick = lambda d: (d.get("brazilian") or d.get("english") or next(iter(d.values()), "")) if isinstance(d, dict) else str(d)
            got = bool((data >> int(bit)) & 1)
            out[a.get("name", "%s_%s" % (sid, bit))] = dict(
                name=pick(nm), desc=pick(ds), unlocked=got, time=int(times.get(bit, 0) or 0) if got else 0)
    return out
