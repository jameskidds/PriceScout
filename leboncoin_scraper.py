"""
leboncoin_scraper.py — LeBonCoin via page HTML + __NEXT_DATA__ avec curl_cffi
Supporte la pagination (plusieurs pages de résultats).
"""

import re
import json
from urllib.parse import quote
from curl_cffi import requests as cffi_requests

BASE_URL = "https://www.leboncoin.fr"
PER_PAGE = 35


def fetch_leboncoin(query: str, pages: int = 3) -> list:
    query_clean = " ".join(query.split())

    session = cffi_requests.Session(impersonate="chrome124")

    try:
        session.get(BASE_URL + "/", timeout=10)
    except Exception:
        pass

    all_items = []
    seen_urls = set()

    for page in range(pages):
        offset = page * PER_PAGE
        url = (
            f"{BASE_URL}/recherche"
            f"?text={quote(query_clean)}"
            f"&offset={offset}"
        )

        try:
            resp = session.get(url, timeout=20)
            if resp.status_code != 200:
                break
        except Exception:
            break

        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                      resp.text, re.DOTALL)
        if not m:
            break

        try:
            data = json.loads(m.group(1))
            ads  = data["props"]["pageProps"]["searchData"]["ads"]
        except Exception:
            break

        if not ads:
            break

        new_items = 0
        for ad in ads:
            title = ad.get("subject") or ""
            if not title:
                continue
            price_list = ad.get("price") or []
            try:
                price = float(price_list[0])
            except (TypeError, ValueError, IndexError):
                # fallback sur price_cents (en centimes)
                cents = ad.get("price_cents")
                if cents and cents > 0:
                    price = round(cents / 100, 2)
                else:
                    continue
            if not (1.0 < price < 5000.0):
                continue

            ad_url = ad.get("url") or ""
            if ad_url and not ad_url.startswith("http"):
                ad_url = BASE_URL + ad_url

            if ad_url in seen_urls:
                continue
            seen_urls.add(ad_url)

            images = ad.get("images") or {}
            thumbs = images.get("urls_thumb") or images.get("urls") or []
            photo  = thumbs[0] if thumbs else ""

            # Date de publication → timestamp Unix
            date_str = ad.get("first_publication_date") or ad.get("index_date") or ""
            date_ts  = 0
            if date_str:
                import re as _re
                m = _re.search(r"(\d{4}-\d{2}-\d{2})", date_str)
                if m:
                    from datetime import datetime
                    try:
                        date_ts = int(datetime.strptime(m.group(1), "%Y-%m-%d").timestamp())
                    except Exception:
                        date_ts = 0

            description = (ad.get("body") or "").strip()

            all_items.append({
                "source":      "LeBonCoin",
                "titre":       title,
                "prix":        round(price, 2),
                "url":         ad_url,
                "photo":       photo,
                "date_ts":     date_ts,
                "description": description,
            })
            new_items += 1

        if new_items == 0:
            break  # plus de nouveaux résultats

    return all_items
