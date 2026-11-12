"""Pastas do Windows e configurações do Zerômetro."""
import json
import os

APP_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Zerometro")


def data_path(*parts):
    os.makedirs(APP_DIR, exist_ok=True)
    return os.path.join(APP_DIR, *parts)


def _known_documents():
    """Pasta Documentos de verdade (pode estar no OneDrive ou em outro disco)."""
    try:
        import ctypes
        from ctypes import wintypes
        # FOLDERID_Documents = {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
        class GUID(ctypes.Structure):
            _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]
        fid = GUID(0xFDD39AD0, 0x238F, 0x46AF, (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
        p = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(p)) == 0:
            path = p.value
            ctypes.windll.ole32.CoTaskMemFree(p)
            return path
    except Exception:
        pass
    return None


def documents_dirs():
    home = os.path.expanduser("~")
    cands = [_known_documents(), os.path.join(home, "Documents"), os.path.join(home, "Documentos"),
             os.path.join(home, "OneDrive", "Documents"), os.path.join(home, "OneDrive", "Documentos")]
    seen, out = set(), []
    for c in cands:
        if c and os.path.isdir(c) and os.path.normcase(c) not in seen:
            seen.add(os.path.normcase(c)); out.append(c)
    return out


def settings():
    try:
        with open(data_path("settings.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(s):
    with open(data_path("settings.json"), "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)


def extra_dirs(game_id):
    """Pastas que a pessoa escolheu à mão para um jogo."""
    return [d for d in settings().get("folders", {}).get(game_id, []) if os.path.isdir(d)]
