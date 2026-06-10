"""
activation.py — Validation de licence Price Scout.
"""
import hmac
import hashlib
import os
import subprocess
import json

_SECRET    = "v8#kPx2$mQn9!rTz4@wLj6&hYs0^dFb"
_BASE      = os.path.dirname(os.path.abspath(__file__))
if getattr(__import__("sys"), "frozen", False):
    import sys as _sys
    _BASE = os.path.dirname(_sys.executable)
_LIC_FILE   = os.path.join(_BASE, ".license")
_TRIAL_FILE = os.path.join(_BASE, ".trial")
TRIAL_LIMIT = 5


def _get_machine_id() -> str:
    """Retourne un identifiant unique lié au matériel du PC."""
    try:
        raw = subprocess.check_output(
            "wmic csproduct get uuid", shell=True, stderr=subprocess.DEVNULL
        ).decode(errors="ignore")
        uid = [l.strip() for l in raw.splitlines() if l.strip() and l.strip() != "UUID"]
        if uid:
            return hashlib.sha256(uid[0].encode()).hexdigest()[:24]
    except Exception:
        pass
    # Fallback : nom du PC + username
    import platform, getpass
    fallback = platform.node() + getpass.getuser()
    return hashlib.sha256(fallback.encode()).hexdigest()[:24]


def validate_key(key: str) -> bool:
    """Vérifie que la clé est mathématiquement valide."""
    try:
        parts = key.strip().upper().split("-")
        if len(parts) != 3 or parts[0] != "PSCT":
            return False
        uid, sig = parts[1], parts[2]
        expected = hmac.new(_SECRET.encode(), uid.encode(), hashlib.sha256).hexdigest()[:8].upper()
        return hmac.compare_digest(sig, expected)
    except Exception:
        return False


def activate(key: str) -> bool:
    """Active la licence sur ce PC. Retourne True si succès."""
    if not validate_key(key):
        return False
    machine_id = _get_machine_id()
    token = hashlib.sha256(f"{key.upper()}:{machine_id}".encode()).hexdigest()
    try:
        with open(_LIC_FILE, "w", encoding="utf-8") as f:
            f.write(f"{token}\n{key.upper()}\n{machine_id}\n")
        return True
    except Exception:
        return False


def is_activated() -> bool:
    """Vérifie si ce PC est activé."""
    if not os.path.exists(_LIC_FILE):
        return False
    try:
        lines = open(_LIC_FILE, encoding="utf-8").read().strip().splitlines()
        if len(lines) < 3:
            return False
        token, key, stored_mid = lines[0], lines[1], lines[2]
        machine_id = _get_machine_id()
        if stored_mid != machine_id:
            return False  # Clé copiée sur un autre PC
        expected = hashlib.sha256(f"{key}:{machine_id}".encode()).hexdigest()
        return hmac.compare_digest(token, expected)
    except Exception:
        return False


def get_activated_key() -> str:
    """Retourne la clé activée ou chaîne vide."""
    try:
        if os.path.exists(_LIC_FILE):
            lines = open(_LIC_FILE, encoding="utf-8").read().strip().splitlines()
            return lines[1] if len(lines) >= 2 else ""
    except Exception:
        pass
    return ""


# ── Système d'essai gratuit ───────────────────────────────────────────────────

def _trial_checksum(used: int, mid: str) -> str:
    data = f"{used}:{mid}:{_SECRET[:8]}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def get_trial_searches() -> int:
    """Retourne le nombre de recherches d'essai utilisées."""
    if not os.path.exists(_TRIAL_FILE):
        return 0
    try:
        raw = open(_TRIAL_FILE, encoding="utf-8").read()
        data = json.loads(raw)
        used = int(data.get("u", TRIAL_LIMIT))
        mid = _get_machine_id()
        if data.get("c") != _trial_checksum(used, mid):
            return TRIAL_LIMIT  # fichier modifié → essai expiré
        return min(used, TRIAL_LIMIT)
    except Exception:
        return TRIAL_LIMIT


def increment_trial() -> int:
    """Incrémente le compteur d'essai. Retourne le nouveau total."""
    used = get_trial_searches()
    if used >= TRIAL_LIMIT:
        return TRIAL_LIMIT
    new_used = used + 1
    mid = _get_machine_id()
    data = {"u": new_used, "c": _trial_checksum(new_used, mid)}
    try:
        with open(_TRIAL_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass
    return new_used


def trial_expired() -> bool:
    """Retourne True si les essais gratuits sont épuisés."""
    return get_trial_searches() >= TRIAL_LIMIT


def trial_remaining() -> int:
    """Retourne le nombre de recherches d'essai restantes."""
    return max(0, TRIAL_LIMIT - get_trial_searches())
