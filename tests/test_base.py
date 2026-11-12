"""Helpers comuns dos leitores (readers/base.py)."""
import os
import time
import types

from readers import base


def touch(path, mtime=None, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    if mtime:
        os.utime(path, (mtime, mtime))
    return path


def test_find_latest_pega_o_mais_novo(tmp_path):
    touch(str(tmp_path / "a" / "um.sav"), 1000)
    novo = touch(str(tmp_path / "b" / "dois.sav"), 2000)
    touch(str(tmp_path / "b" / "tres.txt"), 3000)
    path, mtime = base.find_latest([str(tmp_path / "a"), str(tmp_path / "b")], "*.sav")
    assert path == novo and mtime == 2000


def test_find_latest_ignora_pasta_que_nao_existe_e_vazio(tmp_path):
    assert base.find_latest([str(tmp_path / "nao_existe"), "", None], "*.sav") is None
    assert base.find_files([str(tmp_path)], "*.sav") == []


def test_find_files_exclude_sem_maiusculas(tmp_path):
    touch(str(tmp_path / "Profile.DAT"))
    ok = touch(str(tmp_path / "save1.dat"))
    assert base.find_files([str(tmp_path)], "*.dat", exclude=["profile.dat"]) == [ok]


def test_find_files_com_subpasta_no_padrao(tmp_path):
    slot = touch(str(tmp_path / "slot0" / "game_data.sav"))
    assert base.find_files([str(tmp_path)], os.path.join("*", "game_data.sav")) == [slot]


def test_cached_calcula_uma_vez():
    cache, calls = {}, []

    def compute():
        calls.append(1)
        return {"v": 1}
    assert base.cached(cache, ("g", 1), compute) == {"v": 1}
    assert base.cached(cache, ("g", 1), compute) == {"v": 1}
    assert len(calls) == 1


def test_cached_mantem_so_a_entrada_mais_nova_de_cada_jogo():
    cache = {}
    base.cached(cache, ("g", 1), lambda: "velho")
    base.cached(cache, ("outro", 1), lambda: "outro jogo")
    base.cached(cache, ("g", 2), lambda: "novo")
    assert set(cache) == {("g", 2), ("outro", 1)}


def test_cached_nao_guarda_none():
    cache, calls = {}, []

    def compute():
        calls.append(1)
        return None
    assert base.cached(cache, ("g", 1), compute) is None
    assert base.cached(cache, ("g", 1), compute) is None
    assert len(calls) == 2 and cache == {}


def test_cached_erro_nao_fica_no_cache():
    cache = {}

    def quebra():
        raise ValueError("x")
    try:
        base.cached(cache, ("g", 1), quebra)
    except ValueError:
        pass
    assert cache == {}


def test_cover_from_png_jpg_e_limites(tmp_path):
    png = touch(str(tmp_path / "a.png"), data=b"\x89PNG")
    jpg = touch(str(tmp_path / "a.jpg"), data=b"\xff\xd8")
    grande = touch(str(tmp_path / "grande.png"), data=b"0" * 200000)
    assert base.cover_from(png).startswith("data:image/png;base64,")
    assert base.cover_from(jpg).startswith("data:image/jpeg;base64,")
    assert base.cover_from(grande) is None
    assert base.cover_from(str(tmp_path / "nao_existe.png")) is None
    assert base.cover_from(touch(str(tmp_path / "x.txt"))) is None


def segs():
    return [dict(title="A", h=2, frac=1.0, done=True), dict(title="B", h=2, frac=0.5, done=False),
            dict(title="C", h=4, frac=0.0, done=False)]


def test_build_content_calcula_progresso():
    c = base.build_content("base", segs())
    assert c["key"] == "base" and c["status"] == "andamento"
    assert c["total"] == 8 and c["left"] == 5.0 and c["pct"] == 37.5
    assert c["pace"] == 1.0 and c["paceKnown"] is False
    assert [s["done"] for s in c["segs"]] == [True, False, False]
    assert set(c["segs"][0]) == {"title", "h", "frac", "done"}


def test_build_content_estados():
    nada = [dict(title="A", h=1, frac=0.0)]
    tudo = [dict(title="A", h=1, frac=1.0)]
    assert base.build_content("k", nada)["status"] == "nao_iniciado"
    z = base.build_content("k", tudo)
    assert z["status"] == "zerado" and z["pct"] == 100.0 and z["left"] == 0
    # regra própria do leitor sobrescreve a padrão
    assert base.build_content("k", nada, finished=True)["status"] == "zerado"
    assert base.build_content("k", nada, started=True)["status"] == "andamento"


def test_build_content_pace_e_extras():
    c = base.build_content("k", segs(), pace=1.5, pace_known=None, lastT=7)
    assert c["pace"] == 1.5 and "paceKnown" not in c and c["lastT"] == 7


def test_build_content_arredonda_horas():
    c = base.build_content("k", [dict(title="A", h=1 / 3, frac=1 / 3), dict(title="B", h=1 / 3, frac=0)], ndigits=2)
    assert c["total"] == 0.67 and c["segs"][0]["h"] == 0.33 and c["segs"][0]["frac"] == 0.33


def test_error_entry_mensagens_por_tipo():
    mod = types.SimpleNamespace(ID="g", NAME="Jogo", PLATFORM="PC", STEAM_APPID="123")
    e = base.error_entry(mod, ValueError("x"))
    assert (e["id"], e["name"], e["platform"], e["appid"]) == ("g", "Jogo", "PC", "123")
    assert "formato" in e["erro"]
    assert "abrir" in base.error_entry(mod, PermissionError("x"))["erro"]
    assert "erro ao ler" in base.error_entry(mod, KeyError("x"))["erro"]
    assert "contents" not in e
    assert base.error_entry(types.SimpleNamespace(ID="g", NAME="J", PLATFORM="P"), ValueError())["appid"] is None
