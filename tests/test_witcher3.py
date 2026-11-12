"""Save sintético do Witcher 3: container SNFHFZLC com blocos LZ4 e "facts" fabricados."""
import struct

import pytest

from readers import witcher3


def lz4_literais(data):
    """Bloco LZ4 só com literais (válido para o descompressor)."""
    n = len(data)
    if n < 15:
        return bytes([n << 4]) + data
    ext, rest = bytearray(), n - 15
    while rest >= 255:
        ext.append(255); rest -= 255
    ext.append(rest)
    return bytes([0xF0]) + bytes(ext) + data


def pack_sav(payload, bloco=200):
    blocos = [lz4_literais(payload[i:i + bloco]) for i in range(0, len(payload), bloco)] or [lz4_literais(b"")]
    inicio = 16 + 12 * len(blocos)
    head = b"SNFHFZLC" + struct.pack("<II", len(blocos), inicio)
    tabela = b"".join(struct.pack("<III", len(b), 0, 0) for b in blocos)
    return head + tabela + b"".join(blocos)


def fact(nome, pontos):
    """pontos: lista de (valor, tempo_em_segundos)."""
    b = nome.encode()
    out = bytes([0x80 | len(b)]) + b + b"\x00\x00" + bytes([len(pontos)]) + b"\x00"
    for v, t in pontos:
        out += struct.pack("<hff", v, float(t), -1.0)
    return out


def make_save(facts):
    return pack_sav(b"".join(fact(n, p) for n, p in facts))


def filler(n=60):
    return [("filler_%02d" % i, [(1, 10.0)]) for i in range(n)]


def hist(code, t0, n=4):
    return [("%s_passo%d" % (code, i), [(1, t0 + i * 600)]) for i in range(n)]


def test_container_roundtrip():
    payload = bytes(range(256)) * 5
    assert witcher3.decompress(pack_sav(payload)) == payload


def test_nao_e_save_do_witcher():
    with pytest.raises(ValueError, match="not_w3_save"):
        witcher3.decompress(b"XXXXXXXX" + b"\x00" * 32)


def test_poucos_facts_e_recusado():
    with pytest.raises(ValueError, match="no_facts"):
        witcher3.analyze(make_save(filler(5)))


def test_read_facts_pega_o_valor_mais_recente():
    facts = witcher3.read_facts(b"".join(fact(n, p) for n, p in [("q101_a", [(1, 100.0), (7, 500.0), (3, 300.0)])]))
    assert facts["q101_a"] == (7, 500.0)


def test_progresso_do_jogo_base():
    facts = filler() + hist("q001", 100) + hist("q002", 3000) + hist("q101", 6000)
    res = witcher3.analyze(make_save(facts))
    c = {x["key"]: x for x in res["contents"]}
    assert res["current"] == "base"
    assert c["base"]["status"] == "andamento"
    assert 0 < c["base"]["pct"] < 100
    assert c["hos"]["status"] == "nao_iniciado" and c["baw"]["status"] == "nao_iniciado"
    prologo, velen = c["base"]["segs"][0], c["base"]["segs"][1]
    assert prologo["done"] is True            # Velen já começou, então o prólogo acabou
    assert velen["done"] is False and velen["frac"] > 0
    assert res["playH"] > 0


def test_nada_iniciado():
    res = witcher3.analyze(make_save(filler()))
    assert all(c["status"] == "nao_iniciado" and c["pct"] == 0 for c in res["contents"])


def test_fatos_soltos_de_actor_nao_contam_como_inicio():
    # mortes/nocautes (actor_) aparecem soltas pelo mapa: não iniciam a missão
    facts = filler() + [("actor_q301_x%d" % i, [(1, 50.0)]) for i in range(5)]
    res = witcher3.analyze(make_save(facts))
    assert {c["key"]: c for c in res["contents"]}["base"]["status"] == "nao_iniciado"
