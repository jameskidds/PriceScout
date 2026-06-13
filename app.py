import re
import threading
import statistics
import unicodedata
import uuid
import time
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if getattr(sys, "frozen", False):
    sys.path.insert(0, sys._MEIPASS)

from paths import BASE_DIR, bundled_path

ALERTS_FILE    = os.path.join(BASE_DIR, "alerts.json")
HISTORY_FILE   = os.path.join(BASE_DIR, "history.json")
WATCHLIST_FILE = os.path.join(BASE_DIR, "watchlist.json")
GEMINI_KEY_FILE = os.path.join(BASE_DIR, "gemini_key.txt")
_alerts_lock   = threading.Lock()
_history_lock  = threading.Lock()
_wl_lock       = threading.Lock()

from flask import Flask, render_template, request, jsonify
from vinted_pricer import fetch_vinted
from leboncoin_scraper import fetch_leboncoin
from activation import is_activated, increment_trial, trial_remaining, TRIAL_LIMIT


_tpl = bundled_path("templates")
app = Flask(__name__, template_folder=_tpl)

LOT_KEYWORDS = ["lot de", "lot d'", "lot ", "x cartes", " cartes pokemon",
                "bundle", "collection de", "pack de"]

def _normalize(text):
    return "".join(c for c in unicodedata.normalize("NFD", text.lower())
                   if unicodedata.category(c) != "Mn")

def _keywords_match_strict(title, query):
    """Tous les mots doivent être dans le titre."""
    title_n  = _normalize(title)
    keywords = [_normalize(k) for k in re.split(r"[\s/\-]+", query) if len(k) > 2]
    return all(kw in title_n for kw in keywords)

def _keywords_match_large(title, query):
    """Au moins un mot doit être dans le titre."""
    title_n  = _normalize(title)
    keywords = [_normalize(k) for k in re.split(r"[\s/\-]+", query) if len(k) > 2]
    return any(kw in title_n for kw in keywords) if keywords else True

def _is_lot(title):
    return any(kw in title.lower() for kw in LOT_KEYWORDS)

def _vinted_fees(price):
    """Commission Vinted : 5% + 0.70€ sous 20€, 8% + 0.70€ au-dessus."""
    if price <= 0:
        return 0
    pct = 0.05 if price < 20 else 0.08
    return round(price * pct + 0.70, 2)

def _calc_marge(buy_price, ref_price):
    """Retourne marge en € et % après frais Vinted."""
    if not ref_price or ref_price <= 0:
        return None
    fees   = _vinted_fees(ref_price)
    net    = round(ref_price - fees, 2)
    profit = round(net - buy_price, 2)
    pct    = round((profit / buy_price) * 100, 1) if buy_price > 0 else 0
    return {"profit": profit, "pct": pct, "net": net, "fees": fees, "ref": ref_price}

def _load_history():
    try:
        if os.path.exists(HISTORY_FILE):
            return json.load(open(HISTORY_FILE, encoding="utf-8"))
    except Exception:
        pass
    return []

