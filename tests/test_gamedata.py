"""games.json: validação, cache local, fallback embutido e atualização remota."""
import copy
import json

import pytest

from readers import by_achievements, gamedata

GOOD = {"id": "g1", "name": "Jogo", "platform": "PC · Steam", "labels": {"base": "História"},
        "contents": [{"key": "base", "segs": [{"title": "A", "h": 2, "ach": ["X"]}, {"title": "B", "h": 3.5, "ach": ["Y", "Z"]}]}]}


def doc(**games):
    return {"schema": 1, "games": games}


@pytest.fixture(autouse=True)
def pasta(monkeypatch, tmp_path):
    monkeypatch.setattr(gamedata.paths, "APP_DIR", str(tmp_path))
    return tmp_path


def test_jogo_valido_vira_formato_interno():
    out = gamedata.validate(doc(**{"123": GOOD}))
    g = out["123"]
    assert g["id"] == "g1" and g["contents"][0][0] == "base" and g["contents"][0][1][1]["ach"] == ["Y", "Z"]


def mut(f):
    g = copy.deepcopy(GOOD)
    f(g)
    return g


@pytest.mark.parametrize("ruim", [
    mut(lambda g: g.update(id="Maiúscula!")),
    mut(lambda g: g.update(name="")),
    mut(lambda g: g.update(name="x" * 200)),
    mut(lambda g: g.update(labels={})),
    mut(lambda g: g.update(contents=[])),
    mut(lambda g: g["contents"][0].update(segs=[])),
    mut(lambda g: g["contents"][0]["segs"][0].update(h=-1)),
    mut(lambda g: g["contents"][0]["segs"][0].update(h="2")),
    mut(lambda g: g["contents"][0]["segs"][0].update(h=True)),
    mut(lambda g: g["contents"][0]["segs"][0].update(h=9999)),
    mut(lambda g: g["contents"][0]["segs"][0].update(ach=[])),
    mut(lambda g: g["contents"][0]["segs"][0].update(ach=["tem espaço"])),
    mut(lambda g: g["contents"][0]["segs"][0].update(ach="X")),
    mut(lambda g: g["contents"][0]["segs"].extend([GOOD["contents"][0]["segs"][0]] * 100)),
    "texto", None, 5, [],
])
def test_entrada_invalida_e_ignorada_sem_derrubar_as_outras(ruim):
    out = gamedata.validate(doc(**{"1": ruim, "2": mut(lambda g: g.update(id="g2"))}))
    assert list(out) == ["2"]


def test_appid_invalido_e_id_repetido_ignorados():
    out = gamedata.validate(doc(**{"abc": GOOD, "1": GOOD, "2": GOOD}))
    assert list(out) == ["1"]  # "2" repete o id g1


@pytest.mark.parametrize("d", [None, [], "x", {}, {"schema": 2, "games": {}}, {"schema": "1", "games": {}},
                               {"schema": True, "games": {}}, {"schema": 1, "games": []}])
def test_documento_invalido_ou_de_versao_futura(d):
    assert gamedata.validate(d) == {}


def test_arquivo_embutido_do_repositorio_e_valido():
    out = gamedata._read(gamedata.embedded_path())
    assert "292030" in out and out["292030"]["id"] == "w3"
    assert len(out["292030"]["contents"][0][1]) == 6


def test_load_usa_cache_por_cima_do_embutido(pasta):
    novo = copy.deepcopy(GOOD)
    novo["id"] = "outro"
    (pasta / "games.json").write_text(json.dumps(doc(**{"999": novo, "292030": mut(lambda g: g.update(name="Witcher novo", id="w3"))})), encoding="utf-8")
    out = gamedata.load()
    assert out["999"]["id"] == "outro" and out["292030"]["name"] == "Witcher novo"


def test_cache_estragado_cai_no_embutido(pasta):
    (pasta / "games.json").write_text("{isto não é json", encoding="utf-8")
    assert "292030" in gamedata.load()


def test_cache_grande_demais_e_ignorado(pasta):
    (pasta / "games.json").write_bytes(b" " * (gamedata.MAX_BYTES + 1))
    assert "292030" in gamedata.load()


