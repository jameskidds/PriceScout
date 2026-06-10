"""
activation_window.py — Fenêtre d'activation Price Scout.
"""
import tkinter as tk
from tkinter import font as tkfont
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from activation import validate_key, activate, is_activated, get_activated_key, TRIAL_LIMIT


BG       = "#0d0d14"
CARD     = "#1c1c2e"
BORDER   = "#2e2e4a"
ACCENT   = "#6c47ff"
TEXT     = "#eeeef8"
MUTED    = "#6b6b90"
GREEN    = "#3ddc84"
RED      = "#ff5a5a"
YELLOW   = "#ffc857"


def show_activation_window(trial_mode: bool = False) -> bool:
    """
    Affiche la fenêtre d'activation.
    trial_mode=True : l'essai est épuisé, message adapté.
    Retourne True si activé avec succès, False si fermé sans activer.
    """
    result = {"ok": False}

    root = tk.Tk()
    root.title("Price Scout — Activation")
    root.configure(bg=BG)
    root.resizable(False, False)

    # Centrer la fenêtre
    w, h = 520, 390
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # ── Logo ──────────────────────────────────
    logo_frame = tk.Frame(root, bg=BG)
    logo_frame.pack(pady=(24, 0))

    logo_icon = tk.Label(logo_frame, text="🔎", font=("Segoe UI", 28), bg=BG)
    logo_icon.pack()
    logo_txt = tk.Label(logo_frame, text="Price Scout",
                        font=("Segoe UI", 20, "bold"), bg=BG, fg=TEXT)
    logo_txt.pack()

    if trial_mode:
        sub_txt = tk.Label(
            logo_frame,
            text=f"Essai gratuit terminé ({TRIAL_LIMIT}/{TRIAL_LIMIT} recherches utilisées)",
            font=("Segoe UI", 10, "bold"), bg=BG, fg=YELLOW
        )
        sub_txt.pack(pady=(4, 0))
        hint_txt = tk.Label(
            logo_frame,
            text="Entrez votre clé pour continuer à utiliser Price Scout",
            font=("Segoe UI", 9), bg=BG, fg=MUTED
        )
        hint_txt.pack(pady=(2, 0))
    else:
        sub_txt = tk.Label(logo_frame, text="Activez votre licence pour continuer",
                           font=("Segoe UI", 10), bg=BG, fg=MUTED)
        sub_txt.pack(pady=(4, 0))

    # ── Champ clé ─────────────────────────────
    key_frame = tk.Frame(root, bg=BG)
    key_frame.pack(pady=(28, 0), padx=40, fill="x")

    key_label = tk.Label(key_frame, text="Clé d'activation",
                         font=("Segoe UI", 9, "bold"), bg=BG, fg=MUTED)
    key_label.pack(anchor="w")

    entry_frame = tk.Frame(key_frame, bg=BORDER, bd=0)
    entry_frame.pack(fill="x", pady=(5, 0))

    key_var = tk.StringVar()
    key_entry = tk.Entry(
        entry_frame, textvariable=key_var,
        font=("Consolas", 13), bg=CARD, fg=TEXT,
        insertbackground=TEXT, relief="flat",
        bd=10, justify="center"
    )
    key_entry.pack(fill="x", ipady=6)
    key_entry.insert(0, "PSCT-XXXXXXXX-XXXXXXXX")
    key_entry.config(fg=MUTED)

    def on_focus_in(e):
        if key_entry.get() == "PSCT-XXXXXXXX-XXXXXXXX":
            key_entry.delete(0, "end")
            key_entry.config(fg=TEXT)

    def on_focus_out(e):
        if not key_entry.get().strip():
            key_entry.insert(0, "PSCT-XXXXXXXX-XXXXXXXX")
            key_entry.config(fg=MUTED)

    key_entry.bind("<FocusIn>",  on_focus_in)
    key_entry.bind("<FocusOut>", on_focus_out)
    key_entry.bind("<Return>",   lambda e: do_activate())

    # ── Statut ────────────────────────────────
    status_var = tk.StringVar(value="")
    status_lbl = tk.Label(root, textvariable=status_var,
                          font=("Segoe UI", 9), bg=BG, fg=MUTED)
    status_lbl.pack(pady=(10, 0))

    # ── Bouton activer ────────────────────────
    def do_activate():
        key = key_var.get().strip()
        if not key or key == "PSCT-XXXXXXXX-XXXXXXXX":
            status_var.set("Entrez votre clé d'activation.")
            status_lbl.config(fg=YELLOW)
            return

        if not validate_key(key):
            status_var.set("Clé invalide. Vérifiez et réessayez.")
            status_lbl.config(fg=RED)
            entry_frame.config(bg=RED)
            root.after(600, lambda: entry_frame.config(bg=BORDER))
            return

        if activate(key):
            status_var.set("Activation réussie !")
            status_lbl.config(fg=GREEN)
            btn_activate.config(state="disabled")
            result["ok"] = True
            root.after(1200, root.destroy)
        else:
            status_var.set("Erreur lors de l'activation. Réessayez.")
            status_lbl.config(fg=RED)

    btn_activate = tk.Button(
        root, text="Activer",
        font=("Segoe UI", 11, "bold"),
        bg=ACCENT, fg="white", activebackground="#8f6fff",
        activeforeground="white", relief="flat", cursor="hand2",
        padx=30, pady=10,
        command=do_activate
    )
    btn_activate.pack(pady=(8, 0))

    # ── Aide ──────────────────────────────────
    help_lbl = tk.Label(
        root,
        text="Vous n'avez pas de clé ? Contactez le vendeur.",
        font=("Segoe UI", 8), bg=BG, fg=MUTED
    )
    help_lbl.pack(pady=(16, 0))

    key_entry.focus_set()

    def on_close():
        result["ok"] = False
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
    return result["ok"]


if __name__ == "__main__":
    if is_activated():
        print(f"Deja active : {get_activated_key()}")
    else:
        ok = show_activation_window()
        print("Resultat :", "OK" if ok else "Annule")
