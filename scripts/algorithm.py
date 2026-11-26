import json, time
import statistics as st
import requests

# URLs fournies par l'organisateur (inscription sous l'id "paul_transon")
MARKET_URL = "https://raw.githubusercontent.com/exofri/ensim-trade-center/refs/heads/main/docs/data/market.json"
HOLDINGS_URL = "https://raw.githubusercontent.com/exofri/ensim-trade-center/refs/heads/main/traders/paul_transon/holdings.json"

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

def compute_signal(prices, window):
    """
    Retour à la moyenne par z-score.
    prices : historique d'UN produit (du plus ancien au plus récent)
    window : nombre de ticks utilisés pour la moyenne ; None = on ne trade pas
    Renvoie un float dans [-1, 1] : bas par rapport à la normale -> achat, haut -> vente.
    """
    if window is None or len(prices) < window:
        return 0.0                       # pas de stratégie ou pas assez d'historique
    recent = prices[-window:]
    mean = st.mean(recent)
    std = st.pstdev(recent)
    if std == 0:
        return 0.0                       # prix parfaitement plat : aucune information
    z = (prices[-1] - mean) / std        # à combien d'écarts-types de la normale ?
    return max(-1.0, min(1.0, -z / 2))   # signe inversé + borné à [-1, 1]

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

    decision = {}
    for p in products:
        prices = [row[p] for row in history]
        raw = compute_signal(prices, WINDOWS.get(p))
        current_price = prices[-1] if prices else 0
        decision[p] = round(apply_budget_guard(raw, holdings["money"], current_price), 3)

    decision["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open("decision.json", "w", encoding="utf-8") as f:
        json.dump(decision, f, indent=2)
    print(f"Wrote decision.json: {decision}")

if __name__ == "__main__":
    main()
