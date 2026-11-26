"""Reconstruit, UNE FOIS, la valeur passée de mon portefeuille et des 3 baselines.

Source : l'historique Git du dépôt de l'organisateur. Chaque commit « Market tick »
met à jour tous les traders/<id>/holdings.json ; on relit la version de chaque commit
et on la valorise aux prix du tick correspondant.
Sortie : data/backfill.csv (1 ligne par tick). Le dashboard l'affiche avant data/history.csv.

Usage : python -X utf8 scripts/backfill_values.py   (depuis la racine du dépôt)
"""
import csv
from bisect import bisect_right
from pathlib import Path

import requests

REPO = "exofri/ensim-trade-center"
API = f"https://api.github.com/repos/{REPO}"
RAW = f"https://raw.githubusercontent.com/{REPO}"
ME = "paul_transon"
BASELINES = ["random_trader", "random_buyer", "random_seller"]  # décision confidentialité : rien d'autre
START = {"money": 1000.0, "products": {"A": 1000.0, "B": 1000.0, "C": 1000.0}}  # panier de départ
OUT = Path("data/backfill.csv")

session = requests.Session()
session.trust_env = False  # ignore les proxys système (même logique que fetch_json)


def get_json(url):
    r = session.get(url, timeout=(10, 30))
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def value(holdings, prices):
    return holdings["money"] + sum(q * prices[p] for p, q in holdings["products"].items())


# 1) Les prix de tous les ticks (version actuelle de market.json)
history = get_json(f"{RAW}/refs/heads/main/docs/data/market.json")["history"]
tick_times = [r["timestamp"] for r in history]

# 2) La liste des commits « Market tick » (via le fichier d'une baseline)
commits, page = [], 1
while True:
    batch = get_json(f"{API}/commits?path=traders/random_trader/holdings.json"
                     f"&per_page=100&page={page}")
    if not batch:
        break
    commits += batch
    page += 1
commits.reverse()  # du plus ancien au plus récent
print(f"{len(commits)} commits à relire, {len(history)} ticks de prix")

# 3) Pour chaque commit : relire les holdings de l'époque et valoriser
rows = {}
for i, c in enumerate(commits, 1):
    sha, date = c["sha"], c["commit"]["committer"]["date"]
    idx = bisect_right(tick_times, date) - 1  # dernier tick antérieur au commit
    if idx < 0:
        continue
    tick = history[idx]
    row = {"tick": tick["t"], "tick_time": tick["timestamp"]}
    mine = get_json(f"{RAW}/{sha}/traders/{ME}/holdings.json") or START  # avant inscription
    row["value"] = round(value(mine, tick), 2)
    row["value_hold"] = round(value(START, tick), 2)
    for b in BASELINES:
        h = get_json(f"{RAW}/{sha}/traders/{b}/holdings.json")
        row[f"value_{b}"] = round(value(h, tick), 2) if h else ""
    rows[tick["t"]] = row  # si 2 commits pour le même tick, le plus récent l'emporte
    if i % 50 == 0:
        print(f"  {i}/{len(commits)} commits relus")

OUT.parent.mkdir(exist_ok=True)
with open(OUT, "w", encoding="utf-8", newline="") as f:
    fields = ["tick", "tick_time", "value", "value_hold"] + [f"value_{b}" for b in BASELINES]
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows[t] for t in sorted(rows))
print(f"Écrit {OUT} : {len(rows)} ticks")
