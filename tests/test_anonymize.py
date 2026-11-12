"""Relatório anônimo: caminhos, ID Steam e log sem dados pessoais, saves intactos."""
import json
import os
import zipfile

import pytest

import anonymize
import report
from readers import steam

HOME = r"C:\Users\MariaSilva"
ID64 = "76561198012345678"
ACC = str(int(ID64) - anonymize.STEAM64_BASE)  # número curto das pastas userdata


@pytest.fixture
def an():
    return anonymize.Anon(home=HOME, account_ids=[ACC], salt="s", computer="PC-DA-MARIA")


def test_caminho_do_usuario_vira_userprofile(an):
    assert an.path(HOME + r"\Documents\Jogo\save.dat") == r"%USERPROFILE%\Documents\Jogo\save.dat"
    assert an.path("c:\\users\\mariasilva\\AppData") == r"%USERPROFILE%\AppData"
    assert an.path("C:/Users/MariaSilva/Saved Games/x") == "%USERPROFILE%/Saved Games/x"


def test_outro_usuario_do_windows_tambem_e_escondido(an):
    assert an.path(r"D:\Users\Joao\Saves") == r"D:\Users\<usuario>\Saves"
    assert an.path(r"C:\Users\Public\Documents") == r"C:\Users\<usuario>\Documents"


def test_pastas_sem_usuario_ficam_iguais(an):
    p = r"D:\Games\Steam\steamapps\common\Jogo"
    assert an.path(p) == p
    assert an.path(r"C:\Users\MariaSilvaOutra\x") == r"C:\Users\<usuario>\x"  # não confunde com prefixo parecido


def test_id_steam_nos_dois_formatos_e_consistente(an):
    a = an.path(r"C:\Steam\userdata\%s\1234\remote" % ACC)
    b = an.steam("id " + ID64)
    assert ACC not in a and ID64 not in b
    tag = a.split("STEAMID_")[1][:6]
    assert b == "id STEAMID_" + tag  # a mesma conta dá o mesmo código nas duas formas
    assert "1234" in a  # o appid não é mexido
    assert an.seen == {ACC}


def test_numero_parecido_nao_e_trocado(an):
    s = "tempo 1%s9 e %s0" % (ACC, ACC)  # ambos têm dígitos colados no ID
    assert ("1%s9" % ACC) in an.steam(s)  # número maior que contém o ID não é um ID


def test_sal_diferente_muda_o_codigo():
    a = anonymize.Anon(home=HOME, account_ids=[ACC], salt="um")
    b = anonymize.Anon(home=HOME, account_ids=[ACC], salt="dois")
    assert a.steam(ID64) != b.steam(ID64)


def test_log_tira_token_email_ip_usuario_e_pc(an):
    linha = ("2026-11-12 INFO abrindo http://127.0.0.1:5000/?t=abc_DEF-123 em %s\\x por maria@exemplo.com "
             "de 192.168.0.12 (MariaSilva) no PC-DA-MARIA token=xyz secret: 123 conta %s" % (HOME, ID64))
    out = an.log_line(linha)
    for vazou in ("abc_DEF", HOME, "maria@", "192.168", "MariaSilva", "PC-DA-MARIA", "xyz", ID64):
        assert vazou not in out
    assert "127.0.0.1" in out  # a porta local é inofensiva e ajuda a ler o log
    assert "%USERPROFILE%" in out and "<ip>" in out and "<email>" in out and "<pc>" in out


def test_log_limita_linhas(an):
    txt = "\n".join("linha %d" % i for i in range(5000))
    out = an.log(txt, max_lines=100).splitlines()
    assert len(out) == 100 and out[-1] == "linha 4999"


