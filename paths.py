"""
paths.py — Résolution de chemin pour mode gelé (PyInstaller) ou normal.
"""
import sys
import os


def _get_base() -> str:
    """Dossier contenant l'exe (frozen) ou le script (normal)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _get_base()


def base_path(*parts) -> str:
    """Construit un chemin absolu relatif à BASE_DIR."""
    return os.path.join(BASE_DIR, *parts)


def bundled_path(*parts) -> str:
    """
    Chemin vers un fichier bundlé (templates, etc.).
    En mode frozen : dans _MEIPASS (extraction temp).
    En mode normal : à côté du script.
    """
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, *parts)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), *parts)
