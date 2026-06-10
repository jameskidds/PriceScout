"""
main.py — Point d'entrée unique Price Scout.
Lance Flask dans un thread du même processus (plus fiable en mode frozen).
"""
import sys
import os
import socket
import threading
import webbrowser
import time

# Ajouter les dossiers sources au path
_this_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _this_dir)
if getattr(sys, "frozen", False):
    sys.path.insert(0, sys._MEIPASS)


def port_libre(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) != 0


PORT = 5000

# ── Vérification licence / essai gratuit ─────────────────────
from activation import is_activated, trial_expired

if not is_activated():
    if trial_expired():
        from activation_window import show_activation_window
        ok = show_activation_window(trial_mode=True)
        if not ok:
            sys.exit(0)

# ── Si le serveur tourne déjà, ouvrir le navigateur ──────────
if not port_libre(PORT):
    webbrowser.open(f"http://localhost:{PORT}")
    sys.exit(0)

# ── Lancer Flask dans un thread du même processus ────────────
def _run_flask():
    import traceback
    try:
        import app as flask_app
        flask_app.app.run(
            host="127.0.0.1",
            port=PORT,
            debug=True,
            use_reloader=False,
            threaded=True,
        )
    except Exception:
        err = traceback.format_exc()
        print(err, flush=True)
        log = os.path.join(_this_dir, "error_log.txt")
        with open(log, "w", encoding="utf-8") as f:
            f.write(err)

flask_thread = threading.Thread(target=_run_flask, daemon=False)
flask_thread.start()

# Attendre que Flask soit prêt
for _ in range(30):
    time.sleep(0.5)
    if not port_libre(PORT):
        break

webbrowser.open(f"http://localhost:{PORT}")
