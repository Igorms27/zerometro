"""readers.scan(): save que existe mas não foi lido vira um aviso {id, name, erro} em vez de o jogo sumir."""
import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

import main
import readers
from readers import botw, by_achievements, horizon_fw, rv_there_yet, steam


@pytest.fixture(autouse=True)
def isolado(monkeypatch, tmp_path):
    """Nada de ler o PC de verdade: só os leitores e pastas que cada teste escolhe."""
    monkeypatch.setattr(readers, "_cache", {})
    monkeypatch.setattr(by_achievements, "GAMES", {})
    monkeypatch.setattr(steam, "stats_files", lambda appid, root=None: ({}, []))
    monkeypatch.setattr(steam, "achievements", lambda appid, root=None: {})


def fake(id_, resultado):
    import types

    def latest(cache):
        if isinstance(resultado, Exception):
            raise resultado
        return resultado
    return types.SimpleNamespace(ID=id_, NAME="Jogo " + id_, PLATFORM="PC", LABELS={}, STEAM_APPID="42", latest=latest)


def ok_game():
    return dict(current="base", contents=[dict(key="base", status="andamento")], cover="data:x")


def test_erro_de_formato_vira_aviso(monkeypatch):
    monkeypatch.setattr(readers, "SAVE_READERS", [fake("a", ValueError("x")), fake("b", ok_game())])
    out = readers.scan()
    erro = next(g for g in out if g["id"] == "a")
    assert erro["name"] == "Jogo a" and "formato" in erro["erro"] and erro["appid"] == "42"
    assert "contents" not in erro
    bom = next(g for g in out if g["id"] == "b")
    assert "erro" not in bom and bom["contents"]  # um jogo quebrado não derruba o outro


def test_sem_save_nao_gera_aviso(monkeypatch):
    monkeypatch.setattr(readers, "SAVE_READERS", [fake("a", None)])
    assert readers.scan() == []


def test_conquistas_cobrem_o_erro_do_save(monkeypatch):
    monkeypatch.setattr(readers, "SAVE_READERS", [fake("w3", ValueError("x"))])
    monkeypatch.setattr(by_achievements, "GAMES", {"1": dict(id="w3")})
    monkeypatch.setattr(by_achievements, "analyze", lambda appid: dict(
        current="base", contents=[dict(status="andamento")], cover=None, id="w3", name="W3"))
    out = readers.scan()
    assert [g["id"] for g in out] == ["w3"] and "erro" not in out[0]


def test_botw_com_save_corrompido(monkeypatch, tmp_path):
    slot = tmp_path / "save_0" / "slot0"
    slot.mkdir(parents=True)
    (slot / "game_data.sav").write_bytes(b"isto nao e um save")
    monkeypatch.setattr(botw, "save_dirs", lambda: [str(tmp_path / "save_0")])
    monkeypatch.setattr(readers, "SAVE_READERS", [botw])
    out = readers.scan()
    assert len(out) == 1 and out[0]["id"] == "botw" and "erro" in out[0]


def test_botw_sem_save_nao_gera_aviso(monkeypatch, tmp_path):
    monkeypatch.setattr(botw, "save_dirs", lambda: [str(tmp_path / "nada")])
    monkeypatch.setattr(readers, "SAVE_READERS", [botw])
    assert readers.scan() == []


def test_horizon_com_saves_ilegiveis(monkeypatch, tmp_path):
    (tmp_path / "x.dat").write_bytes(b"lixo")
    (tmp_path / "profile.dat").write_bytes(b"lixo")
    monkeypatch.setattr(horizon_fw, "save_dirs", lambda: [str(tmp_path)])
    monkeypatch.setattr(readers, "SAVE_READERS", [horizon_fw])
    out = readers.scan()
    assert len(out) == 1 and out[0]["id"] == "hfw" and "erro" in out[0]


def test_horizon_so_com_profile_dat_nao_gera_aviso(monkeypatch, tmp_path):
    (tmp_path / "profile.dat").write_bytes(b"lixo")
    monkeypatch.setattr(horizon_fw, "save_dirs", lambda: [str(tmp_path)])
    monkeypatch.setattr(readers, "SAVE_READERS", [horizon_fw])
    assert readers.scan() == []


def test_rv_com_meta_ilegivel_e_sem_conquistas(monkeypatch, tmp_path):
    (tmp_path / "s1.meta.sav").write_bytes(b"lixo")
    monkeypatch.setattr(rv_there_yet, "save_dirs", lambda: [str(tmp_path)])
    monkeypatch.setattr(readers, "SAVE_READERS", [rv_there_yet])
    out = readers.scan()
    assert len(out) == 1 and out[0]["id"] == "rvty" and "erro" in out[0]


def test_rv_ilegivel_mas_com_conquistas_ainda_le(monkeypatch, tmp_path):
    (tmp_path / "s1.meta.sav").write_bytes(b"lixo")
    monkeypatch.setattr(rv_there_yet, "save_dirs", lambda: [str(tmp_path)])
    monkeypatch.setattr(steam, "achievements", lambda appid, root=None: {"ACH_REACH_CHECKPOINT_2": {"unlocked": True, "time": 5}})
    monkeypatch.setattr(readers, "SAVE_READERS", [rv_there_yet])
    out = readers.scan()
    assert len(out) == 1 and "erro" not in out[0] and out[0]["source"] == "steam"


def test_api_scan_separa_jogos_e_erros(monkeypatch):
    monkeypatch.setattr(readers, "SAVE_READERS", [fake("a", ValueError("x")), fake("b", ok_game())])
    srv = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
        c.request("GET", "/api/scan", headers={"X-ZM-Token": main.TOKEN})
        r = c.getresponse()
        data = json.loads(r.read())
    finally:
        srv.shutdown()
        srv.server_close()
    assert r.status == 200
    assert [g["id"] for g in data["games"]] == ["b"]
    assert [e["id"] for e in data["erros"]] == ["a"] and data["erros"][0]["erro"]
