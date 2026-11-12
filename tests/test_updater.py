import updater


def test_ver_parse():
    assert updater._ver("0.3.8") == (0, 3, 8)
    assert updater._ver("v1.2.3") == (1, 2, 3)
    assert updater._ver(" v2.0 ") == (2, 0)


def test_ver_compara_numericamente_e_nao_como_texto():
    assert updater._ver("0.3.10") > updater._ver("0.3.8")
    assert updater._ver("0.10.0") > updater._ver("0.9.9")
    assert updater._ver("1.0.0") > updater._ver("0.99.99")


def test_ver_iguais_nao_atualizam():
    assert not (updater._ver("0.3.8") > updater._ver("0.3.8"))
    assert not (updater._ver("v0.3.8") > updater._ver("0.3.8"))
