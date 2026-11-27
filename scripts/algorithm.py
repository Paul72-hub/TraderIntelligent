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

# Stratégie par produit, choisie par backtest (voir DECISIONS.md) :
#   ("zscore", n)   : retour à la moyenne, moyenne/écart-type sur n ticks
#   ("momentum", n) : suivi de tendance, moyenne sur n ticks + sa pente
STRATEGIES = {
    "A": ("zscore", 48),    # cycle régulier ~48 ticks, pas de tendance
    "B": ("momentum", 10),  # tendance haussière par vagues ~100 ticks
    "C": ("zscore", 20),    # baisse + cycle rapide ~22 ticks
}
MOMENTUM_SLOPE_LAG = 5          # pente = moyenne actuelle vs moyenne d'il y a 5 ticks
BUY_PRIORITY = ["A", "C", "B"]  # répartition de l'argent entre achats (règle c, backtest portefeuille)

def fetch_json(url):
    resp = requests.get(url, proxies={"http": None, "https": None}, timeout=(10, 20))
    resp.raise_for_status()
    return resp.json()

# --- Les deux indicateurs ----------------------------------------------------
def zscore(prices, window):
    """À combien d'écarts-types de sa moyenne (sur `window` ticks) est le dernier prix ?
    None si pas assez d'historique ou prix parfaitement plat."""
    if len(prices) < window:
        return None
    recent = prices[-window:]
    std = st.pstdev(recent)
    if std == 0:
        return None
    return (prices[-1] - st.mean(recent)) / std

def momentum(prices, window, lag=MOMENTUM_SLOPE_LAG):
    """Renvoie (prix au-dessus de la moyenne ?, moyenne en hausse ?), ou None si historique court."""
    if len(prices) < window + lag:
        return None
    ma_now = st.mean(prices[-window:])
    ma_before = st.mean(prices[-window - lag:-lag])
    return prices[-1] > ma_now, ma_now > ma_before

# --- Le signal (la fonction demandée par le sujet) ----------------------------
def compute_signal(prices, strategy):
    """
    prices   : historique d'UN produit (du plus ancien au plus récent)
    strategy : ("zscore", n) ou ("momentum", n)
    Renvoie un float dans [-1, 1] : positif = achat, négatif = vente, 0 = rien.
    """
    kind, window = strategy
    if kind == "zscore":                      # retour à la moyenne
        z = zscore(prices, window)
        if z is None:
            return 0.0
        return max(-1.0, min(1.0, -z / 2))    # bas -> achat, haut -> vente, gradué
    if kind == "momentum":                    # suivi de tendance
        m = momentum(prices, window)
        if m is None:
            return 0.0
        above, rising = m
        if above and rising:
            return 1.0                        # tendance haussière confirmée
        if not above and not rising:
            return -1.0                       # tendance baissière confirmée
        return 0.0                            # signaux contradictoires : on attend
    raise ValueError(f"stratégie inconnue : {kind}")

# --- Répartition de l'argent entre les achats --------------------------------
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

def allocate(raw, money, prices_now):
    """Règle c : on sert les achats dans l'ordre BUY_PRIORITY ; chacun ne voit que
    l'argent LAISSÉ par les précédents (le garde du prof appliqué en cascade)."""
    final, money_left = {}, money
    for p in BUY_PRIORITY:
        final[p] = apply_budget_guard(raw[p], money_left, prices_now[p])
        if final[p] > 0:
            money_left -= 100 * final[p] * prices_now[p]
    return final

# --- Journal ------------------------------------------------------------------
def make_reason(p, prices, raw, final):
    """Phrase d'une ligne pour le journal de décisions."""
    kind, window = STRATEGIES[p]
    units = f"{abs(100 * final):.1f}".removesuffix(".0")   # 1.4 reste 1.4 (avant : arrondi à 1)
    if final > 0:
        # comparé au brut ARRONDI : 0.15 vs 0.1501 n'est pas une réduction (bug 27/11)
        action = f"achat {units}" + (" (réduit : argent)" if final < round(raw, 3) else "")
    elif final < 0:
        action = f"vente {units}"
    else:
        action = "rien (pas d'argent)" if raw > 0 else "rien"
    if kind == "zscore":
        z = zscore(prices, window)
        if z is None:
            return f"{p} : historique insuffisant, rien"
        position = "sous" if z < 0 else "au-dessus de"
        return f"{p} {position} sa moyenne {window} (z={z:+.2f}) → {action}"
    m = momentum(prices, window)
    if m is None:
        return f"{p} : historique insuffisant, rien"
    above, rising = m
    return (f"{p} {'au-dessus de' if above else 'sous'} sa moyenne {window}, "
            f"moyenne {'en hausse' if rising else 'en baisse'} → {action}")

def portfolio_value(holdings, last_prices):
    return holdings["money"] + sum(q * last_prices[p] for p, q in holdings["products"].items())

def log_history(row):
    """1 ligne par tick dans data/history.csv. Si le tick est déjà enregistré, la ligne
    est REMPLACÉE : elle garde la DERNIÈRE décision calculée, celle que le marché lira
    au tick suivant (incident 27/11 : la 1re version gardait un calcul périmé)."""
    HISTORY_CSV.parent.mkdir(exist_ok=True)
    rows = []
    if HISTORY_CSV.exists():
        with open(HISTORY_CSV, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    row = {k: str(v) for k, v in row.items()}
    if rows and rows[-1]["tick"] == row["tick"]:
        rows[-1] = row
        print(f"Tick {row['tick']} déjà enregistré : ligne mise à jour (dernière décision)")
    else:
        rows.append(row)
        print(f"Ajouté au journal : tick {row['tick']}")
    with open(HISTORY_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerows(rows)

def main():
    market = fetch_json(MARKET_URL)
    holdings = fetch_json(HOLDINGS_URL)
    products = market["products"]
    history = market["history"]

    series = {p: [row[p] for row in history] for p in products}
    prices_now = {p: series[p][-1] for p in products}
    raw = {p: compute_signal(series[p], STRATEGIES[p]) for p in products}
    final = allocate(raw, holdings["money"], prices_now)

    decision = {p: round(final[p], 3) for p in products}
    decision["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open("decision.json", "w", encoding="utf-8") as f:
        json.dump(decision, f, indent=2)
    print(f"Wrote decision.json: {decision}")

    # --- Historique pour le dashboard : 1 ligne par tick (colonnes inchangées) --
    last = history[-1]
    row = {"tick": last["t"], "tick_time": last["timestamp"], "run_time": decision["updated_at"]}
    for p in products:
        row[f"price_{p}"] = last[p]
    for p in products:
        kind, window = STRATEGIES[p]
        z = zscore(series[p], window) if kind == "zscore" else None
        row[f"z_{p}"] = "" if z is None else round(z, 3)   # vide pour B (momentum)
        row[f"signal_{p}"] = decision[p]
    row["money"] = round(holdings["money"], 2)
    for p in products:
        row[f"units_{p}"] = round(holdings["products"][p], 2)
    row["value"] = round(portfolio_value(holdings, last), 2)
    for b in BASELINES:
        row[f"value_{b}"] = round(portfolio_value(fetch_json(f"{TRADERS_URL}/{b}/holdings.json"), last), 2)
    row["reason"] = " | ".join(make_reason(p, series[p], raw[p], decision[p]) for p in products)
    log_history(row)

if __name__ == "__main__":
    main()