def _save_history_entry(query, items, mode, prices):
    try:
        entry = {
            "id":          str(uuid.uuid4())[:8],
            "ts":          int(time.time()),
            "query":       query,
            "mode":        mode,
            "nb":          len(items),
            "prix_min":    round(min(prices), 2) if prices else 0,
            "prix_max":    round(max(prices), 2) if prices else 0,
            "prix_moyen":  round(statistics.mean(prices), 2) if prices else 0,
            "prix_median": round(statistics.median(prices), 2) if prices else 0,
            "items": [{"titre": i["titre"], "prix": i["prix"], "source": i["source"],
                       "url": i["url"], "photo": i.get("photo", "")} for i in items[:20]],
        }
        with _history_lock:
            history = _load_history()
            history = [h for h in history if h.get("query","").lower() != query.lower()]
            history.insert(0, entry)
            history = history[:50]
            json.dump(history, open(HISTORY_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception:
        pass

def _load_watchlist():
    try:
        if os.path.exists(WATCHLIST_FILE):
            return json.load(open(WATCHLIST_FILE, encoding="utf-8"))
    except Exception:
        pass
    return []

def _save_watchlist(wl):
    try:
        json.dump(wl, open(WATCHLIST_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception:
        pass


def _detect_etat_lbc(titre: str) -> str:
    t = titre.lower()
    if any(k in t for k in ["neuf", "jamais utilisé", "jamais ouvert", "scellé"]):
        return "Neuf"
    if any(k in t for k in ["très bon état", "tbe", "tres bon etat"]):
        return "Très bon état"
    if any(k in t for k in ["bon état", "bon etat", "be "]):
        return "Bon état"
    if any(k in t for k in ["satisfaisant", "état correct", "etat correct", "usé", "use"]):
        return "Satisfaisant"
    return ""


def _inject_marges(items):
    """Calcule la médiane de tous les prix puis injecte la marge sur chaque item."""
    prices = [i["prix"] for i in items if i.get("prix", 0) > 0]
    if not prices:
        return
    ref = round(statistics.median(prices), 2)
    for item in items:
        item["marge"] = _calc_marge(item["prix"], ref)


def _get_version():
    try:
        vpath = os.path.join(BASE_DIR, "version.txt")
        if not os.path.exists(vpath):
            vpath = bundled_path("version.txt")
        return open(vpath, encoding="utf-8").read().strip()
    except Exception:
        return "2"

@app.route("/")
def index():
    return render_template("index.html", version=_get_version())


@app.route("/search", methods=["POST"])
def search():
    data  = request.get_json()
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"erreur": "Veuillez saisir un article."}), 400

    activated = is_activated()
    if not activated:
        remaining = trial_remaining()
        if remaining <= 0:
            return jsonify({"erreur": "Essai gratuit terminé. Relancez l'application pour activer votre licence."}), 403
        increment_trial()
        remaining -= 1
    else:
        remaining = None

    mode     = (data.get("mode") or "strict")   # "strict" ou "large"
    nb_pages = int(data.get("pages") or 5)
    nb_pages = max(1, min(nb_pages, 10))
    lbc_pages   = int(data.get("lbc_pages") or 3)
    lbc_pages   = max(1, min(lbc_pages, 5))

    try:
        prix_min = float(data.get("prix_min") or 0)
        prix_max = float(data.get("prix_max") or 0)
    except (ValueError, TypeError):
        prix_min = prix_max = 0

    def keyword_ok(title):
        if mode == "large":
            return _keywords_match_large(title, query)
        return _keywords_match_strict(title, query)

    def price_ok(price):
        if prix_min > 0 and price < prix_min:
            return False
        if prix_max > 0 and price > prix_max:
            return False
        return True

    res    = {"vinted": [], "lbc": []}
    errors = {}

    def get_vinted():
        try:
            raw_items = fetch_vinted(query, pages=nb_pages)
            items = []
            for raw in raw_items:
                try:
                    ps = raw.get("price", "0")
                    if isinstance(ps, dict):
                        ps = ps.get("amount", "0")
                    price = float(str(ps).replace(",", ".").replace("€", "").strip())
                    if not (1.0 < price < 5000.0):
                        continue
                except Exception:
                    continue
                title = raw.get("title", "")
                if not keyword_ok(title):
                    continue
                if mode == "strict" and _is_lot(title):
                    continue
                if not price_ok(price):
                    continue
                item_id = raw.get("id", "")
                url     = raw.get("url") or f"https://www.vinted.fr/items/{item_id}"
                photos  = raw.get("photos") or []
                photo   = ""
                if photos:
                    first  = photos[0] if isinstance(photos[0], dict) else {}
                    thumbs = first.get("thumbnails") or []
                    photo  = (thumbs[0].get("url", "") if thumbs and isinstance(thumbs[0], dict) else "") or first.get("url", "")
                date_ts = raw.get("created_at_ts") or raw.get("updated_at_ts") or 0
                # État de l'article Vinted
                status_map = {
                    "new_with_tags":    "Neuf avec étiquettes",
                    "new_without_tags": "Neuf sans étiquettes",
                    "very_good":        "Très bon état",
                    "good":             "Bon état",
                    "satisfactory":     "Satisfaisant",
                }
                raw_status = raw.get("status") or ""
                etat = status_map.get(raw_status, raw_status or "")
                items.append({"source": "Vinted", "titre": title,
                              "prix": round(price, 2), "url": url, "photo": photo,
                              "date_ts": int(date_ts) if date_ts else 0,
                              "etat": etat})
            res["vinted"] = items
        except Exception as e:
            errors["vinted"] = str(e)

    def get_lbc():
        try:
            items = fetch_leboncoin(query, pages=lbc_pages)
            items = [i for i in items if keyword_ok(i["titre"]) and price_ok(i["prix"])]
            for item in items:
                item["etat"] = _detect_etat_lbc(item.get("titre", ""))
            res["lbc"] = items
            if not items:
                errors["lbc"] = "Aucun résultat LeBonCoin"
        except Exception as e:
            errors["lbc"] = str(e)

    threads = [
        threading.Thread(target=get_vinted),
        threading.Thread(target=get_lbc),
    ]

    for t in threads: t.start()
    for t in threads: t.join()

    all_items = res["vinted"] + res["lbc"]
    all_items.sort(key=lambda x: x["prix"])
    _inject_marges(all_items)

    prices = [i["prix"] for i in all_items]

    if all_items:
        _save_history_entry(query, all_items, mode, prices)

    return jsonify({
        "items":      all_items,
        "nb":         len(all_items),
        "prix_min":   round(min(prices), 2) if prices else 0,
        "prix_max":   round(max(prices), 2) if prices else 0,
        "prix_moyen": round(statistics.mean(prices), 2) if prices else 0,
        "sources": {
            "vinted": len(res["vinted"]),
            "lbc":    len(res["lbc"]),
        },
        "errors":  errors,
        "mode":    mode,
        "trial":   {"remaining": remaining, "limit": TRIAL_LIMIT} if remaining is not None else None,
    })


def _load_telegram():
    path = os.path.join(BASE_DIR, "telegram_key.txt")
    if not os.path.exists(path):
        return None
    try:
        lines = [l.strip() for l in open(path, encoding="utf-8").read().splitlines()
                 if l.strip() and not l.startswith("#")]
        if len(lines) >= 2:
            return {"token": lines[0], "chat_id": lines[1]}
    except Exception:
        pass
    return None


def _send_telegram(token, chat_id, items, query):
    try:
        import requests as _req
        lines = [f"🔥 *{len(items)} nouvelle{'s' if len(items)>1 else ''} bonne{'s' if len(items)>1 else ''} affaire{'s' if len(items)>1 else ''}* — `{query}`\n"]
        for i in items[:5]:
            lines.append(f"• [{i['titre'][:60]}]({i['url']}) — *{i['prix']} €* (score {i.get('score',0)})")
        msg = "\n".join(lines)
        _req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown",
                  "disable_web_page_preview": True},
            timeout=8,
        )
    except Exception:
        pass


