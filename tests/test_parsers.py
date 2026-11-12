import struct

import pytest

from readers import steam
from readers.witcher3 import lz4_block


def test_lz4_so_literais():
    out = bytearray()
    lz4_block(bytes([0x30]) + b"abc", out)
    assert bytes(out) == b"abc"


def test_lz4_copia_com_sobreposicao():
    # literais "abc", copia 6 bytes a partir de 3 atras (sobrepoe), token final vazio
    out = bytearray()
    lz4_block(bytes([0x32]) + b"abc" + bytes([3, 0]) + bytes([0x00]), out)
    assert bytes(out) == b"abcabcabc"


def test_lz4_copia_sem_sobreposicao():
    # "abcd" + copia de 4 bytes 4 atras
    out = bytearray()
    lz4_block(bytes([0x40]) + b"abcd" + bytes([4, 0]) + bytes([0x00]), out)
    assert bytes(out) == b"abcdabcd"


def test_lz4_literais_longos_com_extensao():
    lit = b"x" * 300  # 15 + 255 + 30
    out = bytearray()
    lz4_block(bytes([0xF0, 255, 30]) + lit, out)
    assert bytes(out) == lit


def _kv(t, key, payload):
    return bytes([t]) + key.encode() + b"\0" + payload


def test_kv_parse_tipos_e_aninhamento():
    data = (
        _kv(0x00, "raiz", b"")
        + _kv(0x01, "nome", b"valor\0")
        + _kv(0x02, "inteiro", struct.pack("<i", -7))
        + _kv(0x03, "real", struct.pack("<f", 1.5))
        + _kv(0x07, "grande", struct.pack("<q", 2 ** 40))
        + b"\x08"   # fecha "raiz"
        + b"\x08"   # fecha o nivel de cima
    )
    out, pos = steam.kv_parse(data)
    assert out == {"raiz": {"nome": "valor", "inteiro": -7, "real": 1.5, "grande": 2 ** 40}}
    assert pos == len(data)


def test_kv_parse_vazio():
    assert steam.kv_parse(b"")[0] == {}


def test_kv_parse_tipo_desconhecido_da_erro():
    with pytest.raises(ValueError):
        steam.kv_parse(_kv(0x7E, "x", b"\0\0\0\0"))
