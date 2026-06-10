#!/usr/bin/env python3
"""
vinted_pricer.py - Analyseur de prix Vinted pour revente
Usage: python vinted_pricer.py "nike air max 90" --prix 45 --frais 5
"""

import json
import statistics
import argparse
import time
import sys
import random
from datetime import datetime

try:
    from curl_cffi import requests
    _IMPERSONATE = "chrome120"
except ImportError:
    import requests as requests
    _IMPERSONATE = None

VINTED_SEARCH_URL = "https://www.vinted.fr/api/v2/catalog/items"
MARGE_MIN_PCT = 30

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# ─────────────────────────────────────────────
#  FETCH VINTED
# ─────────────────────────────────────────────
def fetch_vinted(query: str, pages: int = 3) -> list[dict]:
    """Récupère les annonces Vinted pour une recherche donnée."""
    items = []

    headers = {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.vinted.fr/",
        "Origin": "https://www.vinted.fr",
        "DNT": "1",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }

    if _IMPERSONATE:
        session = requests.Session(impersonate=_IMPERSONATE)
    else:
        session = requests.Session()
        session.headers.update(headers)

    # Récupère les cookies CSRF comme un vrai navigateur
    try:
        if _IMPERSONATE:
            session.get("https://www.vinted.fr/", timeout=10)
        else:
            session.get("https://www.vinted.fr/", timeout=10)
    except Exception:
        pass

    for page in range(1, pages + 1):
        params = {
            "search_text": query,
            "page": page,
            "per_page": 96,
            "order": "newest_first",
        }
        try:
            if _IMPERSONATE:
                resp = session.get(VINTED_SEARCH_URL, params=params, timeout=15)
            else:
                resp = session.get(VINTED_SEARCH_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            page_items = data.get("items", [])
            if not page_items:
                break
            items.extend(page_items)
            print(f"  Page {page} → {len(page_items)} annonces récupérées")
            time.sleep(random.uniform(3.0, 4.0))  # délai aléatoire anti-détection
        except Exception as e:
            print(f"[ERREUR] Page {page} : {e}")
            break

    return items


# ─────────────────────────────────────────────
#  ANALYSE PRIX
# ─────────────────────────────────────────────
def extract_prices(items: list[dict]) -> list[float]:
    """Extrait les prix des annonces Vinted."""
    prices = []
    for item in items:
        try:
            price_str = item.get("price", "0")
            # Vinted renvoie le prix comme string ou dict selon la version de l'API
            if isinstance(price_str, dict):
                price_str = price_str.get("amount", "0")
            price = float(str(price_str).replace(",", ".").replace("€", "").strip())
            if 1.0 < price < 5000.0:  # Filtre les valeurs absurdes
                prices.append(price)
        except (ValueError, TypeError):
            continue
    return prices


def analyse(prices: list[float], prix_achat: float, frais: float = 0.0) -> dict:
    """Calcule les statistiques et la rentabilité."""
    if not prices:
        return {"erreur": "Aucun prix exploitable trouvé."}

    prix_total = prix_achat + frais
    mediane = statistics.median(prices)
    moyenne = statistics.mean(prices)
    ecart_type = statistics.stdev(prices) if len(prices) > 1 else 0
    prix_min = min(prices)
    prix_max = max(prices)

    # Prix de revente réaliste = médiane - 10% (pour vendre vite)
    prix_revente_cible = mediane * 0.90

    # Commission Vinted (~5% + 0.70€ ou 8% + 0.70€ selon montant)
    if prix_revente_cible < 20:
        commission_vinted = prix_revente_cible * 0.05 + 0.70
    else:
        commission_vinted = prix_revente_cible * 0.08 + 0.70

    revenu_net = prix_revente_cible - commission_vinted
    profit = revenu_net - prix_total
    marge_pct = (profit / prix_total * 100) if prix_total > 0 else 0

    # Verdict
    if marge_pct >= MARGE_MIN_PCT:
        verdict = "✅ OPPORTUNITÉ RENTABLE"
        conseil = f"Marge de {marge_pct:.1f}% — tu peux acheter à {prix_achat}€."
    elif marge_pct >= 10:
        verdict = "⚠️  MARGE FAIBLE"
        conseil = f"Marge de {marge_pct:.1f}% — risqué si l'article met du temps à partir."
    elif marge_pct >= 0:
        verdict = "❌ PAS INTÉRESSANT"
        conseil = f"Marge de {marge_pct:.1f}% — à peine rentable. Négocie à la baisse."
    else:
        verdict = "🔴 PERTE ASSURÉE"
        conseil = f"Tu perdras {abs(profit):.2f}€. N'achète pas à ce prix."

    # Prix max à payer pour atteindre la marge cible
    prix_max_acceptable = (revenu_net / (1 + MARGE_MIN_PCT / 100)) - frais

    return {
        "verdict": verdict,
        "conseil": conseil,
        "nb_annonces": len(prices),
        "prix_median": round(mediane, 2),
        "prix_moyen": round(moyenne, 2),
        "ecart_type": round(ecart_type, 2),
        "prix_min": prix_min,
        "prix_max": prix_max,
        "prix_revente_cible": round(prix_revente_cible, 2),
        "commission_vinted": round(commission_vinted, 2),
        "revenu_net": round(revenu_net, 2),
        "prix_achat": prix_achat,
        "frais": frais,
        "cout_total": round(prix_total, 2),
        "profit": round(profit, 2),
        "marge_pct": round(marge_pct, 1),
        "prix_max_acceptable": round(max(0, prix_max_acceptable), 2),
    }


# ─────────────────────────────────────────────
#  AFFICHAGE
# ─────────────────────────────────────────────
def afficher(query: str, result: dict):
    sep = "─" * 50
    print(f"\n{sep}")
    print(f"  ANALYSE VINTED — {query.upper()}")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(sep)

    if "erreur" in result:
        print(f"\n  ❌ {result['erreur']}\n")
        return

    print(f"\n  📊 MARCHÉ ({result['nb_annonces']} annonces analysées)")
    print(f"     Médiane       : {result['prix_median']} €")
    print(f"     Moyenne       : {result['prix_moyen']} €")
    print(f"     Écart-type    : ± {result['ecart_type']} €")
    print(f"     Fourchette    : {result['prix_min']} € → {result['prix_max']} €")

    print(f"\n  💰 TON DEAL")
    print(f"     Prix achat    : {result['prix_achat']} €")
    print(f"     Frais divers  : {result['frais']} €")
    print(f"     Coût total    : {result['cout_total']} €")

    print(f"\n  📦 REVENTE ESTIMÉE")
    print(f"     Prix cible    : {result['prix_revente_cible']} € (médiane -10%)")
    print(f"     Commission    : -{result['commission_vinted']} €")
    print(f"     Revenu net    : {result['revenu_net']} €")

    print(f"\n  📈 RÉSULTAT")
    print(f"     Profit        : {result['profit']:+.2f} €")
    print(f"     Marge         : {result['marge_pct']:+.1f}%")
    print(f"     Max à payer   : {result['prix_max_acceptable']} € (pour {MARGE_MIN_PCT}% de marge)")

    print(f"\n  {result['verdict']}")
    print(f"  → {result['conseil']}")
    print(f"\n{sep}\n")


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Analyse la rentabilité d'un achat-revente sur Vinted."
    )
    parser.add_argument("recherche", type=str, help='Article à rechercher, ex: "nike air max 90"')
    parser.add_argument("--prix", type=float, required=True, help="Prix auquel tu veux acheter (€)")
    parser.add_argument("--frais", type=float, default=0.0, help="Frais annexes : livraison, nettoyage... (€)")
    parser.add_argument("--pages", type=int, default=3, help="Nombre de pages Vinted à analyser (défaut: 3)")
    parser.add_argument("--json", action="store_true", help="Sortie en JSON brut")

    args = parser.parse_args()

    print(f"\n🔍 Recherche Vinted : « {args.recherche} » ({args.pages} pages)...")
    items = fetch_vinted(args.recherche, pages=args.pages)

    if not items:
        print("\n❌ Aucune annonce récupérée. Vinted bloque peut-être la requête.")
        print("   → Essaie de relancer dans quelques minutes ou réduis le nombre de pages.")
        sys.exit(1)

    prices = extract_prices(items)
    result = analyse(prices, prix_achat=args.prix, frais=args.frais)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        afficher(args.recherche, result)


if __name__ == "__main__":
    main()