@app.route("/notify", methods=["POST"])
def notify():
    data  = request.get_json()
    items = data.get("items") or []
    query = data.get("query") or ""
    tg    = _load_telegram()
    if tg and items:
        threading.Thread(
            target=_send_telegram,
            args=(tg["token"], tg["chat_id"], items, query),
            daemon=True,
        ).start()
    return jsonify({"ok": True})


_NON_EXPERT_KW = [
    "mon fils", "ma fille", "mon enfant", "mes enfants", "mon neveu",
    "ma niece", "mon frere", "ma soeur", "mon petit fils", "cadeau de",
    "pour noel", "anniversaire", "offert par", "recu en cadeau",
    "vide chambre", "vide grenier", "vide-grenier", "vide maison",
    "demenagement", "fait le tri", "fait du tri", "on fait le tri",
    "placard", "cave", "range dans",
    "trouve dans", "trouve au", "trouvai", "heritage", "divorce",
    "sais pas", "je sais pas", "connais pas", "pas connaisseur",
    "a estimer", "faire offre", "prix libre", "prix a discuter",
    "pas la valeur", "je ne connais pas",
    "lot de", "lot d", "en vrac", "tout ensemble", "a prendre ensemble",
    "pokmon", "pokkemon", "pikatchou", "pikatchu",
    "carte de mon", "cartes de mon", "cartes de ma",
    "idee cadeau", "a donner", "a saisir",
]

