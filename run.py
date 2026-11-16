import argparse, io, json, urllib.request, zipfile
from pathlib import Path
import numpy as np
import pandas as pd

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
INTERVALS = ("15m", "1h", "4h", "1d")
STRATEGIES = ("ema_rsi", "rsi", "macd", "breakout")
COLS = ["time","open","high","low","close","volume","close_time","quote_volume","trades","buy_base","buy_quote","ignore"]

def download(symbol, interval, year, months):
    frames = []
    for month in months:
        tag = f"{year}-{month:02d}"
        url = f"https://data.binance.vision/data/spot/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{tag}.zip"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MV-Crypto-Research/1.0"})
            with urllib.request.urlopen(req, timeout=40) as response:
                with zipfile.ZipFile(io.BytesIO(response.read())) as z:
                    with z.open(next(n for n in z.namelist() if n.endswith(".csv"))) as f:
                        df = pd.read_csv(f, header=None, names=COLS, usecols=range(6))
            df["time"] = pd.to_datetime(pd.to_numeric(df["time"]), unit="ms" if year < 2025 else "us", utc=True)
            for c in ("open","high","low","close","volume"):
                df[c] = pd.to_numeric(df[c], errors="coerce")
            frames.append(df.dropna())
            print("Downloaded", symbol, interval, tag, len(df), flush=True)
        except Exception as exc:
            print("FAILED", url, str(exc), flush=True)
            return pd.DataFrame()
    return pd.concat(frames).drop_duplicates("time").sort_values("time").reset_index(drop=True)

def indicators(d):
    d = d.copy()
    c = d.close
    d["ema21"] = c.ewm(span=21, adjust=False).mean()
    d["ema55"] = c.ewm(span=55, adjust=False).mean()
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    d["rsi"] = 100 - 100/(1 + up/down.replace(0, np.nan))
    d["macd"] = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    d["signal"] = d.macd.ewm(span=9, adjust=False).mean()
    tr = pd.concat([d.high-d.low, (d.high-c.shift()).abs(), (d.low-c.shift()).abs()], axis=1).max(axis=1)
    d["atr"] = tr.ewm(alpha=1/14, adjust=False).mean()
    d["high20"] = d.high.shift().rolling(20).max()
    return d

def signal(d, j, strategy):
    if j < 60: return False
    p, prev = d.iloc[j], d.iloc[j-1]
    if not np.isfinite(p.rsi) or not np.isfinite(p.atr): return False
    if strategy == "ema_rsi":
        return bool(p.ema21 > p.ema55 and p.close > p.ema21 and p.rsi > 52 and prev.ema21 <= prev.ema55)
    if strategy == "rsi":
        return bool(prev.rsi <= 30 and p.rsi > 30 and p.close > p.ema55)
    if strategy == "macd":
        return bool(prev.macd <= prev.signal and p.macd > p.signal and p.close > p.ema55)
    return bool(p.close > p.high20 and prev.close <= prev.high20 and p.close > p.ema55)

def simulate(d, strategy, start, end, initial=10000., fee=.001, slip=.0005):
    cash, qty, stop, take = initial, 0., 0., 0.
    pnls, equity = [], []
    entry_equity = 0.
    for i in range(start, end):
        bar = d.iloc[i]
        if qty:
            exit_price = None
            if bar.open <= stop or bar.open >= take:
                exit_price = bar.open * (1-slip)
            elif bar.low <= stop:
                exit_price = stop * (1-slip)
            elif bar.high >= take:
                exit_price = take * (1-slip)
            if exit_price is not None:
                cash += qty*exit_price*(1-fee)
                pnls.append(cash-entry_equity)
                qty = 0.
        # Signal only uses the previous fully closed candle; fill at current open.
        if not qty and signal(d, i-1, strategy):
            atr = float(d.atr.iloc[i-1])
            buy = float(bar.open)*(1+slip)
            distance = 2*atr
            if np.isfinite(distance) and distance > 0:
                q = min((cash*.01)/distance, cash/(buy*(1+fee)))
                if q > 0:
                    entry_equity = cash
                    cash -= q*buy*(1+fee)
                    qty = q
                    stop = buy-distance
                    take = buy+3*atr
        equity.append(cash+qty*float(bar.close))
    if qty:
        cash += qty*float(d.close.iloc[end-1])*(1-slip)*(1-fee)
        pnls.append(cash-entry_equity)
        equity[-1] = cash
    pnl = np.asarray(pnls)
    curve = np.asarray(equity)
    peak = np.maximum.accumulate(np.r_[initial, curve])[1:]
    losses = -pnl[pnl<0].sum()
    wins = pnl[pnl>0].sum()
    return dict(returns_pct=round((cash/initial-1)*100,3),
        trades=len(pnl),
        win_rate_pct=round(float((pnl>0).mean()*100),2) if len(pnl) else None,
        profit_factor=round(float(wins/losses),3) if losses>0 else None,
        max_drawdown_pct=round(float(np.min(curve/peak-1)*100),3),
        buy_hold_pct=round(float((d.close.iloc[end-1]/d.open.iloc[start]-1)*100),3))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--months", default="1,2,3,4,5,6,7,8,9,10,11,12")
    args = ap.parse_args()
    months = [int(v) for v in args.months.split(",")]
    output = Path("results")
    output.mkdir(exist_ok=True)
    rows, missing = [], []
    for symbol in SYMBOLS:
        for interval in INTERVALS:
            d = download(symbol, interval, args.year, months)
            if len(d) < 250:
                missing.append(f"{symbol} {interval}")
                continue
            d = indicators(d)
            cut = int(len(d)*.7)
            for strategy in STRATEGIES:
                for sample, lo, hi in (("train", 60, cut), ("test", cut, len(d))):
                    rows.append(dict(symbol=symbol, interval=interval, strategy=strategy,
                        sample=sample, start=str(d.time.iloc[lo]), end=str(d.time.iloc[hi-1]),
                        bars=hi-lo, **simulate(d, strategy, lo, hi)))
    pd.DataFrame(rows).to_csv(output/"backtest_results.csv", index=False)
    (output/"status.json").write_text(json.dumps(dict(year=args.year, missing=missing,
        evaluations=len(rows), status="partial" if missing else "complete"), indent=2))
    print("Evaluations:", len(rows), "Missing:", missing, flush=True)
    if missing: raise SystemExit(1)

if __name__ == "__main__":
    main()
