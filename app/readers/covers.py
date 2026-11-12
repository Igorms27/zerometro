"""Capa do jogo para quando o save não tem foto: a arte que a Steam já guarda no PC ou, se não tiver, a da loja."""
import glob
import os
import re
import urllib.request

from . import paths, steam

NAMES = ("library_hero.jpg", "library_header.jpg", "header.jpg")
CDN = "https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/%s/%s"


def url(appid):
    return "/api/cover/%s" % appid if appid else None


def _local(appid):
    root = steam.steam_root()
    if not root:
        return None
    cache = os.path.join(root, "appcache", "librarycache")
    for name in NAMES:
        # formato novo: librarycache/<appid>/<hash>/library_hero.jpg; antigo: librarycache/<appid>_library_hero.jpg
        hits = glob.glob(os.path.join(cache, appid, "*", name)) + glob.glob(os.path.join(cache, appid, name)) \
            + glob.glob(os.path.join(cache, "%s_%s" % (appid, name)))
        if hits:
            return max(hits, key=os.path.getmtime)
    return None


def get(appid):
    """Bytes JPEG da capa, ou None."""
    appid = str(appid)
    if not re.match(r"^\d{1,10}$", appid):
        return None
    p = _local(appid)
    if p:
        with open(p, "rb") as f:
            return f.read()
    saved = paths.data_path("capas", appid + ".jpg")
    if os.path.exists(saved):
        with open(saved, "rb") as f:
            return f.read()
    for name in NAMES:
        try:
            req = urllib.request.Request(CDN % (appid, name), headers={"User-Agent": "Zerometro"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = r.read(3_000_000)
        except OSError:
            continue
        os.makedirs(os.path.dirname(saved), exist_ok=True)
        with open(saved, "wb") as f:
            f.write(data)
        return data
    return None