_EXPERT_KW = [
    "psa", "bgs", "cgc", "graded", "grade", "gradee",
    "near mint", "mint condition", "centering", "centrage", "gem mint",
    "extension", "set complet", "serie complete",
    "full art", "secret rare", "ultra rare", "premiere edition",
]


def _seller_profile(titre: str, desc: str) -> dict:
    """Détecte si le vendeur est un non-expert, incertain ou expert."""
    text = _normalize(titre + " " + desc)

    non_expert = sum(1 for kw in _NON_EXPERT_KW if kw in text)
    expert     = sum(1 for kw in _EXPERT_KW     if kw in text)

    desc_len = len(desc.strip())
    if desc_len < 30:
        non_expert += 1
    if desc_len < 10:
        non_expert += 1
    if desc_len > 300:
        expert += 1

    net = non_expert - expert

    if net >= 2:
        return {"label": "Non-expert", "icon": "🟢", "cls": "profile-green"}
    elif net >= 0:
        return {"label": "Incertain",  "icon": "🟡", "cls": "profile-yellow"}
    else:
        return {"label": "Expert",     "icon": "🔴", "cls": "profile-red"}


def _load_gemini_key() -> str:
    try:
        if os.path.exists(GEMINI_KEY_FILE):
            return open(GEMINI_KEY_FILE, encoding="utf-8").read().strip()
    except Exception:
        pass
    return ""


def _gemini_analyze(items: list, query: str) -> dict:
    """1 appel Gemini pour analyser les top 15 annonces. Retourne dict index → analyse."""
    key = _load_gemini_key()
    if not key or not items:
        return {}

    top = items[:15]
    items_txt = "\n".join([
        f"{i}. [{item['source']}] {item['titre']} — {item['prix']}€\n"
        f"   Description: {(item.get('description') or '')[:200]}"
        for i, item in enumerate(top)
    ])

    prompt = f"""Tu es un expert en achat-revente de seconde main (Vinted, LeBonCoin).
Recherche de l'utilisateur : "{query}"

Voici les annonces trouvées. Pour chacune, identifie l'objet et donne un verdict de revente.

{items_txt}

Réponds UNIQUEMENT avec un JSON valide, sans texte avant ni après :
[{{"i":0,"objet":"nom court","verdict":"achète","mult":3.0,"raison":"max 12 mots"}}]

Règles :
- verdict = "achète" | "peut-être" | "passe"
- mult = multiplicateur de revente estimé (2.0 = vendre 2x le prix d'achat)
- Si pas assez d'info : verdict "peut-être", mult null
- objet : nom précis et court (ex: "Nintendo 2DS XL rouge", "Lot 150 cartes Pokémon")
"""

    try:
        import urllib.request
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-1.5-flash:generateContent?key={key}"
        )
        body = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1200},
        }).encode()
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            resp = json.loads(r.read())
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if not m:
            return {}
        analyses = json.loads(m.group(0))
        return {a["i"]: a for a in analyses if isinstance(a, dict) and "i" in a}
    except Exception:
        return {}


def _hunt_score(item, keywords_n):
    """Calcule un score d'opportunité pour le mode Chasse."""
    import time as _time
    title = _normalize(item.get("titre", ""))
    desc  = _normalize(item.get("description", ""))
    prix  = item.get("prix", 0)
    ts    = item.get("date_ts", 0)
    score = 0
    matched = []

    for kw in keywords_n:
        if kw in title:
            score += 3
            matched.append(kw)
        elif kw in desc:
            score += 2
            matched.append(kw)

    # Prix très bas = vendeur qui ne sait pas ce que ça vaut
    if 0 < prix <= 10:
        score += 3
    elif prix <= 25:
        score += 2
    elif prix <= 50:
        score += 1

    # Prix rond (5, 10, 15, 20...) = mis au hasard
    if prix > 0 and prix == round(prix / 5) * 5:
        score += 1

    # Annonce récente (< 24h)
    if ts and (_time.time() - ts) < 86400:
        score += 3

    # Profil vendeur : bonus si non-expert détecté
    profile = _seller_profile(item.get("titre", ""), item.get("description", ""))
    item["seller_profile"] = profile
    if profile["label"] == "Non-expert":
        score += 4
    elif profile["label"] == "Incertain":
        score += 1

    item["score"]            = score
    item["matched_keywords"] = matched
    return score


