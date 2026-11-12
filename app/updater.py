"""Atualização automática: ao abrir, confere no GitHub se tem versão nova e troca o próprio exe.

A versão nova passa a valer na próxima vez que o app for aberto.
Cada versão publicada tem dois arquivos: Zerometro.exe e version.json ({"version", "sha256"}).
"""
import hashlib
import json
import logging
import os
import sys
import time
import urllib.request

log = logging.getLogger("zerometro")
state = {"ready": None, "latest": None, "status": None}
# ready: versão já baixada e instalada, esperando o app reabrir
# latest: versão mais nova publicada; status: None, "baixando" ou "erro"
CHECK_EVERY = 3600  # com o app aberto, confere de novo a cada hora


def _ver(v):
    return tuple(int(x) for x in str(v).strip().lstrip("v").split(".") if x.isdigit())


def _get(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "Zerometro-updater"})
    return urllib.request.urlopen(req, timeout=timeout)


def loop(current, repo):
    test_base = os.environ.get("ZM_UPDATE_BASE")  # só para teste
    if not (repo or test_base):
        return
    exe = sys.executable
    for p in (exe + ".old", exe + ".new"):  # sobras da atualização anterior
        try:
            os.remove(p)
        except OSError:
            pass
    base = test_base or "https://github.com/%s/releases/latest/download/" % repo
    while not state["ready"]:
        run(current, base)
        time.sleep(CHECK_EVERY)


def run(current, base):
    exe = sys.executable
    new = exe + ".new"
    old = exe + ".old"
    try:
        info = json.load(_get(base + "version.json", 15))
        state["latest"] = info["version"]
        if _ver(info["version"]) <= _ver(current):
            return
        if not getattr(sys, "frozen", False):
            return  # rodando pelo Python: só avisa, não troca nada
        state["status"] = "baixando"
        log.info("versão nova %s encontrada, baixando", info["version"])
        h = hashlib.sha256()
        with _get(base + "Zerometro.exe", 60) as r, open(new, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                h.update(chunk); f.write(chunk)
        if h.hexdigest().lower() != str(info.get("sha256", "")).lower():
            raise ValueError("arquivo baixado não confere")
        # o Windows deixa renomear o exe que está rodando; o novo fica no lugar dele
        os.replace(exe, old)
        try:
            os.replace(new, exe)
        except OSError:
            os.replace(old, exe)  # desfaz se não deu
            raise
        state["ready"], state["status"] = info["version"], None
        log.info("versão %s instalada; vale na próxima abertura", info["version"])
    except Exception as e:
        log.warning("atualização não feita: %s", e)
        if state["latest"] and _ver(state["latest"]) > _ver(current):
            state["status"] = "erro"
        try:
            os.remove(new)
        except OSError:
            pass
