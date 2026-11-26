import csv, json, time
import statistics as st
from pathlib import Path
import requests

# URLs fournies par l'organisateur (inscription sous l'id "paul_transon")
MARKET_URL = "https://raw.githubusercontent.com/exofri/ensim-trade-center/refs/heads/main/docs/data/market.json"
HOLDINGS_URL = "https://raw.githubusercontent.com/exofri/ensim-trade-center/refs/heads/main/traders/paul_transon/holdings.json"

TRADERS_URL = "https://raw.githubusercontent.com/exofri/ensim-trade-center/refs/heads/main/traders"
BASELINES = ["random_trader", "random_buyer", "random_seller"]  # seuls autres portefeuilles lus (décision confidentialité)
HISTORY_CSV = Path("data/history.csv")

MIN_MONEY_RESERVE = 50 # never let a buy signal spend below this much money

# Réglage par produit, choisi par backtest (voir DECISIONS.md) :
#   fenêtre = nombre de ticks pour la moyenne et l'écart-type ; None = pas de signal (on garde)
WINDOWS = {
    "A": 48,    # cycle régulier ~48 ticks  -> retour à la moyenne
    "B": None,  # tendance haussière        -> on garde, pas de trading
    "C": 20,    # baisse + cycle ~22 ticks  -> retour à la moyenne
}

def fetch_json(url):
    resp = requests.get(url, proxies={"http": None, "https": None}, timeout=(10, 20))
    resp.raise_for_status()
    return resp.json()

def zscore(prices, window):
    """À combien d'écarts-types de sa moyenne (sur `window` ticks) est le dernier prix ?
    None si pas de stratégie, pas assez d'historique ou prix parfaitement plat."""
    if window is None or len(prices) < window:
        return None
    recent = prices[-window:]
    std = st.pstdev(recent)
    if std == 0:
        return None
    return (prices[-1] - st.mean(recent)) / std

def compute_signal(prices, window):
    """
    Retour à la moyenne par z-score.
    prices : historique d'UN produit (du plus ancien au plus récent)
    window : nombre de ticks utilisés pour la moyenne ; None = on ne trade pas
    Renvoie un float dans [-1, 1] : bas par rapport à la normale -> achat, haut -> vente.
    """
    z = zscore(prices, window)
    if z is None:
        return 0.0                       # pas de stratégie / pas assez d'historique
    return max(-1.0, min(1.0, -z / 2))   # signe inversé + borné à [-1, 1]

def make_reason(p, z, final_signal):
    """Phrase d'une ligne pour le journal de décisions."""
    if WINDOWS.get(p) is None:
        return f"{p} gardé (stratégie conservation)"
    if z is None:
        return f"{p} : historique insuffisant, rien"
    position = "sous" if z < 0 else "au-dessus de"
    if final_signal > 0:
        action = f"achat {100 * final_signal:.0f}"
    elif final_signal < 0:
        action = f"vente {-100 * final_signal:.0f}"
    else:
        action = "rien (budget)" if z < 0 else "rien"
    return f"{p} {position} sa moyenne (z={z:+.2f}) → {action}"

def portfolio_value(holdings, last_prices):
    return holdings["money"] + sum(q * last_prices[p] for p, q in holdings["products"].items())

def log_history(row):
    """Ajoute une ligne à data/history.csv, sauf si ce tick y est déjà (1 ligne par tick)."""
    HISTORY_CSV.parent.mkdir(exist_ok=True)
    exists = HISTORY_CSV.exists()
    if exists:
        with open(HISTORY_CSV, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        if rows and rows[-1]["tick"] == str(row["tick"]):
            print(f"Tick {row['tick']} déjà enregistré, historique inchangé")
            return
    with open(HISTORY_CSV, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not exists:
            writer.writeheader()
        writer.writerow(row)
    print(f"Ajouté au journal : tick {row['tick']}")

def apply_budget_guard(raw_signal, money, price, reserve=MIN_MONEY_RESERVE):
    # A buy signal (positive) that would spend into the reserve gets scaled down,
    # not silently zeroed out -- you still act on the signal, just smaller. A sell
    # signal is never touched here: selling only ever adds money, never risks it.
    if raw_signal <= 0:
        return raw_signal
    if money <= reserve:
        return 0.0
    max_affordable_units = (money - reserve) / price
    desired_units = 100 * raw_signal
    if desired_units <= max_affordable_units:
        return raw_signal
    return round(max_affordable_units / 100, 3)

def main():
    market = fetch_json(MARKET_URL)
    holdings = fetch_json(HOLDINGS_URL)
    products = market["products"]
    history = market["history"]

    decision, zs = {}, {}
    for p in products:
        prices = [row[p] for row in history]
        zs[p] = zscore(prices, WINDOWS.get(p))
        raw = compute_signal(prices, WINDOWS.get(p))
        current_price = prices[-1] if prices else 0
        decision[p] = round(apply_budget_guard(raw, holdings["money"], current_price), 3)

    decision["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open("decision.json", "w", encoding="utf-8") as f:
        json.dump(decision, f, indent=2)
    print(f"Wrote decision.json: {decision}")

    # --- Historique pour le dashboard : 1 ligne par tick ---------------------
    last = history[-1]
    row = {"tick": last["t"], "tick_time": last["timestamp"], "run_time": decision["updated_at"]}
    for p in products:
        row[f"price_{p}"] = last[p]
    for p in products:
        row[f"z_{p}"] = "" if zs[p] is None else round(zs[p], 3)
        row[f"signal_{p}"] = decision[p]
    row["money"] = round(holdings["money"], 2)
    for p in products:
        row[f"units_{p}"] = round(holdings["products"][p], 2)
    row["value"] = round(portfolio_value(holdings, last), 2)
    for b in BASELINES:
        row[f"value_{b}"] = round(portfolio_value(fetch_json(f"{TRADERS_URL}/{b}/holdings.json"), last), 2)
    row["reason"] = " | ".join(make_reason(p, zs[p], decision[p]) for p in products)
    log_history(row)

if __name__ == "__main__":
    main()