@app.route("/hunt", methods=["POST"])
def hunt():
    data     = request.get_json()
    query    = (data.get("query") or "").strip()
    keywords = [k.strip() for k in (data.get("keywords") or []) if k.strip()]
    if not query:
        return jsonify({"erreur": "Veuillez saisir un article."}), 400

    nb_pages  = max(1, min(int(data.get("pages") or 5), 10))
    lbc_pages = max(1, min(int(data.get("lbc_pages") or 3), 5))
    keywords_n = [_normalize(k) for k in keywords]

    res    = {"vinted": [], "lbc": []}

    def get_vinted_hunt():
        try:
            raw_items = fetch_vinted(query, pages=nb_pages)
            items = []
            for raw in raw_items:
                try:
                    ps = raw.get("price", "0")
                    if isinstance(ps, dict):
                        ps = ps.get("amount", "0")
                    price = float(str(ps).replace(",", ".").replace("€", "").strip())
                    if not (1.0 < price < 5000.0):
                        continue
                except Exception:
                    continue
                title = raw.get("title", "")
                desc  = (raw.get("description") or "").strip()
                item_id = raw.get("id", "")
                url     = raw.get("url") or f"https://www.vinted.fr/items/{item_id}"
                photos  = raw.get("photos") or []
                photo   = ""
                if photos:
                    first  = photos[0] if isinstance(photos[0], dict) else {}
                    thumbs = first.get("thumbnails") or []
                    photo  = (thumbs[0].get("url", "") if thumbs and isinstance(thumbs[0], dict) else "") or first.get("url", "")
                date_ts = raw.get("created_at_ts") or raw.get("updated_at_ts") or 0
                items.append({"source": "Vinted", "titre": title, "description": desc,
                              "prix": round(price, 2), "url": url, "photo": photo,
                              "date_ts": int(date_ts) if date_ts else 0})
            res["vinted"] = items
        except Exception:
            pass

    def get_lbc_hunt():
        try:
            res["lbc"] = fetch_leboncoin(query, pages=lbc_pages)
        except Exception:
            pass

    threads = [
        threading.Thread(target=get_vinted_hunt),
        threading.Thread(target=get_lbc_hunt),
    ]
    for t in threads: t.start()
    for t in threads: t.join()

    all_items = res["vinted"] + res["lbc"]

    # Calcule le score pour chaque item
    for item in all_items:
        _hunt_score(item, keywords_n)

    # Filtre : garde uniquement les items avec au moins 1 mot-clé trouvé (si des mots-clés fournis)
    if keywords_n:
        all_items = [i for i in all_items if i.get("score", 0) > 0]

    _inject_marges(all_items)

    # ── Flip score : potentiel de revente basé sur la médiane Vinted ──
    vinted_prices = [i["prix"] for i in res["vinted"] if i.get("prix", 0) > 0]
    vinted_median = round(statistics.median(vinted_prices), 2) if len(vinted_prices) >= 3 else None

    for item in all_items:
        if vinted_median and item["prix"] > 0:
            mult = round(vinted_median / item["prix"], 1)
            if mult >= 3:
                cls, icon = "flip-fire",  "🔥"
            elif mult >= 2:
                cls, icon = "flip-good",  "✅"
            elif mult >= 1.3:
                cls, icon = "flip-ok",    "⚠️"
            else:
                cls, icon = "flip-bad",   "❌"
            item["flip"] = {"mult": mult, "label": f"{icon} x{mult}", "cls": cls, "ref": vinted_median}
        else:
            item["flip"] = None

    # Trie par flip multiplier décroissant, puis score décroissant
    all_items.sort(key=lambda x: (
        -(x["flip"]["mult"] if x.get("flip") else 0),
        -x.get("score", 0)
    ))

    # ── Analyse LLM Gemini (1 seul appel pour les 15 premiers) ──
    gemini = _gemini_analyze(all_items, query)
    for idx, item in enumerate(all_items[:15]):
        if idx in gemini:
            g = gemini[idx]
            verdict = g.get("verdict", "")
            item["llm"] = {
                "objet":   g.get("objet", ""),
                "verdict": verdict,
                "icon":    {"achète": "🔥", "peut-être": "⚠️", "passe": "❌"}.get(verdict, "💡"),
                "mult":    g.get("mult"),
                "raison":  g.get("raison", ""),
            }

    return jsonify({
        "items":          all_items,
        "nb":             len(all_items),
        "vinted_median":  vinted_median,
        "has_llm":        bool(gemini),
        "sources": {
            "vinted": len(res["vinted"]),
            "lbc":    len(res["lbc"]),
        },
    })