class Resp:
    def __init__(self, raw):
        self.raw = raw

    def read(self, n=-1):
        return self.raw if n < 0 else self.raw[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def serve(monkeypatch, raw):
    visto = {}

    def fake(req, timeout):
        visto["timeout"], visto["ua"] = timeout, req.get_header("User-agent")
        if isinstance(raw, Exception):
            raise raw
        return Resp(raw)
    monkeypatch.setattr(gamedata.urllib.request, "urlopen", fake)
    return visto


def test_refresh_guarda_no_cache_e_junta_com_embutido(monkeypatch, pasta):
    novo = copy.deepcopy(GOOD)
    visto = serve(monkeypatch, json.dumps(doc(**{"777": novo})).encode())
    out = gamedata.refresh()
    assert "777" in out and "292030" in out  # o embutido continua
    assert visto["timeout"] == gamedata.TIMEOUT and visto["ua"] == "Zerometro"
    assert "777" in gamedata._read(str(pasta / "games.json"))


@pytest.mark.parametrize("raw", [OSError("sem rede"), TimeoutError("lento"), b"<html>404</html>", b"[]",
                                 b'{"schema": 1, "games": {"1": 5}}', b"x" * (gamedata.MAX_BYTES + 10)])
def test_refresh_com_falha_nao_muda_nada(monkeypatch, pasta, raw):
    serve(monkeypatch, raw)
    assert gamedata.refresh() is None
    assert not (pasta / "games.json").exists()


def test_by_achievements_refresh_troca_o_mapa_na_memoria(monkeypatch):
    monkeypatch.setattr(by_achievements, "GAMES", {"1": "velho"})
    monkeypatch.setattr(gamedata, "refresh", lambda: {"2": "novo"})
    assert by_achievements.refresh() is True and by_achievements.GAMES == {"2": "novo"}
    monkeypatch.setattr(gamedata, "refresh", lambda: None)
    assert by_achievements.refresh() is False and by_achievements.GAMES == {"2": "novo"}


def test_analyze_do_witcher_continua_igual(monkeypatch):
    ach = {a: {"unlocked": a == "NECROMANCER", "time": 100, "name": a, "desc": ""} for a in
           ["LILAC", "FAMILY_COUNSELOR", "FRIEND_IN_NEED", "NECROMANCER", "SOMETHING_MORE", "THE_KING", "PASSED_THE_TRIAL"]}
    monkeypatch.setattr(by_achievements.steam, "achievements", lambda appid, root=None: ach)
    monkeypatch.setattr(by_achievements, "GAMES", gamedata.load())
    r = by_achievements.analyze("292030")
    c = r["contents"][0]
    assert [s["done"] for s in c["segs"]] == [True, True, True, True, False, False]
    assert c["total"] == 51.5 and c["status"] == "andamento" and c["left"] == 14.5


def test_refresh_durante_a_leitura_nao_estoura_runtimeerror(monkeypatch):
    """Antes, refresh fazia clear()+update() no mesmo dict que o scan percorria."""
    import threading
    velho = {str(i): {"id": "g%d" % i} for i in range(300)}
    monkeypatch.setattr(by_achievements, "GAMES", velho)
    novo = {str(i): {"id": "n%d" % i} for i in range(300, 600)}
    monkeypatch.setattr(gamedata, "refresh", lambda: dict(novo))
    erros, parar = [], threading.Event()

    def ler():
        while not parar.is_set():
            try:
                for _ in list(by_achievements.GAMES.items()):
                    pass
                for _ in by_achievements.GAMES.items():
                    pass
            except RuntimeError as e:  # "dictionary changed size during iteration"
                erros.append(e)
    t = threading.Thread(target=ler)
    t.start()
    for _ in range(300):
        by_achievements.refresh()
    parar.set()
    t.join()
    assert not erros
    assert by_achievements.GAMES == novo and len(velho) == 300  # o dict antigo nunca é mexido


def test_texto_com_quebra_de_linha_no_fim_nao_passa_na_validacao():
    g = copy.deepcopy(GOOD)
    g["id"] = "g1\n"
    assert gamedata._game(g) is None
    g = copy.deepcopy(GOOD)
    g["contents"][0]["key"] = "base\n"
    assert gamedata._game(g) is None
    g = copy.deepcopy(GOOD)
    g["contents"][0]["segs"][0]["ach"] = ["X\n"]
    assert gamedata._game(g) is None
    assert gamedata.validate(doc(**{"777\n": copy.deepcopy(GOOD)})) == {}
    assert gamedata.validate(doc(**{"٣٣٣": copy.deepcopy(GOOD)})) == {}  # dígitos não ASCII


@pytest.mark.parametrize("valor", [5, None, ["g1"], {"a": 1}])
def test_id_e_key_precisam_ser_texto(valor):
    g = copy.deepcopy(GOOD)
    g["id"] = valor
    assert gamedata._game(g) is None
    g = copy.deepcopy(GOOD)
    g["contents"][0]["key"] = valor
    assert gamedata._game(g) is None


def test_download_pode_ser_desligado_nas_configuracoes(monkeypatch, pasta):
    visto = serve(monkeypatch, json.dumps(doc(**{"777": copy.deepcopy(GOOD)})).encode())
    (pasta / "settings.json").write_text('{"baixar_mapa": false}', encoding="utf-8")
    assert gamedata.download_enabled() is False
    assert gamedata.refresh() is None
    assert visto == {} and not (pasta / "games.json").exists()  # nem tentou a rede
    (pasta / "settings.json").write_text('{"baixar_mapa": true}', encoding="utf-8")
    assert gamedata.download_enabled() is True and "777" in gamedata.refresh()
    (pasta / "settings.json").write_text('[1]', encoding="utf-8")
    assert gamedata.download_enabled() is True
