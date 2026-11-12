"""Save sintético do Zelda BotW (flags game_data.sav), sem dados de ninguém."""
import struct
import zlib

import pytest

from readers import botw


def make_save(flags):
    """flags: {nome: valor}. Formato: cabeçalho de 12 bytes, pares (crc32, valor), rodapé FFFFFFFF."""
    body = b"".join(struct.pack("<II", zlib.crc32(n.encode()) & 0xFFFFFFFF, v) for n, v in flags.items())
    return b"\x00\x00\x00\x00" + b"\xff\xff\xff\xff" + b"\x00\x00\x00\x00" + body + b"\xff\xff\xff\xff"


def by_key(res):
    return {c["key"]: c for c in res["contents"]}


def test_save_recusado_se_nao_for_botw():
    with pytest.raises(ValueError):
        botw.botw_analyze(b"isto nao e um save de jogo")
    with pytest.raises(ValueError):
        botw.botw_flags(b"\x00" * 32)


def test_flags_lidas():
    vals = botw.botw_flags(make_save({"Alguma_Flag": 5}))
    assert vals[zlib.crc32(b"Alguma_Flag") & 0xFFFFFFFF] == 5


def test_save_novo_nao_iniciado():
    res = botw.botw_analyze(make_save({"PlayReport_PlayTime": 0}))
    c = by_key(res)
    assert c["zbase"]["status"] == "nao_iniciado" and c["zbase"]["pct"] == 0
    assert res["playH"] == 0


def test_progresso_parcial():
    res = botw.botw_analyze(make_save({
        "PlayReport_PlayTime": 36000,          # 10 h
        "IsGet_PlayerStole2": 1,               # Planalto Isolado (3 h) feito
        "Find_Impa_Finish": 1,                 # Encontre a Impa (2 h) feito
        "Fire_Relic_Activated": 1,             # Rudania começou
    }))
    z = by_key(res)["zbase"]
    assert res["playH"] == 10.0
    assert z["status"] == "andamento"
    assert [s["done"] for s in z["segs"]][:2] == [True, True]
    assert 0 < z["pct"] < 100
    assert z["total"] == sum(s["h"] for s in z["segs"])
    assert res["current"] == "zbase"


def test_valor_ffffffff_conta_como_desligado():
    res = botw.botw_analyze(make_save({"IsGet_PlayerStole2": 0xFFFFFFFF}))
    assert by_key(res)["zbase"]["segs"][0]["done"] is False


def test_tudo_feito_esta_zerado():
    flags = {"PlayReport_PlayTime": 3600}
    for _key, defs in botw.BOTW_CONTENT:
        for d in defs:
            flags[d["done"][0]] = 1
    res = botw.botw_analyze(make_save(flags))
    for c in res["contents"]:
        assert c["status"] == "zerado" and c["pct"] == 100.0 and c["left"] == 0