# ─────────────────────────────────────────────
#  GESTION DES ALERTES (persistantes)
# ─────────────────────────────────────────────

def _load_alerts():
    try:
        if os.path.exists(ALERTS_FILE):
            return json.load(open(ALERTS_FILE, encoding="utf-8"))
    except Exception:
        pass
    return []

def _save_alerts(alerts):
    try:
        json.dump(alerts, open(ALERTS_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    except Exception:
        pass

def _scan_alert(alert):
    """Scanne une alerte et notifie si nouvelles annonces."""
    query     = alert.get("query", "")
    prix_max  = float(alert.get("prix_max") or 0)
    mode      = alert.get("mode", "large")
    seen_urls = set(alert.get("seen_urls", []))

    def kw_ok(title):
        if mode == "large":
            return _keywords_match_large(title, query)
        return _keywords_match_strict(title, query)

    res = {"vinted": [], "lbc": []}

    def _vinted():
        try:
            raw_items = fetch_vinted(query, pages=2)
            res["vinted_raw_count"] = len(raw_items)  # pour détecter le ban
            items = []
            for raw in raw_items:
                try:
                    ps = raw.get("price", "0")
                    if isinstance(ps, dict): ps = ps.get("amount", "0")
                    price = float(str(ps).replace(",", ".").replace("€", "").strip())
                    if not (1.0 < price < 5000.0): continue
                except Exception:
                    continue
                title = raw.get("title", "")
                if not kw_ok(title): continue
                if prix_max > 0 and price > prix_max: continue
                item_id = raw.get("id", "")
                url     = raw.get("url") or f"https://www.vinted.fr/items/{item_id}"
                items.append({"source": "Vinted", "titre": title, "prix": round(price, 2), "url": url})
            res["vinted"] = items
        except Exception:
            res["vinted_raw_count"] = -1  # erreur réseau

    def _lbc():
        try:
            items = fetch_leboncoin(query, pages=2)
            items = [i for i in items if kw_ok(i["titre"])
                     and (prix_max <= 0 or i["prix"] <= prix_max)]
            res["lbc"] = items
        except Exception:
            pass

    res["vinted_raw_count"] = 0
    t1 = threading.Thread(target=_vinted)
    t2 = threading.Thread(target=_lbc)
    t1.start(); t2.start(); t1.join(); t2.join()

    # Détecteur de ban Vinted : 0 résultat brut = suspect
    vinted_raw = res.get("vinted_raw_count", 0)
    if vinted_raw == 0:
        alert["vinted_zero_streak"] = alert.get("vinted_zero_streak", 0) + 1
    else:
        alert["vinted_zero_streak"] = 0
    alert["vinted_ban_suspect"] = alert.get("vinted_zero_streak", 0) >= 3

    all_items  = res["vinted"] + res["lbc"]
    cutoff    = time.time() - 48 * 3600
    new_items = [i for i in all_items
                 if i["url"] not in seen_urls
                 and (not i.get("date_ts") or i.get("date_ts", 0) > cutoff)]

    # Met à jour les URLs vues
    alert["seen_urls"] = list(seen_urls | {i["url"] for i in all_items})
    alert["last_scan"] = int(time.time())
    alert["total_seen"] = len(alert["seen_urls"])

    if new_items:
        alert["last_hit"]    = int(time.time())
        alert["nb_hits"]     = alert.get("nb_hits", 0) + len(new_items)
        tg = _load_telegram()
        if tg:
            _send_telegram(tg["token"], tg["chat_id"], new_items,
                           f'{query}{" ≤"+str(prix_max)+"€" if prix_max else ""}')

    return new_items


def _alert_worker():
    """Thread daemon qui scanne toutes les alertes toutes les 5 min."""
    time.sleep(15)  # attend que Flask soit prêt
    while True:
        with _alerts_lock:
            alerts = _load_alerts()
            changed = False
            for alert in alerts:
                if not alert.get("active", True):
                    continue
                try:
                    _scan_alert(alert)
                    changed = True
                except Exception:
                    pass
            if changed:
                _save_alerts(alerts)
        time.sleep(120)  # 2 minutes


# Lance le worker au démarrage
_worker_thread = threading.Thread(target=_alert_worker, daemon=True)
_worker_thread.start()


@app.route("/alerts", methods=["GET"])
def get_alerts():
    with _alerts_lock:
        alerts = _load_alerts()
    # Ne retourne pas les seen_urls (trop lourd)
    safe = [{k: v for k, v in a.items() if k != "seen_urls"} for a in alerts]
    return jsonify(safe)


ALERT_LIMIT = 5

@app.route("/alerts", methods=["POST"])
def create_alert():
    data      = request.get_json()
    query     = (data.get("query") or "").strip()
    if not query:
        return jsonify({"erreur": "Requête vide"}), 400
    with _alerts_lock:
        alerts = _load_alerts()
        active_count = sum(1 for a in alerts if a.get("active", True))
        if active_count >= ALERT_LIMIT:
            return jsonify({"erreur": f"Limite de {ALERT_LIMIT} alertes atteinte. Supprime ou désactive une alerte existante."}), 400
        alert = {
            "id":         str(uuid.uuid4())[:8],
            "query":      query,
            "prix_max":   float(data.get("prix_max") or 0),
            "mode":       data.get("mode", "large"),
            "active":     True,
            "created_at": int(time.time()),
            "last_scan":  None,
            "last_hit":   None,
            "nb_hits":    0,
            "total_seen": 0,
            "seen_urls":  [],
        }
        # Premier scan pour initialiser les URLs (pas de notif)
        try:
            _scan_alert(alert)
        except Exception:
            pass
        alerts.append(alert)
        _save_alerts(alerts)
    return jsonify({k: v for k, v in alert.items() if k != "seen_urls"})


@app.route("/alerts/<alert_id>", methods=["DELETE"])
def delete_alert(alert_id):
    with _alerts_lock:
        alerts = _load_alerts()
        alerts = [a for a in alerts if a.get("id") != alert_id]
        _save_alerts(alerts)
    return jsonify({"ok": True})


@app.route("/alerts/<alert_id>/toggle", methods=["POST"])
def toggle_alert(alert_id):
    with _alerts_lock:
        alerts = _load_alerts()
        for a in alerts:
            if a.get("id") == alert_id:
                a["active"] = not a.get("active", True)
                break
        _save_alerts(alerts)
    return jsonify({"ok": True})


@app.route("/alerts/<alert_id>", methods=["PUT"])
def update_alert(alert_id):
    data  = request.get_json()
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"erreur": "Requête vide"}), 400
    with _alerts_lock:
        alerts = _load_alerts()
        for a in alerts:
            if a.get("id") == alert_id:
                a["query"]     = query
                a["prix_max"]  = float(data.get("prix_max") or 0)
                a["mode"]      = data.get("mode", "large")
                a["seen_urls"] = []   # repart de zéro après modif
                a["last_scan"] = None
                break
        _save_alerts(alerts)
    return jsonify({"ok": True})


