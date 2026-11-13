"""Auto-update com rollback: o exe antigo (.old) só some depois que o novo provar que funciona."""
import hashlib
import json
import os
import sys

import pytest

import updater


@pytest.fixture
def exe(tmp_path, monkeypatch):
    p = tmp_path / "Zerometro.exe"
    p.write_bytes(b"VELHO")
    monkeypatch.setattr(sys, "executable", str(p))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater, "state", {"ready": None, "latest": None, "status": None})
    monkeypatch.setattr(updater.threading, "Thread", FakeThread)  # sem esperar minutos de verdade
    FakeThread.criados.clear()
    return str(p)


class FakeThread:
    criados = []

    def __init__(self, target, args=(), daemon=None):
        self.target, self.args, self.daemon = target, args, daemon
        FakeThread.criados.append(self)

    def start(self):
        pass

    def dispara(self, monkeypatch=None, segundos=None):
        """Roda o batimento como se o app tivesse ficado aberto `segundos` (padrão: o bastante para confirmar)."""
        exe, t0 = self.args
        segundos = updater.SUCCESS_AFTER if segundos is None else segundos
        relogio = iter([t0 + min(segundos, s) for s in range(updater.ALIVE_EVERY, 10 ** 6, updater.ALIVE_EVERY)])
        mp = monkeypatch or pytest.MonkeyPatch()
        mp.setattr(updater.time, "sleep", lambda s: None)
        mp.setattr(updater.time, "time", lambda: next(relogio))
        if segundos < updater.SUCCESS_AFTER:
            # para depois de `segundos`: simula o processo morrendo ali
            parar = {"n": segundos // updater.ALIVE_EVERY}
            real = updater._write_json

            def grava(p, d):
                real(p, d)
                parar["n"] -= 1
                if parar["n"] <= 0:
                    raise SystemExit
            mp.setattr(updater, "_write_json", grava)
            try:
                self.target(*self.args)
            except SystemExit:
                pass
            mp.setattr(updater, "_write_json", real)
        else:
            self.target(*self.args)
        if monkeypatch is None:
            mp.undo()


def publica(tmp_path, versao, conteudo=b"NOVO", sha=None):
    pasta = tmp_path / "release"
    pasta.mkdir(exist_ok=True)
    (pasta / "Zerometro.exe").write_bytes(conteudo)
    (pasta / "version.json").write_text(json.dumps(
        {"version": versao, "sha256": sha or hashlib.sha256(conteudo).hexdigest()}))
    return pasta.as_uri() + "/"


def ler(p):
    with open(p, "rb") as f:
        return f.read()


def instala(tmp_path, exe, versao="0.4.0"):
    updater.run("0.3.8", publica(tmp_path, versao))
    return exe


# ---------- instalação ----------

def test_instalacao_guarda_o_antigo_e_marca_teste(tmp_path, exe):
    instala(tmp_path, exe)
    assert ler(exe) == b"NOVO" and ler(exe + ".old") == b"VELHO"
    trial = json.loads(ler(exe + ".trial"))
    assert trial["version"] == "0.4.0" and trial["fails"] == 0 and trial["running"] is False
    assert updater.state["ready"] == "0.4.0"


def test_download_que_nao_confere_nao_instala(tmp_path, exe):
    updater.run("0.3.8", publica(tmp_path, "0.4.0", sha="0" * 64))
    assert ler(exe) == b"VELHO"
    assert not os.path.exists(exe + ".trial") and not os.path.exists(exe + ".old") and not os.path.exists(exe + ".new")
    assert updater.state["status"] == "erro"


def test_falha_na_troca_desfaz_e_nao_deixa_teste(tmp_path, exe, monkeypatch):
    real = os.replace

    def replace(a, b):
        if a.endswith(".new"):
            raise OSError("travado")
        return real(a, b)
    monkeypatch.setattr(updater.os, "replace", replace)
    updater.run("0.3.8", publica(tmp_path, "0.4.0"))
    assert ler(exe) == b"VELHO"
    assert not os.path.exists(exe + ".trial")


# ---------- versão nova funciona ----------

def test_abrir_a_versao_nova_nao_apaga_o_antigo_ainda(tmp_path, exe):
    instala(tmp_path, exe)
    assert updater.startup("0.4.0", relaunch=False) is False
    assert os.path.exists(exe + ".old")  # ainda em teste
    assert json.loads(ler(exe + ".trial"))["running"] is True
    assert len(FakeThread.criados) == 1 and FakeThread.criados[0].target == updater._heartbeat


def test_rodar_alguns_minutos_confirma_e_apaga_o_antigo(tmp_path, exe):
    instala(tmp_path, exe)
    updater.startup("0.4.0", relaunch=False)
    FakeThread.criados[0].dispara()
    assert not os.path.exists(exe + ".old") and not os.path.exists(exe + ".trial")
    assert ler(exe) == b"NOVO"


def test_fechar_normal_depois_de_uns_segundos_confirma(tmp_path, exe):
    instala(tmp_path, exe)
    updater.startup("0.4.0", relaunch=False)
    updater.finish(updater.CLEAN_MIN_UPTIME + 1)
    assert not os.path.exists(exe + ".old") and not os.path.exists(exe + ".trial")


def test_fechar_normal_rapido_nao_confirma_nem_conta_como_queda(tmp_path, exe):
    instala(tmp_path, exe)
    for _ in range(4):  # abre e fecha de cara várias vezes: não é queda
        assert updater.startup("0.4.0", relaunch=False) is False
        updater.finish(2)
    assert ler(exe) == b"NOVO" and os.path.exists(exe + ".old")
    trial = json.loads(ler(exe + ".trial"))
    assert trial["fails"] == 0 and trial["running"] is False


# ---------- versão nova falha ----------

def test_duas_quedas_seguidas_voltam_para_a_antiga(tmp_path, exe):
    instala(tmp_path, exe)
    assert updater.startup("0.4.0", relaunch=False) is False  # 1ª abertura, caiu (sem finish)
    assert updater.startup("0.4.0", relaunch=False) is False  # 2ª abertura: viu 1 queda, ainda tenta
    assert json.loads(ler(exe + ".trial"))["fails"] == 1
    assert updater.startup("0.4.0", relaunch=False) is True   # 3ª: viu 2 quedas, volta
    assert ler(exe) == b"VELHO"
    assert ler(exe + ".bad") == b"NOVO"
    assert not os.path.exists(exe + ".trial") and not os.path.exists(exe + ".old")
    assert json.loads(ler(exe + ".skip")) == {"version": "0.4.0"}


def test_relanca_a_versao_antiga_ao_voltar(tmp_path, exe, monkeypatch):
    chamadas = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda *a, **k: chamadas.append((a, k)))
    instala(tmp_path, exe)
    for _ in range(3):
        voltou = updater.startup("0.4.0")
    assert voltou is True and len(chamadas) == 1
    assert chamadas[0][0][0][0] == exe
    assert chamadas[0][1]["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"


def test_queda_seguida_de_sucesso_zera_a_conta(tmp_path, exe):
    instala(tmp_path, exe)
    updater.startup("0.4.0", relaunch=False)   # caiu
    updater.startup("0.4.0", relaunch=False)   # abriu de novo (1 queda registrada)
    updater.finish(60)                          # e funcionou
    assert not os.path.exists(exe + ".trial") and not os.path.exists(exe + ".old")


def test_sem_exe_antigo_nao_da_para_voltar_e_segue(tmp_path, exe):
    instala(tmp_path, exe)
    os.remove(exe + ".old")
    for _ in range(3):
        assert updater.startup("0.4.0", relaunch=False) is False
    assert ler(exe) == b"NOVO" and not os.path.exists(exe + ".trial")


def test_versao_ruim_nao_e_instalada_de_novo(tmp_path, exe):
    instala(tmp_path, exe)
    for _ in range(3):
        updater.startup("0.4.0", relaunch=False)
    assert ler(exe) == b"VELHO"
    # a versão antiga volta a rodar e confere o GitHub: a 0.4.0 continua publicada, mas é pulada
    updater.state.update(ready=None, latest=None, status=None)
    updater.run("0.3.8", publica(tmp_path, "0.4.0"))
    assert ler(exe) == b"VELHO" and updater.state["ready"] is None
    # uma versão mais nova que a ruim é instalada normalmente
    updater.run("0.3.8", publica(tmp_path, "0.4.1", conteudo=b"NOVO2"))
    assert ler(exe) == b"NOVO2" and updater.state["ready"] == "0.4.1"
    assert not os.path.exists(exe + ".skip")


# ---------- limpeza ----------

def test_sem_teste_em_andamento_limpa_as_sobras_como_antes(tmp_path, exe):
    for ext in (".old", ".new", ".bad"):
        (tmp_path / ("Zerometro.exe" + ext)).write_bytes(b"x")
    assert updater.startup("0.3.8", relaunch=False) is False
    assert sorted(os.listdir(tmp_path)) == ["Zerometro.exe"]


def test_marcador_de_outra_versao_e_descartado(tmp_path, exe):
    instala(tmp_path, exe)  # marcador da 0.4.0
    assert updater.startup("0.3.8", relaunch=False) is False  # quem abriu é outra versão
    assert not os.path.exists(exe + ".trial") and not os.path.exists(exe + ".old")


def test_finish_sem_teste_nao_faz_nada(tmp_path, exe):
    updater.finish(100)
    assert os.listdir(tmp_path) == ["Zerometro.exe"]


def test_rodando_pelo_python_nao_mexe_em_nada(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    py = tmp_path / "python.exe"
    py.write_bytes(b"py")
    (tmp_path / "python.exe.old").write_bytes(b"x")
    monkeypatch.setattr(sys, "executable", str(py))
    assert updater.startup("0.3.8") is False
    assert sorted(os.listdir(tmp_path)) == ["python.exe", "python.exe.old"]


# ---------- fechado à força depois de rodar um tempo não é defeito ----------

def test_morrer_depois_de_rodar_um_tempo_nao_conta_como_queda(tmp_path, exe, monkeypatch):
    instala(tmp_path, exe)
    for _ in range(updater.MAX_FAILS + 1):  # PC desligado várias vezes, sempre depois de ~1 minuto
        assert updater.startup("0.4.0", relaunch=False) is False
        if not os.path.exists(exe + ".trial"):
            break
        FakeThread.criados[-1].dispara(monkeypatch, segundos=60)
    assert ler(exe) == b"NOVO"  # não voltou para a antiga
    assert not os.path.exists(exe + ".skip")


def test_cair_logo_ao_abrir_ainda_volta_para_a_antiga(tmp_path, exe):
    instala(tmp_path, exe)
    for _ in range(updater.MAX_FAILS):
        assert updater.startup("0.4.0", relaunch=False) is False  # e "cai" sem anotar tempo nenhum
    assert updater.startup("0.4.0", relaunch=False) is True
    assert ler(exe) == b"VELHO"