def test_texto_troca_id_e_binario_passa_intacto(an):
    t, mudou = an.file_content("perfil.json", json.dumps({"steam": ID64}).encode())
    assert mudou and ID64.encode() not in t and json.loads(t)["steam"].startswith("STEAMID_")
    raw = b"\x00\x01" + ID64.encode() + b"\xff"
    b, mudou = an.file_content("slot.sav", raw)
    assert b == raw and not mudou  # binário não é mexido
    b, mudou = an.file_content("x.json", raw)  # tem byte zero: tratado como binário
    assert b == raw and not mudou
    assert an.has_id(raw) and not an.has_id(b"\x00\x01\x02")
    assert an.file_content("a.txt", b"\xff\xfe\xfa") == (b"\xff\xfe\xfa", False)  # não é UTF-8


def test_head_hex_zera_o_id_com_mesmo_tamanho(an):
    raw = b"GVAS" + ID64.encode() + b"\x01\x02"
    h = an.head_hex(raw)
    assert len(h) == len(raw.hex()) and ID64.encode().hex() not in h
    assert h.startswith(b"GVAS".hex()) and h.endswith("0102")


def test_steam_accounts(tmp_path):
    ud = tmp_path / "userdata"
    for n in (ACC, "0", "anonymous"):
        (ud / n).mkdir(parents=True)
    assert anonymize.steam_accounts(str(tmp_path)) == [ACC]
    assert anonymize.steam_accounts(None) == [] and anonymize.steam_accounts(str(tmp_path / "x")) == []


def test_relatorio_completo_nao_vaza_e_mantem_o_save(tmp_path, monkeypatch):
    home = tmp_path / "Users" / "MariaSilva"
    saves = home / "Documents" / "Jogo" / "Saves"
    saves.mkdir(parents=True)
    binario = b"GVAS\x00\x01" + ID64.encode() + b"\x02" * 50
    (saves / "slot1.sav").write_bytes(binario)
    (saves / "perfil.json").write_text(json.dumps({"conta": ID64, "nivel": 7}), encoding="utf-8")
    desk = tmp_path / "Desktop"
    desk.mkdir()
    appdata = tmp_path / "AppData"
    appdata.mkdir()
    (appdata / "zerometro.log").write_text("erro em %s\\Documents\\x token=SEGREDO\nok\n" % home, encoding="utf-8")
    steam_root = tmp_path / "Steam"
    (steam_root / "userdata" / ACC).mkdir(parents=True)

    monkeypatch.setattr(report, "_desktop", lambda: str(desk))
    monkeypatch.setattr(report.paths, "APP_DIR", str(appdata))
    monkeypatch.setattr(report.steam, "steam_root", lambda: str(steam_root))
    monkeypatch.setattr(report.steam, "stats_files", lambda appid, root=None: (None, []))
    monkeypatch.setattr(report.steam, "achievements", lambda appid, root=None: {"A": {"unlocked": True, "time": 1, "name": "a", "desc": ""}})
    monkeypatch.setattr(anonymize.os.path, "expanduser", lambda p: str(home))

    r = report.build("Jogo", "42", [str(saves)], "9.9.9")
    with zipfile.ZipFile(r["path"]) as z:
        names = z.namelist()
        assert "saves/0/slot1.sav" in names and "saves/0/perfil.json" in names
        assert z.read("saves/0/slot1.sav") == binario  # save binário idêntico ao original
        assert ID64 not in z.read("saves/0/perfil.json").decode()
        assert json.loads(z.read("saves/0/perfil.json"))["nivel"] == 7
        tudo = "\n".join(z.read(n).decode("utf-8", "ignore") for n in ("relatorio.json", "zerometro.log", "steam/conquistas.json"))
        assert "MariaSilva" not in tudo and "SEGREDO" not in tudo
        man = json.loads(z.read("relatorio.json"))
        assert man["folders"][0]["path"].startswith("%USERPROFILE%")
        assert man["steamid_no_conteudo"] == [dict(folder=0, file="slot1.sav")]  # avisa onde o ID ficou
        assert [f["file"] for f in man["folders"][0]["files"]] and ID64.encode().hex() not in z.read("relatorio.json").decode()
        assert "ok" in z.read("zerometro.log").decode()