# ─────────────────────────────────────────────
#  HISTORIQUE
# ─────────────────────────────────────────────

@app.route("/history", methods=["GET"])
def get_history():
    with _history_lock:
        h = _load_history()
    summary = [{k: v for k, v in e.items() if k != "items"} for e in h]
    return jsonify(summary)

@app.route("/history/<entry_id>", methods=["GET"])
def get_history_entry(entry_id):
    with _history_lock:
        h = _load_history()
    entry = next((e for e in h if e.get("id") == entry_id), None)
    if not entry:
        return jsonify({"erreur": "Not found"}), 404
    return jsonify(entry)

@app.route("/history", methods=["DELETE"])
def clear_history():
    with _history_lock:
        if os.path.exists(HISTORY_FILE):
            os.remove(HISTORY_FILE)
    return jsonify({"ok": True})


# ─────────────────────────────────────────────
#  WATCHLIST
# ─────────────────────────────────────────────

@app.route("/watchlist", methods=["GET"])
def get_watchlist():
    with _wl_lock:
        wl = _load_watchlist()
    return jsonify(wl)

@app.route("/watchlist", methods=["POST"])
def add_watchlist():
    data = request.get_json()
    item = {
        "id":     str(uuid.uuid4())[:8],
        "ts":     int(time.time()),
        "titre":  (data.get("titre") or "")[:200],
        "prix":   float(data.get("prix") or 0),
        "source": data.get("source", ""),
        "url":    data.get("url", ""),
        "photo":  data.get("photo", ""),
        "query":  data.get("query", ""),
        "marge":  data.get("marge"),
    }
    with _wl_lock:
        wl = _load_watchlist()
        if not any(w.get("url") == item["url"] for w in wl):
            wl.insert(0, item)
            _save_watchlist(wl)
    return jsonify(item)

