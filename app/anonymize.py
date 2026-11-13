"""Tira dados pessoais do relatório sem atrapalhar a análise do save.

O que muda:
- caminhos com a pasta do usuário do Windows viram %USERPROFILE%\\... (e C:\\Users\\qualquer-nome vira C:\\Users\\<usuario>);
- o ID da conta Steam (SteamID64 de 17 dígitos e o número curto das pastas userdata\\<número>) vira um
  código de 6 letras/números, sempre o mesmo dentro do mesmo relatório e diferente de um relatório para outro;
- no log: além disso, tokens, e-mails, endereços IP (menos 127.x), nome do usuário e nome do PC.

O que NÃO muda: o conteúdo dos arquivos de save. Só arquivos de texto (json, txt, vdf...) têm o ID trocado;
binário fica como está, porque mexer nele pode quebrar o formato. Os que têm um ID dentro são listados no
relatório (campo steamid_no_conteudo) para a pessoa saber.
"""
import hashlib
import os
import re
import secrets

STEAM64_BASE = 76561197960265728
_STEAM64 = re.compile(r"7656119\d{10}")
_STEAM64_B = re.compile(rb"7656119\d{10}")
_USERS = re.compile(r"(?i)((?:[A-Za-z]:)?[\\/]+Users[\\/]+)(?!<usuario>)[^\\/\s\"'<>|:*?,;()\[\]{}]+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# IPv4: não pega o meio de números maiores (1.2.3.4.5), octetos > 255 nem versões ("versão 1.2.3.4", "v1.2.3.4")
_IPV4 = re.compile(r"(?<![\d.])(?!127\.)(?!0\.)\d{1,3}(?:\.\d{1,3}){3}(?!\.?\d)")
_VERSION_BEFORE = re.compile(r"(?i)\b(vers[aã]o|version|ver|build|release|windows|win|python|app|v)[\s:=_-]{0,3}$")
# IPv6: forma completa (8 grupos) e a abreviada com "::" que tenha algum dígito (evita "face::beef", "std::x")
_IPV6 = re.compile(r"(?<![\w:])(?:(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}"
                   r"|(?:[0-9A-Fa-f]{1,4}:){1,7}:(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,5})?)(?![\w:])")


def _ipv4_repl(m):
    if any(int(p) > 255 for p in m.group().split(".")):
        return m.group()
    if _VERSION_BEFORE.search(m.string[max(0, m.start() - 20):m.start()]):
        return m.group()
    return "<ip>"


def _ipv6_repl(m):
    g = m.group()
    return "<ip>" if re.search(r"[0-9]", g) else g


def _decode_text(data):
    """(texto, codificação, BOM) se for texto UTF-8 ou UTF-16 (com ou sem BOM); None se for binário."""
    if data[:2] == b"\xff\xfe":
        enc, bom, body = "utf-16-le", b"\xff\xfe", data[2:]
    elif data[:2] == b"\xfe\xff":
        enc, bom, body = "utf-16-be", b"\xfe\xff", data[2:]
    elif b"\x00" in data:
        # UTF-16 sem BOM: texto latino tem um byte zero a cada dois
        if len(data) < 4 or len(data) % 2 or data[0::2].count(0) or data[1::2].count(0) < 0.9 * (len(data) // 2):
            return None
        enc, bom, body = "utf-16-le", b"", data
    else:
        enc, bom, body = "utf-8", b"", data
    try:
        return body.decode(enc), enc, bom
    except UnicodeDecodeError:
        return None
_TOKEN = re.compile(r"(?i)((?:token|senha|password|secret|key)\s*[=:]\s*|[?&]t=)[^\s&\"']+")
TEXT_EXT = {".json", ".txt", ".vdf", ".acf", ".ini", ".cfg", ".xml", ".csv", ".yaml", ".yml", ".log"}


class Anon:
    def __init__(self, home=None, account_ids=(), salt=None, computer=None):
        self.home = (home if home is not None else os.path.expanduser("~")).rstrip("\\/")
        self.user = os.path.basename(self.home.replace("\\", "/")) if self.home else ""
        self.salt = salt or secrets.token_hex(8)
        self.computer = computer if computer is not None else os.environ.get("COMPUTERNAME", "")
        self.accounts = {str(a) for a in account_ids if str(a).isdigit() and len(str(a)) >= 5}
        self.seen = set()  # contas que apareceram e foram trocadas
        self._home_re = None
        if self.home:
            parts = [re.escape(p) for p in re.split(r"[\\/]+", self.home) if p]
            self._home_re = re.compile(r"(?i)" + r"[\\/]+".join(parts) + r"(?=[\\/]|$|[^\w])")
        self._acc_re = None
        self._rebuild()

    def _rebuild(self):
        self._acc_re = re.compile(r"(?<!\d)(?:%s)(?!\d)" % "|".join(sorted(map(re.escape, self.accounts), key=len, reverse=True))) \
            if self.accounts else None

    def add_accounts(self, ids):
        self.accounts |= {str(a) for a in ids if str(a).isdigit() and len(str(a)) >= 5}
        self._rebuild()

    def tag(self, account):
        self.seen.add(str(account))
        return hashlib.sha256((self.salt + str(account)).encode()).hexdigest()[:6]

    def steam(self, s):
        """Troca SteamID64 e os números de conta conhecidos."""
        def big(m):
            acc = int(m.group()) - STEAM64_BASE
            return "STEAMID_" + self.tag(acc)
        s = _STEAM64.sub(big, s)
        if self._acc_re:
            s = self._acc_re.sub(lambda m: "STEAMID_" + self.tag(m.group()), s)
        return s

    def path(self, s):
        """Caminho/texto com a pasta do usuário trocada e IDs Steam mascarados."""
        s = str(s)
        if self._home_re:
            s = self._home_re.sub(lambda m: "%USERPROFILE%", s)
        s = _USERS.sub(lambda m: m.group(1) + "<usuario>", s)
        return self.steam(s)

    def names(self, s):
        """Troca o nome de usuário do Windows e o nome do PC onde aparecerem como palavra inteira."""
        if len(self.user) >= 3:
            s = re.sub(r"(?i)(?<![\w])%s(?![\w])" % re.escape(self.user), "<usuario>", s)
        if len(self.computer) >= 3:
            s = re.sub(r"(?i)(?<![\w])%s(?![\w])" % re.escape(self.computer), "<pc>", s)
        return s

    def text(self, s):
        """Texto de um arquivo: caminhos, ID Steam, nome de usuário e nome do PC (sem mexer em e-mail, IP ou token)."""
        return self.names(self.path(s))

    def log_line(self, s):
        s = self.path(s)
        s = _TOKEN.sub(lambda m: m.group(1) + "<oculto>", s)
        s = _EMAIL.sub("<email>", s)
        s = _IPV4.sub(_ipv4_repl, s)
        s = _IPV6.sub(_ipv6_repl, s)
        return self.names(s)

    def log(self, text, max_lines=1500):
        lines = text.splitlines()[-max_lines:]
        return "\n".join(self.log_line(x) for x in lines) + "\n"

    def has_id(self, data):
        """True se há um ID Steam em ASCII dentro de bytes (usado só para avisar, sem alterar o arquivo)."""
        if _STEAM64_B.search(data):
            return True
        return any(a.encode() in data for a in self.accounts if len(a) >= 8)

    def head_hex(self, data):
        """Primeiros bytes em hexadecimal, com IDs em ASCII trocados por zeros do mesmo tamanho."""
        b = _STEAM64_B.sub(lambda m: b"0" * len(m.group()), data)
        for a in self.accounts:
            if len(a) >= 8:
                b = b.replace(a.encode(), b"0" * len(a))
        return b.hex()

    def file_content(self, name, data):
        """(bytes a gravar, True se houve troca). Só texto puro mexe; binário passa intacto."""
        if os.path.splitext(name)[1].lower() not in TEXT_EXT:
            return data, False
        dec = _decode_text(data)
        if dec is None:
            return data, False
        txt, enc, bom = dec
        new = self.text(txt)
        return (bom + new.encode(enc), True) if new != txt else (data, False)


def steam_accounts(steam_root):
    """Números de conta Steam do PC (pastas de userdata)."""
    if not steam_root:
        return []
    try:
        return [d for d in os.listdir(os.path.join(steam_root, "userdata")) if d.isdigit() and d != "0"]
    except OSError:
        return []
