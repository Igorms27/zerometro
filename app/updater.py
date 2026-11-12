"""Atualização automática: ao abrir, confere no GitHub se tem versão nova e troca o próprio exe.

A versão nova passa a valer na próxima vez que o app for aberto.
Cada versão publicada tem dois arquivos: Zerometro.exe e version.json ({"version", "sha256"}).

Volta atrás se a versão nova não funcionar: o exe antigo (.old) só é apagado depois que a nova
provar que funciona (rodou por alguns minutos ou fechou normalmente depois de uns segundos de uso).
Se ela cair duas vezes seguidas, a terceira abertura devolve o exe antigo e não tenta essa versão de novo.
Limite: se o exe novo nem chega a executar o Python (ex.: falta uma DLL), ele não consegue se desfazer sozinho.
"""
import hashlib
import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.request

log = logging.getLogger("zerometro")
state = {"ready": None, "latest": None, "status": None}
# ready: versão já baixada e instalada, esperando o app reabrir
# latest: versão mais nova publicada; status: None, "baixando" ou "erro"
CHECK_EVERY = 3600  # com o app aberto, confere de novo a cada hora
SUCCESS_AFTER = 180  # segundos rodando bem até a versão nova ser dada como boa
CLEAN_MIN_UPTIME = 20  # fechar normalmente depois disso também vale como "funcionou"
MAX_FAILS = 2  # aberturas seguidas que caíram antes de voltar para a versão antiga


def _ver(v):
    return tuple(int(x) for x in str(v).strip().lstrip("v").split(".") if x.isdigit())


def _get(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "Zerometro-updater"})
    return urllib.request.urlopen(req, timeout=timeout)


def _rm(p):
    try:
        os.remove(p)
    except OSError:
        pass


def _trial_path(exe):
    return exe + ".trial"  # existe enquanto a versão nova ainda está "em teste"


def _skip_path(exe):
    return exe + ".skip"  # versão que deu problema e não deve ser instalada de novo


def _read_json(p):
    try:
        with open(p, encoding="utf-8-sig") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _write_json(p, d):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(tmp, p)


def confirm(exe=None):
    """A versão nova funcionou: agora o exe antigo pode ser apagado."""
    exe = exe or sys.executable
    if os.path.exists(_trial_path(exe)):
        _rm(_trial_path(exe))
        _rm(exe + ".old")
        log.info("versão nova confirmada; exe antigo apagado")


def rollback(exe=None):
    """Devolve o exe antigo ao lugar do atual e anota a versão ruim para não instalar de novo."""
    exe = exe or sys.executable
    old, bad = exe + ".old", exe + ".bad"
    trial = _read_json(_trial_path(exe)) or {}
    if not os.path.exists(old):
        return False
    _rm(bad)
    os.replace(exe, bad)  # o Windows deixa renomear o exe que está rodando
    try:
        os.replace(old, exe)
    except OSError:
        os.replace(bad, exe)
        raise
    try:
        _write_json(_skip_path(exe), {"version": trial.get("version")})
    except OSError:
        pass
    _rm(_trial_path(exe))
    return True


def startup(current, exe=None, relaunch=True):
    """Chamar ao abrir o app, antes de subir o servidor. Devolve True se voltou para a versão antiga
    e abriu ela: quem chamou deve encerrar."""
    if exe is None:
        if not getattr(sys, "frozen", False):
            return False  # rodando pelo Python: sys.executable é o python.exe, não mexer
        exe = sys.executable
    _rm(exe + ".new")
    _rm(exe + ".bad")  # sobra de um rollback anterior
    trial = _read_json(_trial_path(exe))
    if not trial:
        _rm(exe + ".old")  # sem teste em andamento (ou atualização feita por versão antiga do app)
        return False
    if _ver(trial.get("version")) != _ver(current):
        # marcador de outra versão (ex.: este já é o antigo restaurado): não vale mais
        _rm(_trial_path(exe))
        _rm(exe + ".old")
        return False
    fails = int(trial.get("fails", 0)) + (1 if trial.get("running") else 0)  # "running" sobrando = a abertura anterior caiu
    if fails >= MAX_FAILS:
        log.error("versão %s caiu %d vezes seguidas; voltando para a anterior", current, fails)
        try:
            ok = rollback(exe)
        except OSError as e:
            log.error("não consegui voltar para a versão anterior: %s", e)
            ok = False
        if ok:
            if relaunch:
                env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
                subprocess.Popen([exe] + sys.argv[1:], env=env, close_fds=True,
                                 creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
            return True
        _rm(_trial_path(exe))  # sem versão antiga para voltar: deixa seguir
        return False
    trial.update(fails=fails, running=True)
    try:
        _write_json(_trial_path(exe), trial)
    except OSError as e:
        log.warning("não consegui anotar o teste da versão nova: %s", e)
    t = threading.Timer(SUCCESS_AFTER, confirm, args=(exe,))
    t.daemon = True
    t.start()
    return False


def finish(uptime, exe=None):
    """Chamar quando o app fecha normalmente. Fechar normal não é queda; depois de uns segundos de uso vale como sucesso."""
    exe = exe or sys.executable
    trial = _read_json(_trial_path(exe))
    if not trial:
        return
    if uptime >= CLEAN_MIN_UPTIME:
        confirm(exe)
    else:
        trial["running"] = False
        try:
            _write_json(_trial_path(exe), trial)
        except OSError:
            pass


def loop(current, repo):
    test_base = os.environ.get("ZM_UPDATE_BASE")  # só para teste
    if not (repo or test_base):
        return
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
        skipped = (_read_json(_skip_path(exe)) or {}).get("version")
        if skipped and _ver(info["version"]) <= _ver(skipped):
            log.info("versão %s já deu problema neste PC; esperando uma mais nova", info["version"])
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
        try:
            _write_json(_trial_path(exe), {"version": info["version"], "from": current, "fails": 0, "running": False})
        except OSError as e:
            log.warning("sem proteção de rollback para esta atualização: %s", e)
        os.replace(exe, old)
        try:
            os.replace(new, exe)
        except OSError:
            os.replace(old, exe)  # desfaz se não deu
            _rm(_trial_path(exe))
            raise
        _rm(_skip_path(exe))
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