@app.route("/watchlist/<item_id>", methods=["DELETE"])
def remove_watchlist(item_id):
    with _wl_lock:
        wl = _load_watchlist()
        wl = [w for w in wl if w.get("id") != item_id]
        _save_watchlist(wl)
    return jsonify({"ok": True})


# ─────────────────────────────────────────────
#  STATS MARCHÉ
# ─────────────────────────────────────────────

@app.route("/market-stats", methods=["POST"])
def market_stats():
    data  = request.get_json()
    query = (data.get("query") or "").strip().lower()
    with _history_lock:
        h = _load_history()
    entries = [e for e in h if query in e.get("query","").lower()
               or e.get("query","").lower() in query]
    if len(entries) < 2:
        return jsonify({"available": False})
    now    = int(time.time())
    e7d    = [e for e in entries if e.get("ts", 0) >= now - 7*86400]
    e30d   = [e for e in entries if e.get("ts", 0) >= now - 30*86400]
    def avg(ents):
        vals = [e["prix_median"] for e in ents if e.get("prix_median")]
        return round(statistics.mean(vals), 2) if vals else None
    return jsonify({
        "available":    True,
        "nb_recherches": len(entries),
        "tendance_7j":  avg(e7d),
        "tendance_30j": avg(e30d),
        "tendance_all": avg(entries),
        "last_ts":      entries[0].get("ts", 0),
    })


@app.route("/settings", methods=["GET"])
def get_settings():
    path = os.path.join(BASE_DIR, "telegram_key.txt")
    try:
        if os.path.exists(path):
            lines = [l.strip() for l in open(path, encoding="utf-8").read().splitlines()
                     if l.strip() and not l.startswith("#")]
            if len(lines) >= 2:
                return jsonify({"token": lines[0], "chat_id": lines[1]})
    except Exception:
        pass
    return jsonify({"token": "", "chat_id": ""})


@app.route("/settings", methods=["POST"])
def save_settings():
    data    = request.get_json()
    token   = (data.get("token") or "").strip()
    chat_id = (data.get("chat_id") or "").strip()
    if not token or not chat_id:
        return jsonify({"ok": False, "error": "Champs manquants"}), 400
    path = os.path.join(BASE_DIR, "telegram_key.txt")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{token}\n{chat_id}\n")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/settings/gemini", methods=["GET"])
def get_gemini_settings():
    key = _load_gemini_key()
    masked = (key[:8] + "..." + key[-4:]) if len(key) > 12 else ("✅ Configurée" if key else "")
    return jsonify({"configured": bool(key), "masked": masked})


@app.route("/settings/gemini", methods=["POST"])
def save_gemini_settings():
    data = request.get_json()
    key  = (data.get("key") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "Clé manquante"}), 400
    try:
        with open(GEMINI_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(key)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/settings/test", methods=["POST"])
def test_settings():
    data    = request.get_json()
    token   = (data.get("token") or "").strip()
    chat_id = (data.get("chat_id") or "").strip()
    if not token or not chat_id:
        return jsonify({"ok": False, "error": "Champs manquants"}), 400
    try:
        import requests as _req
        resp = _req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id,
                  "text": "Price Scout — connexion Telegram active !",
                  "parse_mode": "Markdown"},
            timeout=8,
        )
        if resp.status_code == 200:
            return jsonify({"ok": True})
        else:
            detail = resp.json().get("description", "Erreur inconnue")
            return jsonify({"ok": False, "error": detail})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=5000)
