#!/usr/bin/env python3
"""
MS ALGO v1 — GOLD-ONLY (11 production systems) — 1 MONTH LIVE TEST, 1 LOT GOLDPETAL.

Kaam kaise karta hai (Stage-1 semi-manual):
  1) Data refresh (yfinance: GC=F, SI=F, DXY, GVZ, TNX, USDINR) -> panel ke aage attach
  2) 11 production systems ke signals (TierC K=4 book) nikalta hai
  3) Har signal ka ORDER TICKET banata hai: entry / target / stop (₹ per gram me)
  4) Open positions ko track karta hai (stop/target/time-exit) aur batata hai kya karna hai
  5) Journal maintain karta hai (1-month test ka record)

Aapka kaam: 9:00 AM par sheet dekhna, Dhan app me 1 lot ka order lagana, aur fill price algo me daalna.

Commands:
  update                 data refresh (yfinance)
  scan                   signals -> pending orders + action sheet
  fill ID --price 13950  order fill hua -> position khul gayi
  skip ID                order skip kiya (jaise 1%+ gap up)
  close ID --price ...   position band -> journal me
  manage                 open positions ka status + exit advice
  run                    sab kuch (update + scan + manage + sheet)  <-- roz yahi chalao
  report                 1-month test ka scoreboard
  status                 config + open positions + pending orders
"""
import os, sys, json, argparse, datetime as dt
from argparse import Namespace
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))     # GitHub repo folder
MS = ROOT
ADIR = f"{MS}/data/algo"
PANEL = f"{MS}/data/panel_min.csv"
PARITY = f"{MS}/data/mcx_parity_daily.csv"
BOOK_VER = (os.environ.get("MS_BOOK", "v5") or "v5").strip().lower()   # v5 = redesign (16-Oct-2026, phase-4)
SYS_CSV = f"{MS}/data/ms_gold_prod_systems_{BOOK_VER}.csv"
SCREEN_CSV = f"{MS}/data/ms_gold_prod_screen_{BOOK_VER}.csv"
TRADES_CSV = f"{MS}/data/ms_gold_prod_trades.csv"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
OZ2G = 31.1035

DEFAULTS = dict(capital=30167.0, lots=1, max_open=2, skip_gap_pct=1.0,
                gap_dead_lo=0.5, gap_dead_hi=1.0, gap_hard=2.5,
                quick_book=True, quick_book_day=5, quick_book_pct=1.5,
                silver_signals=True, silver_contract="SILVERMIC", silver_lot_kg=1.0,
                silver_margin_per_lot=19082.0, silver_sec_id="562058",
                contract="GOLDPETAL", gram_per_lot=1.0, cost_inr_per_lot=46.0,
                allow_short=False, test_start=None)

ORDER_COLS = ["order_id", "created_on", "signal_date", "entry_day", "system", "family", "side",
              "rule", "lots", "contract", "contract_sec_id", "contract_expiry", "ref_px", "skip_above",
              "gap_lo_px", "gap_hi_px", "gap_hard_px",
              "target_px", "stop_px", "tgt_pct", "stop_pct", "max_hold", "status", "note"]
POS_COLS = ["order_id", "system", "family", "side", "entry_date", "entry_px", "lots", "target_px",
            "stop_px", "max_hold", "last_px", "last_date", "days_held", "unreal_pct", "unreal_inr",
            "status", "note"]
JRN_COLS = ["order_id", "system", "family", "side", "entry_date", "entry_px", "exit_date", "exit_px",
            "lots", "pnl_inr", "pnl_pct", "why", "days_held", "cost_inr", "note"]


# ---------------------------------------------------------------- helpers
def now_ist():
    return dt.datetime.now(IST)


def _next_weekday(d):
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


def next_entry_day(now=None):
    """Agla MCX trading din (09:00 IST se pehle run kiya to aaj hi)."""
    now = now or now_ist()
    d = now.date() if now.time() < dt.time(9, 0) else (now.date() + dt.timedelta(days=1))
    return _next_weekday(d)


def _bar_complete(bar_date, now=None):
    """COMEX bar dated D ~02:30 IST (D+1) par band hota hai; 02:45 IST ke baad 'complete'."""
    now = now or now_ist()
    return now >= dt.datetime.combine(bar_date + dt.timedelta(days=1), dt.time(2, 45), tzinfo=now.tzinfo)


def _next_oid(orders):
    if not len(orders):
        return 1
    ids = pd.to_numeric(orders.order_id, errors="coerce").dropna()
    return int(ids.max()) + 1 if len(ids) else 1


def ensure_dirs():
    os.makedirs(ADIR, exist_ok=True)
    os.makedirs(f"{MS}/outputs", exist_ok=True)


def cfg_load():
    ensure_dirs()
    p = f"{ADIR}/config.json"
    c = dict(DEFAULTS)
    if os.path.exists(p):
        c.update(json.load(open(p)))
    return c


def cfg_save(c):
    ensure_dirs()
    json.dump(c, open(f"{ADIR}/config.json", "w"), indent=1)


def _read(path, cols):
    if os.path.exists(path) and os.path.getsize(path) > 5:
        df = pd.read_csv(path, dtype=str)
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        return df[cols]
    return pd.DataFrame(columns=cols)


def _write(df, path, cols):
    ensure_dirs()
    df = df.copy()
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df[cols].to_csv(path, index=False)


def orders_load(): return _read(f"{ADIR}/orders.csv", ORDER_COLS)
def pos_load():    return _read(f"{ADIR}/positions.csv", POS_COLS)
def jrn_load():    return _read(f"{ADIR}/journal.csv", JRN_COLS)


def orders_save(d): _write(d, f"{ADIR}/orders.csv", ORDER_COLS)
def pos_save(d):    _write(d, f"{ADIR}/positions.csv", POS_COLS)
def jrn_save(d):    _write(d, f"{ADIR}/journal.csv", JRN_COLS)


def fnum(v, d=np.nan):
    try:
        return float(v)
    except Exception:
        return d


def gap_band(cfg, ref):
    """Entry-gap rule ke price levels (improvement-phase2, 16-Oct-2026).
    Backtest: gap (0.5%, 1.0%] = dead-zone (144 trades, 58.3% win, +0.11%), 2.5%+ = -1.93% avg."""
    lo = ref * (1 + float(cfg.get("gap_dead_lo", 0.5) or 0.5) / 100)
    hi = ref * (1 + float(cfg.get("gap_dead_hi", 1.0) or 1.0) / 100)
    hard = ref * (1 + float(cfg.get("gap_hard", 2.5) or 2.5) / 100)
    return lo, hi, hard


def gap_verdict(cfg, ref, open_px):
    """(verdict, reason) — open price ko ref (signal close) se compare karta hai."""
    lo, hi, hard = gap_band(cfg, ref)
    g = (open_px / ref - 1) * 100 if ref else 0.0
    if open_px >= hard:
        return "SKIP", f"+{g:.2f}% gap (2.5%+ upar = bahut bada jump)"
    if lo < open_px <= hi:
        return "SKIP", f"+{g:.2f}% gap (0.5-1.0% dead-zone)"
    return "OK", f"{g:+.2f}% gap"


# ---------------------------------------------------------------- market data
def refresh_market(quiet=False):
    """yfinance se latest daily bars -> data/algo/live_tail.csv (panel ke last 5 din overwrite karke)."""
    import yfinance as yf
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    parity = pd.read_csv(PARITY, index_col=0, parse_dates=True)
    last = panel.index[-1]
    tickers = {"gcf": "GC=F", "sif": "SI=F", "dxy": "DX-Y.NYB", "gvz": "^GVZ",
               "us10y": "^TNX", "usdinr": "USDINR=X"}
    data = {}
    for k, t in tickers.items():
        try:
            d = yf.download(t, period="6mo", interval="1d", progress=False, auto_adjust=False)
        except Exception as e:
            print(f"  ! {t}: {e}"); continue
        if d is None or len(d) == 0:
            continue
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        data[k] = d
    if "gcf" not in data:
        print("  ! gold data nahi mila (internet?). Panel ke aakhri data se chal raha hoon.")
        return None
    g = data["gcf"]
    dates = [d for d in g.index if d >= (last - pd.Timedelta(days=7))]
    rows = {}
    for d in dates:
        r = {}
        r["gold_usd"] = float(g.loc[d, "Close"]); r["gold_open_usd"] = float(g.loc[d, "Open"])
        r["gold_high_usd"] = float(g.loc[d, "High"]); r["gold_low_usd"] = float(g.loc[d, "Low"])
        for k, tag in (("sif", "silver"), ("dxy", "dxy"), ("gvz", "gvz"), ("us10y", "us10y"), ("usdinr", "usdinr")):
            if k in data and d in data[k].index:
                r[tag] = float(data[k].loc[d, "Close"])
                if k == "sif":
                    try:
                        r["silver_open_usd"] = float(data[k].loc[d, "Open"])
                    except Exception:
                        pass
        rows[d] = r
    t = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    t = t.rename(columns={"silver": "silver_usd"})
    for c in ("silver_usd", "silver_open_usd", "dxy", "gvz", "us10y", "usdinr"):
        if c not in t.columns:
            t[c] = np.nan
    t["silver_open_usd"] = t["silver_open_usd"] = t["silver_open_usd"].ffill()
    t["silver_usd"] = t["silver_usd"].ffill()
    t["gvz"] = t["gvz"].ffill()
    t["dxy"] = t["dxy"].ffill().fillna(float(panel["dxy"].iloc[-1]))
    t["us10y"] = t["us10y"].ffill()
    t["usdinr"] = t["usdinr"].ffill().fillna(float(parity["usdinr"].iloc[-1]))
    # macro carry-forward (monthly/weekly series -> panel ka last known)
    t["cpi_yoy_d"] = panel["cpi_yoy_d"].iloc[-1]
    t["real10y_synth"] = t["us10y"] - t["cpi_yoy_d"]
    t["gs_ratio"] = t["gold_usd"] / t["silver_usd"]
    t["gold_duty_pct"] = parity["gold_duty_pct"].iloc[-1]
    t["indirect_tax_pct"] = parity["indirect_tax_pct"].iloc[-1]
    t.index.name = "date"
    t.to_csv(f"{ADIR}/live_tail.csv")
    if not quiet:
        print(f"  data refresh OK — {len(t)} rows ({t.index[0].date()} -> {t.index[-1].date()}), "
              f"gold ${t.gold_usd.iloc[-1]:,.1f} | DXY {t.dxy.iloc[-1]:.2f} | USDINR {t.usdinr.iloc[-1]:.3f}")
    return t


def build_frame(cfg, use_tail=True):
    """Panel (+live tail) -> backtest-identical frame: INR prices, clean(), indicators, 11 masks.

    Freeze rule: jo rows panel_v3 me hain unke macro/state/percentile columns panel se hi liye jaate hain
    (taki algo bilkul wahi signals de jo published book me hain); sirf naye (tail) rows live compute hote hain.
    """
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    parity = pd.read_csv(PARITY, index_col=0, parse_dates=True)
    tail = None
    tp = f"{ADIR}/live_tail.csv"
    if use_tail and os.path.exists(tp):
        t = pd.read_csv(tp, index_col=0, parse_dates=True)
        tail = t if len(t) else None
    hist_idx = panel.index[panel.gold_fut_close.notna()]
    df = panel.loc[hist_idx].copy()
    if tail is not None:
        df = df[~df.index.isin(tail.index)]
        df = pd.concat([df, tail]).sort_index()
    is_hist = df.index.isin(panel.index)
    # --- USD OHLC (gold_fut_* ya live gold_*_usd)
    def pick(cands):
        out = None
        for c in cands:
            if c in df.columns:
                s = pd.to_numeric(df[c], errors="coerce")
                out = s if out is None else out.fillna(s)
        return out
    op_u = pick(["gold_fut_open", "gold_open_usd"])
    hi_u = pick(["gold_fut_high", "gold_high_usd"])
    lo_u = pick(["gold_fut_low", "gold_low_usd"])
    px_u = pick(["gold_fut_close", "gold_usd"])
    # --- macro columns: history = panel frozen, tail = live
    df["gold_usd"] = px_u
    df["gs_ratio"] = pd.to_numeric(pick(["gs_ratio"]), errors="coerce")
    df["dxy"] = pd.to_numeric(pick(["dxy"]), errors="coerce")
    df["gvz"] = pd.to_numeric(pick(["gvz"]), errors="coerce")
    df["us10y"] = pd.to_numeric(pick(["us10y"]), errors="coerce")
    df["cpi_yoy_d"] = pd.to_numeric(pick(["cpi_yoy_d"]), errors="coerce")
    df["gold_duty_pct"] = pd.to_numeric(pick(["gold_duty_pct"]), errors="coerce")
    df["indirect_tax_pct"] = pd.to_numeric(pick(["indirect_tax_pct"]), errors="coerce")
    live_mask = ~is_hist
    # computed (live) versions
    df["gs_ratio"] = df.gs_ratio.fillna(df.gold_usd / pd.to_numeric(pick(["silver_usd"]), errors="coerce"))
    df["real10y_synth"] = df.us10y - df.cpi_yoy_d
    mz = df.real10y_synth.rolling(252, min_periods=60)
    z_calc = (df.real10y_synth - mz.mean()) / mz.std(ddof=0)
    st_calc = pd.Series("COIL", index=df.index, dtype=object)
    g = df.gold_usd
    m50, m200 = g.rolling(50).mean(), g.rolling(200).mean()
    st_calc[(g > m50) & (m50 > m200)] = "UP"
    st_calc[(g < m50) & (m50 < m200)] = "DOWN"
    st_calc[m200.isna()] = "n/a"
    df["gold_ma50"], df["gold_ma200"] = m50, m200
    def pctile(col):
        s = df[col].ffill()
        return s.rolling(252, min_periods=100).apply(lambda x: (x.iloc[-1] >= x).mean() * 100 if pd.notna(x.iloc[-1]) else np.nan, raw=False)
    pct_calc = {"dxy_pct_v3": pctile("dxy"), "gs_pct_v3": pctile("gs_ratio"), "gvz_pct_v3": pctile("gvz")}
    # freeze history from panel
    freeze = {"state": "gold_state", "real10y_synth_z": "real10y_synth_z", "dxy_pct_v3": "dxy_pct_v3",
              "gs_pct_v3": "gs_pct_v3", "gvz_pct_v3": "gvz_pct_v3", "gs_ratio": "gs_ratio", "dxy": "dxy",
              "gvz": "gvz", "us10y": "us10y", "cpi_yoy_d": "cpi_yoy_d"}
    df["state"] = st_calc
    df["real10y_synth_z"] = z_calc
    for k, v in pct_calc.items():
        df[k] = v
    for col, pcol in freeze.items():
        if pcol in panel.columns:
            common = df.index[is_hist]
            df.loc[common, col] = panel.loc[common, pcol].ffill().values
    # TAIL FIX (16-Oct): jo macro live fetch nahi hote (jaise mm_pct_v3) unhe panel ke last value se aage badhao
    for col, pcol in (("mm_pct_v3", "mm_pct_v3"), ("mm_pct", "mm_pct_v3")):
        if pcol in panel.columns:
            lastv = pd.to_numeric(panel[pcol], errors="coerce").dropna()
            if len(lastv):
                if col not in df.columns:
                    df[col] = np.nan
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(float(lastv.iloc[-1]))
    df.loc[df.state.isna(), "state"] = st_calc[df.state.isna()]
    # --- INR conversion
    p = parity[["usdinr", "gold_duty_pct", "indirect_tax_pct"]].reindex(df.index).ffill()
    for c in ("usdinr", "gold_duty_pct", "indirect_tax_pct"):
        base = pd.to_numeric(df[c], errors="coerce") if c in df.columns else pd.Series(np.nan, index=df.index)
        df[c] = base.reindex(df.index).fillna(p[c]).ffill()
    sc = df.usdinr * (1 + df.gold_duty_pct / 100) * (1 + df.indirect_tax_pct / 100) / OZ2G
    df["op"] = op_u * sc; df["hi"] = hi_u * sc; df["lo"] = lo_u * sc; df["px"] = px_u * sc
    df["sil_inr"] = pd.to_numeric(pick(["silver_usd"]), errors="coerce") * sc * 1000
    if use_tail and tail is not None:
        try:
            from ms_gold_inr import load_silver_inr
            si = load_silver_inr().px.reindex(df.index)
            df["sil_inr"] = df["sil_inr"].fillna(si)
            extra = si.reindex(df.index)[is_hist]
            df.loc[df.index[is_hist], "sil_inr"] = extra.values
        except Exception:
            pass
    df["gs_pct"] = df.gs_ratio.rank(pct=True) * 100      # book jaisa: clean se PEHLE (pre-clean frame par rank)
    # --- clean() (ms_gold_only_book jaisa)
    o, h, l, c = df.op, df.hi, df.lo, df.px
    flat = (o == h) & (h == l) & (l == c)
    df = df.loc[~flat].copy()
    bad = (df.op > df.hi + 1e-9) | (df.op < df.lo - 1e-9)
    df.loc[bad, "op"] = df.loc[bad, "op"].clip(lower=df.loc[bad, "lo"], upper=df.loc[bad, "hi"])
    big = (df.op / df.px.shift(1) - 1).abs() > 0.04
    df.loc[big, "op"] = df.loc[big, "px"].shift(1)
    df = df.dropna(subset=["op", "hi", "lo", "px"])
    # --- indicators (enrich, ms_gold_only_book jaisa)
    C, H, L, O = df.px, df.hi, df.lo, df.op
    pc = C.shift(1)
    tr = pd.concat([H - L, (H - pc).abs(), (L - pc).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14, min_periods=10).mean()
    df["ma20"] = C.rolling(20).mean(); df["sd20"] = C.rolling(20).std()
    df["bb_u"] = df.ma20 + 2 * df.sd20; df["bb_l"] = df.ma20 - 2 * df.sd20
    df["pctb"] = (C - df.bb_l) / (df.bb_u - df.bb_l)
    dl = C.diff(); up_ = dl.clip(lower=0); dn_ = -dl.clip(upper=0)
    df["rsi14"] = 100 - 100 / (1 + up_.ewm(alpha=1/14, min_periods=10).mean() / dn_.ewm(alpha=1/14, min_periods=10).mean())
    au = up_.ewm(alpha=1/2, min_periods=2).mean(); ad = dn_.ewm(alpha=1/2, min_periods=2).mean()
    df["rsi2"] = 100 - 100 / (1 + au / ad)
    for k in (1, 3, 5, 21):
        df[f"r{k}"] = (C / C.shift(k) - 1) * 100
    df["gap"] = (O / pc - 1) * 100
    r1 = np.nan_to_num(df["r1"].values, nan=0.0)
    dns = np.zeros(len(df), int); cnt = 0
    for i in range(len(df)):
        cnt = cnt + 1 if r1[i] < 0 else 0; dns[i] = cnt
    df["dn_streak"] = dns
    df["dxy_d"] = (df.dxy / df.dxy.shift(1) - 1) * 100
    # silver 5d return (lag_rel ka signal input).
    # Series = published book wali silver INR (₹/kg). Naye (live tail) dino ke liye wahi scale:
    #   silver_usd x (mcx_silver_kg_inr_modelled / silver_usd) — parity CSV me yahi ratio hai.
    sil = pd.Series(dtype=float)
    try:
        from ms_gold_inr import load_silver_inr
        sil = pd.to_numeric(load_silver_inr().px, errors="coerce").dropna()
    except Exception:
        pass
    if not len(sil):
        f_sil = f"{MS}/data/silver_inr.csv"        # GitHub package me bundled canonical series
        if os.path.exists(f_sil):
            sil = pd.read_csv(f_sil, index_col=0, parse_dates=True).iloc[:, 0]
            sil = pd.to_numeric(sil, errors="coerce").dropna()
    if len(sil):
        try:
            ratio = (pd.to_numeric(parity["mcx_silver_kg_inr_modelled"], errors="coerce") /
                     pd.to_numeric(parity["silver_usd"], errors="coerce")).reindex(df.index).ffill()
            su = pd.to_numeric(pick(["silver_usd"]), errors="coerce")
            add = (su * ratio).dropna()
            add = add[~add.index.isin(sil.index)]
            if len(add):
                sil = pd.concat([sil, add]).sort_index()
                sil = sil[~sil.index.duplicated(keep="last")]
        except Exception:
            pass
    df["sil_r5"] = (sil.pct_change(5) * 100).reindex(df.index)
    if df["sil_r5"].isna().all():
        df["sil_r5"] = df["sil_inr"].pct_change(5) * 100   # aakhri fallback (scale alag, sirf direction)
    return df


def fam_masks(D):
    r14, pb, r3, r5, r21, gap = D.rsi14, D.pctb, D.r3, D.r5, D.r21, D.gap
    up, coil = D.state == "UP", D.state == "COIL"
    S5 = D.sil_r5
    r1d = (D.px / D.px.shift(1) - 1) * 100          # 1-din ka move (naye fast families ke liye)
    MM = D["mm_pct_v3"] if "mm_pct_v3" in D.columns else pd.Series(50.0, index=D.index)   # phase-4
    return dict(
        # --- phase-3 V4 naye families (16-Oct) ---
        drip1=(r1d < -1.8) & (r14 < 55),
        core=(r14 < 40) & (pb < 0.3),
        up_dip1=(up) & (r1d < -1.0) & (r14 < 60),
        pb20=(r14 < 35) & (pb < 0.2) & (r21 < 0),
        lag_gs80pct=(D.gs_pct > 80) & (r5 < 0),
        dxy_dn=(D.dxy_d < -0.6) & (r3 < 0),
        lag_rel=((r5 - S5) < -2) & (r5 < 0),
        up_gap=(up) & (gap < -0.5),
        coil_r3=(coil) & (r3 < -2),
        gvz_panic=(D.gvz_pct_v3 > 85) & (r3 < -2),
        real_z=(D.real10y_synth_z < -1) & (r3 < 0),
        gaprsi=(gap < -1.0) & (r14 < 45),
        dxy_z=(D.dxy_pct_v3 < 15) & (r3 < 0),
        lag_gs20pct=(D.gs_pct < 20) & (r5 < 0),
        # --- phase-4 REDESIGN (16-Oct) naye families ---
        r5_deep=(r5 < -6),
        mm_capit=(MM < 10) & (r3 < -1),
        gvz_spike=(D.gvz_pct_v3 > 70) & (r1d < -1.0),
        dip_above_mean=(r1d < -1.5) & (D.px > D.ma20),
        trend_pull_rsi=(up) & (r14 < 50) & (pb < 0.45),
        gapdown_up=(up) & (gap < -1.0),
        r21pb=(r21 < -6) & (pb < 0.15),
    )


def system_table():
    """11 production systems + unka cfg (tgt/stop/hold) + priority."""
    s = pd.read_csv(SYS_CSV)
    s["fam"] = s.system.str.replace("G-", "", regex=False)
    sc = pd.read_csv(SCREEN_CSV)
    cfgmap = dict(zip(sc.family, sc.cfg))
    namemap = dict(zip(sc.family, sc.name)) if "name" in sc.columns else {}
    tgt_hit = dict(zip(sc.family, sc.tgt_hit)) if "tgt_hit" in sc.columns else {}
    try:
        t = pd.read_csv(TRADES_CSV)
        pris = t.groupby("family").prio.min().to_dict()
    except Exception:
        pris = {}
    out = []
    for _i, (_, r) in enumerate(s.iterrows()):
        cfg = str(cfgmap.get(r.fam, ""))
        if "/" in cfg:
            tgt, stp, hold = [float(x) for x in cfg.split("/")]
        else:
            tgt, stp, hold = float(r.tgt), float(r.stop), 20.0
        out.append(dict(system=r.system, fam=r.fam, tgt=tgt, stp=stp, hold=int(hold),
                        prio=float(pris.get(r.fam, _i)), win=float(r.win), avg=float(r.avg), n=int(r.n),
                        name=str(namemap.get(r.fam, r.fam)), tgt_hit=float(tgt_hit.get(r.fam, 0) or 0)))
    return pd.DataFrame(out).sort_values("prio")


# ---------------------------------------------------------------- contract
MCX_MASTER = f"{MS}/data/mcx/goldpetal_contracts.csv"


CONTRACT_FALLBACK = [  # 16-Oct-2026: Dhan scrip master se verify kiye gaye
    ("GOLDPETAL OCT FUT", "571306", "2026-10-30"),
    ("GOLDPETAL NOV FUT", "574841", "2026-11-30"),
    ("GOLDPETAL DEC FUT", "578631", "2026-12-31"),
    ("GOLDPETAL JAN FUT", "581706", "2027-01-29"),
]


def contract_pick(max_hold, today=None):
    """GOLDPETAL ka sahi contract: expiry >= (aaj + max_hold + 3 din) — expiry se pehle exit ho jaye."""
    today_ts = pd.Timestamp(today if today is not None else now_ist().date())
    if not os.path.exists(MCX_MASTER):
        for disp, sid, exp in CONTRACT_FALLBACK:
            e = pd.Timestamp(exp)
            if e >= today_ts + pd.Timedelta(days=int(max_hold) + 3):
                return dict(symbol=disp.replace(" ", "-"), display=disp, sec_id=sid, expiry=exp,
                            days_left=int((e - today_ts).days))
        return None
    c = pd.read_csv(MCX_MASTER)
    c["exp_dt"] = pd.to_datetime(c.SEM_EXPIRY_DATE, errors="coerce", utc=True).dt.tz_localize(None)
    today = pd.Timestamp(today if today is not None else now_ist().date())
    c = c[c.exp_dt >= today + pd.Timedelta(days=int(max_hold) + 3)].sort_values("exp_dt")
    if not len(c):
        return None
    r = c.iloc[0]
    return dict(symbol=str(r.SEM_TRADING_SYMBOL), display=str(r.SEM_CUSTOM_SYMBOL),
                sec_id=str(int(r.SEM_SMST_SECURITY_ID)), expiry=str(r.exp_dt.date()),
                days_left=int((r.exp_dt - today).days))


# ---------------------------------------------------------------- signals
# ---------------------------------------------------------------- silver (SIGNAL-ONLY)
# Improvement phase-2 (16-Oct-2026): silver ka long book me 4 systems the; live me 3 chalti hain
# (up_gap ke liye silver OHLC/state chahiye, wo repo bundle me nahi). Trigger = clean INR data.
# phase-4 redesign (16-Oct): naya silver book (6 families) — book K=3: 2.41/mo, win 76.1%, 79.6% trades 2.5%+ touch
SILVER_FAMS = {"gapdn": (4.0, 10.0, 20), "rsi30r5": (3.0, 8.0, 20), "up_pb": (3.0, 12.0, 20),
               "up_gap": (3.5, 10.0, 20), "gs_ext_dip": (3.0, 10.0, 20), "mm_capit": (4.0, 10.0, 20)}
SILVER_NAME = {"gapdn": "gap < -1.5% (silver)", "rsi30r5": "Silver RSI14<30 & 5d<-3",
               "up_pb": "UP trend & pctB<0.25", "up_gap": "UP trend & gap<-0.5%",
               "gs_ext_dip": "G/S >90th pct & 3d<0", "mm_capit": "MM <10th pct & 3d<-1%"}
SIL_COLS = ["signal_date", "system", "family", "ref_px", "target_px", "stop_px", "tgt_pct", "stop_pct",
            "max_hold", "risk_inr", "note"]


def silver_frame(df):
    """Silver ₹/kg (model) + trigger inputs — wahi refreshed frame jo gold use karta hai."""
    s = pd.DataFrame(index=df.index)
    s["px"] = (pd.to_numeric(df["sil_inr"], errors="coerce") if "sil_inr" in df.columns
               else pd.Series(np.nan, index=df.index)).ffill()
    s["r3"] = (s.px / s.px.shift(3) - 1) * 100
    s["r5"] = (s.px / s.px.shift(5) - 1) * 100
    dl = s.px.diff(); up = dl.clip(lower=0); dn = -dl.clip(upper=0)
    s["rsi14"] = 100 - 100 / (1 + up.ewm(alpha=1 / 14, min_periods=10).mean() / dn.ewm(alpha=1 / 14, min_periods=10).mean())
    s["gs_pct"] = (pd.to_numeric(df["gs_pct_v3"], errors="coerce") if "gs_pct_v3" in df.columns
                   else pd.Series(np.nan, index=df.index))
    dxy = (pd.to_numeric(df["dxy"], errors="coerce") if "dxy" in df.columns else pd.Series(np.nan, index=df.index))
    s["dxy_chg"] = dxy.pct_change() * 100
    # fase-4 masks
    C = s.px
    s["ma20"] = C.rolling(20).mean(); sd20 = C.rolling(20).std()
    s["pctb"] = (C - (s.ma20 - 2 * sd20)) / (4 * sd20)
    m50, m200 = C.rolling(50).mean(), C.rolling(200).mean()
    st = pd.Series("COIL", index=s.index, dtype=object)
    st[(C > m50) & (m50 > m200)] = "UP"; st[(C < m50) & (m50 < m200)] = "DOWN"
    s["state"] = st
    # GAP fix (16-Oct): backtest jaisa hi — op / pichhla close - 1, USD me (currency cancel ho jaati hai).
    #   history -> panel ka silver_fut_open ; naya din -> yfinance SI=F ka open (silver_open_usd)
    f_open = pd.to_numeric(df["silver_fut_open"], errors="coerce") if "silver_fut_open" in df.columns else pd.Series(np.nan, index=df.index)
    t_open = pd.to_numeric(df["silver_open_usd"], errors="coerce") if "silver_open_usd" in df.columns else pd.Series(np.nan, index=df.index)
    f_close = pd.to_numeric(df["silver_fut_close"], errors="coerce") if "silver_fut_close" in df.columns else pd.Series(np.nan, index=df.index)
    s_usd = pd.to_numeric(df["silver_usd"], errors="coerce") if "silver_usd" in df.columns else pd.Series(np.nan, index=df.index)
    op_usd = f_open.fillna(t_open)
    cl_usd = f_close.fillna(s_usd)
    s["gap"] = (op_usd / cl_usd.shift(1) - 1) * 100
    s["gvz_pct"] = (pd.to_numeric(df["gvz_pct_v3"], errors="coerce") if "gvz_pct_v3" in df.columns
                    else pd.Series(np.nan, index=df.index))
    s["mm_pct"] = (pd.to_numeric(df["mm_pct_v3"], errors="coerce") if "mm_pct_v3" in df.columns
                   else pd.Series(np.nan, index=df.index))
    s["S-gapdn"] = s.gap < -1.5
    s["S-rsi30r5"] = (s.rsi14 < 30) & (s.r5 < -3)
    s["S-up_pb"] = (s.state == "UP") & (s.pctb < 0.25)
    s["S-up_gap"] = (s.state == "UP") & (s.gap < -0.5)
    s["S-gs_ext_dip"] = (s.gs_pct > 90) & (s.r3 < 0)
    s["S-mm_capit"] = (s.mm_pct < 10) & (s.r3 < -1)
    return s


def silver_scan(cfg, df, quiet=False):
    """Silver book ka last-bar check — SIGNAL-ONLY (SILVERMIC margin ~₹19,082; cash ho tab hi trade)."""
    out = dict(last_bar=None, px=None, new=[], note="", margin=float(cfg.get("silver_margin_per_lot", 19082) or 0))
    if not bool(cfg.get("silver_signals", True)):
        out["note"] = "silver_signals OFF"; return out
    try:
        s = silver_frame(df)
    except Exception as e:
        out["note"] = f"silver data problem: {e}"; return out
    if not len(s) or not np.isfinite(s["px"].iloc[-1]):
        out["note"] = "silver data nahi mila (refresh chalao)"; return out
    px = float(s["px"].iloc[-1]); d = pd.Timestamp(s.index[-1])
    out.update(last_bar=str(d.date()), px=px)
    if pd.Timestamp(df.index[-1]).date() != d.date():
        out["note"] = "silver bar purana hai (refresh check karo)"
    inact = [t for t in SILVER_FAMS if ("S-" + t) not in s.columns or bool(s["S-" + t].isna().all())]
    out["inactive"] = inact
    if inact and not quiet:
        print(f"   (silver me data na hone se {len(inact)} family chhupi: {', '.join(inact)})")
    # DUPLICATE FIX (16-Oct): ek hi family ka signal 7 din ke andar dobara mat bhejo
    #   (pehle har run par — 3 run/din — wahi signal dobara chala jata tha)
    recent = set()
    sf = f"{ADIR}/silver_signals.csv"
    if os.path.exists(sf):
        try:
            h = pd.read_csv(sf)
            if "signal_date" in h.columns and "family" in h.columns:
                h["sd"] = pd.to_datetime(h.signal_date, errors="coerce")
                cut = (pd.Timestamp(out["last_bar"]) - pd.Timedelta(days=7)) if out.get("last_bar") else None
                if cut is not None:
                    recent = set(h.loc[h.sd >= cut, "family"].astype(str))
        except Exception:
            recent = set()
    for tag, (tgt, stp, hold) in SILVER_FAMS.items():
        if tag and bool(s["S-" + tag].iloc[-1] if "S-" + tag in s.columns else False) and tag not in recent:
            out["new"].append(dict(system="S-" + tag, family=tag, name=SILVER_NAME[tag], signal_date=out["last_bar"],
                                   ref_px=round(px, 0), target_px=round(px * (1 + tgt / 100), 0),
                                   stop_px=round(px * (1 - stp / 100), 0), tgt_pct=tgt, stop_pct=stp, max_hold=hold,
                                   risk_inr=round(px * float(cfg.get("silver_lot_kg", 1.0) or 1.0) * stp / 100, 0)))
    if out["new"]:
        f = f"{ADIR}/silver_signals.csv"
        try:
            hdr = (not os.path.exists(f)) or os.path.getsize(f) < 5
            with open(f, "a") as fh:
                if hdr:
                    fh.write(",".join(SIL_COLS) + "\n")
                for r in out["new"]:
                    fh.write(",".join(str(r[k]) for k in SIL_COLS[:-1]) + ",signal-only\n")
        except Exception:
            pass
        if not quiet:
            print(f"\n👀 SILVER SIGNALS (signal-only; SILVERMIC 1 kg — margin ~₹{out['margin']:,.0f}, cash check karo):")
            for r in out["new"]:
                print(f"   {r['system']:11s} ref ₹{r['ref_px']:,.0f}/kg | target ₹{r['target_px']:,.0f} (+{r['tgt_pct']:g}%) | "
                      f"stop ₹{r['stop_px']:,.0f} (−{r['stop_pct']:g}%) | max {r['max_hold']} din | 1 lot risk ~₹{r['risk_inr']:,.0f}")
    return out


def signal_scan(cfg, D, quiet=False):
    """Aakhri COMPLETE bar par 11 systems ke triggers -> pending orders (order tickets)."""
    now = now_ist()
    today = now.date()
    bar_dates = list(D.index.date)
    complete = [d for d in bar_dates if d < today]        # aaj ka bar adhoora ho sakta hai
    sig_date = complete[-1] if complete else bar_dates[-1]
    i = bar_dates.index(sig_date)
    provisional = not _bar_complete(sig_date, now)
    Dsig = D.iloc[: i + 1]
    F = fam_masks(Dsig)
    sysdf = system_table()
    orders = orders_load()
    positions = pos_load()
    # stale PENDING (entry day nikal gaya, fill/skip nahi hua) -> EXPIRED, warna slot hamesha block rehta hai
    expired = []
    if len(orders):
        od = pd.to_datetime(orders.entry_day, errors="coerce").dt.date
        stale = (orders.status == "PENDING") & od.notna() & (od < today)
        if bool(stale.any()):
            for _, r in orders.loc[stale].iterrows():
                expired.append((r.order_id, r.system, r.entry_day))
            orders.loc[stale, "status"] = "EXPIRED"
            orders.loc[stale, "note"] = "entry day nikal gaya (fill/skip nahi hua) — slot free kar diya"
            orders_save(orders)
    live_pos = positions.status.isin(["OPEN", "EXIT_ADVICE"]) if len(positions) else pd.Series(dtype=bool)
    open_fams = set(positions.loc[live_pos, "family"]) if len(positions) else set()
    pend = orders.status == "PENDING" if len(orders) else pd.Series(dtype=bool)
    max_open = int(cfg["max_open"])
    n_open = int(live_pos.sum()) if len(positions) else 0
    n_pend = int(pend.sum()) if len(orders) else 0
    px = float(Dsig.px.iloc[-1])
    entry_day = str(next_entry_day(now))
    rows, skipped = [], []
    for _, s in sysdf.iterrows():
        m = F[s.fam]
        if not bool(m.iloc[-1]):
            continue
        if s.fam in open_fams:
            skipped.append((s.system, "same family ka position pehle se khula hai (non-overlap rule)")); continue
        dup = orders[(orders.system == s.system) & (orders.signal_date == str(sig_date)) &
                     (orders.status.isin(["PENDING", "FILLED", "SKIPPED", "CLOSED", "EXPIRED"]))]
        if len(dup):
            skipped.append((s.system, "is signal bar ka order pehle hi ban chuka hai")); continue
        if n_open + n_pend >= max_open:
            skipped.append((s.system, f"slots bhare hue (open {n_open} + pending {n_pend} = max {max_open})")); continue
        oid = _next_oid(orders)
        tgt_px = px * (1 + s.tgt / 100)
        stp_px = px * (1 - s.stp / 100)
        con = contract_pick(s.hold) or {}
        glo, ghi, ghard = gap_band(cfg, px)
        n_pend += 1
        rows.append(dict(order_id=oid, created_on=str(today), signal_date=str(sig_date),
                         entry_day=entry_day, system=s.system, family=s.fam, side="BUY",
                         rule=f"{s.get('name', s.fam)} — win {s.win:.0f}%, avg +{s.avg:.2f}% per trade", lots=int(cfg["lots"]),
                         contract=con.get("display", cfg["contract"]), contract_sec_id=con.get("sec_id", ""),
                         contract_expiry=con.get("expiry", ""),
                         ref_px=round(px, 1), skip_above=round(ghi, 1),
                         gap_lo_px=round(glo, 1), gap_hi_px=round(ghi, 1), gap_hard_px=round(ghard, 1),
                         target_px=round(tgt_px, 1), stop_px=round(stp_px, 1), tgt_pct=s.tgt, stop_pct=s.stp,
                         max_hold=s.hold, status="PENDING",
                         note=(f"quick-book ON: din-{int(cfg.get('quick_book_day',5) or 5)} par "
                               f"+{float(cfg.get('quick_book_pct',1.5) or 1.5):g}% ho to book"
                               if bool(cfg.get("quick_book", True)) else "")))
    if rows:
        orders = pd.concat([orders, pd.DataFrame(rows)], ignore_index=True)
        orders_save(orders)
    sil = silver_scan(cfg, D, quiet=quiet)
    return dict(sig_date=str(sig_date), px=px, new=rows, skipped=skipped, n_open=n_open, n_pend=n_pend, silver=sil,
                provisional=provisional, entry_day=entry_day, expired=expired,
                state=D.state.iloc[-1], r14=float(D.rsi14.iloc[-1]), pb=float(D.pctb.iloc[-1]),
                r21=float(D.r21.iloc[-1]), gs=float(D.gs_pct.iloc[-1]), dxy=float(D.dxy.iloc[-1]),
                dxy_d=float(D.dxy_d.iloc[-1]), gvz=float(D.gvz_pct_v3.iloc[-1]), last_bar=str(D.index[-1].date()))


def suppress_new(cfg, new_rows, reason):
    """RED ZONE: aaj ke naye signals ko khud SKIP mark kar do (safety) — trade block."""
    done = []
    for r in new_rows:
        try:
            cmd_skip(cfg, Namespace(id=str(r["order_id"]), why=f"health RED: {reason[:60]}"))
            done.append(r["order_id"])
        except Exception:
            pass
    return done


def book_summary():
    """Live book ka summary (phase-4 se) — message me 'kitna degi' dikhane ke liye."""
    f = f"{MS}/data/algo/book_summary.json"
    d = dict(win=75.5, avg=1.16, per_mo=3.01, inr_mo=372, dd=6.7, systems=11, trades=821)
    try:
        if os.path.exists(f):
            d.update(json.load(open(f)))
    except Exception:
        pass
    return d


def pending_orders():
    o = orders_load()
    if not len(o):
        return o
    return o[o.status == "PENDING"]


# ---------------------------------------------------------------- actions
def entry_day_info(cfg, D):
    """Entry-day ke COMEX open ka reference price (agar available ho) → exact skip level."""
    now = now_ist()
    lastd_needed = str(now.date())
    tp = f"{ADIR}/live_tail.csv"
    tail = pd.read_csv(tp, index_col=0, parse_dates=True) if os.path.exists(tp) else None
    if tail is not None and len(tail) and "gold_open_usd" in tail.columns:
        lastd = str(tail.index[-1].date())
        if lastd == lastd_needed:
            sc = float(D.usdinr.iloc[-1] * (1 + D.gold_duty_pct.iloc[-1] / 100) *
                       (1 + D.indirect_tax_pct.iloc[-1] / 100) / OZ2G)
            hi = tail.gold_high_usd.iloc[-1]; lo = tail.gold_low_usd.iloc[-1]
            return dict(known=True, ref=float(tail.gold_open_usd.iloc[-1] * sc), day=lastd,
                        hi=float(hi * sc) if pd.notna(hi) else None,
                        lo=float(lo * sc) if pd.notna(lo) else None)
    return dict(known=False, ref=None, day=None, hi=None, lo=None)


def cmd_fill(cfg, args):
    o = orders_load()
    sel = o.index[pd.to_numeric(o.order_id, errors="coerce") == float(args.id)]
    if not len(sel):
        print(f"❌ order #{args.id} nahi mila (orders.csv dekho)"); return
    i = sel[0]
    if str(o.loc[i, "status"]).upper() == "FILLED":
        print(f"⚠️ order #{args.id} PEHLE SE filled hai — dobara fill mat karo (positions.csv dekho)"); return
    if str(o.loc[i, "status"]).upper() not in ("PENDING", ""):
        print(f"⚠️ order #{args.id} ka status '{o.loc[i,'status']}' hai (PENDING nahi) — phir bhi fill likh raha hoon")
    px = float(args.price)
    if px <= 0:
        print("❌ price 0 se bada daalo"); return
    lots = float(args.lots) if args.lots else float(o.loc[i, "lots"] or cfg["lots"])
    if lots <= 0:
        print("❌ lots 0 se badi honi chahiye"); return
    if px < 100:
        print(f"⚠️ price ₹{px} bahut chhota hai — GOLDPETAL ₹/gram me quote hota hai (~₹13,000+)")
    rp = fnum(o.loc[i, "ref_px"] if "ref_px" in o.columns else np.nan)
    if np.isfinite(rp) and rp > 0:
        verdict, why = gap_verdict(cfg, rp, px)
        if verdict == "SKIP":
            print(f"⚠️ GAP WARNING: entry ₹{px:,.1f} vs ref ₹{rp:,.1f} = {why} — ye zone backtest me kamzor tha "
                  f"(dead-zone: 58% win/+0.11% · 2.5%+: 60% win/-1.93%). Phir bhi fill likh raha hoon.")
    try:
        tgt = float(o.loc[i, "tgt_pct"]); stp = float(o.loc[i, "stop_pct"])
    except Exception:
        print("❌ order me target/stop % missing hai — order dobara banao (scan)"); return
    p = pos_load()
    new_row = pd.DataFrame([dict(
        order_id=o.loc[i, "order_id"], system=o.loc[i, "system"], family=o.loc[i, "family"], side="LONG",
        entry_date=str(now_ist().date()), entry_px=round(px, 1), lots=lots,
        target_px=round(px * (1 + tgt / 100), 1), stop_px=round(px * (1 - stp / 100), 1),
        max_hold=o.loc[i, "max_hold"], last_px=round(px, 1), last_date=str(now_ist().date()), days_held=0,
        unreal_pct=0.0, unreal_inr=0.0, status="OPEN", note="")])
    p = pd.concat([p, new_row.reindex(columns=POS_COLS)], ignore_index=True) if len(p) else new_row.reindex(columns=POS_COLS)
    pos_save(p)
    o.loc[i, "status"] = "FILLED"; o.loc[i, "note"] = f"fill ₹{px:g}"; orders_save(o)
    con = str(o.loc[i, "contract"] or cfg["contract"])
    print(f"✔ position khul gayi: {o.loc[i,'system']} | {con} | entry ₹{px:,.0f}/g × {lots:g} lot")
    print(f"   ➜ ABHI protection lagao: target ₹{px*(1+tgt/100):,.0f} (+{tgt}%) | STOP **SL-M** ₹{px*(1-stp/100):,.0f} (−{stp}%)")
    print(f"   ➜ max hold {o.loc[i,'max_hold']} din | roz sheet me HOLD/CLOSE dekho")


def cmd_skip(cfg, args):
    o = orders_load()
    sel = o.index[pd.to_numeric(o.order_id, errors="coerce") == float(args.id)]
    if not len(sel):
        print(f"❌ order #{args.id} nahi mila"); return
    i = sel[0]
    if str(o.loc[i, "status"]).upper() == "FILLED":
        print("⚠️ ye order fill ho chuka hai — skip nahi kar sakte (position band karni ho to `close` use karo)"); return
    o.loc[i, "status"] = "SKIPPED"
    o.loc[i, "note"] = args.why or "manual skip"
    orders_save(o)
    print(f"✔ order #{args.id} SKIPPED mark ho gaya — reason: {o.loc[i,'note']}")


def cmd_close(cfg, args):
    p = pos_load()
    sel = p.index[pd.to_numeric(p.order_id, errors="coerce") == float(args.id)] if len(p) else []
    if not len(sel):
        o = orders_load()
        if len(o) and bool((pd.to_numeric(o.order_id, errors="coerce") == float(args.id)).any()):
            print(f"⚠️ order #{args.id} mila, par koi OPEN position nahi (shayad pehle close ho chuki hai)")
        else:
            print(f"❌ position #{args.id} nahi mili")
        return
    i = sel[0]
    px = float(args.price)
    if px <= 0:
        print("❌ price 0 se bada daalo"); return
    epx = float(p.loc[i, "entry_px"]); lots = float(p.loc[i, "lots"])
    pnl_pct = (px / epx - 1) * 100
    gross = (px - epx) * lots * cfg["gram_per_lot"]
    cost = cfg["cost_inr_per_lot"] * lots
    dv = fnum(p.loc[i, "days_held"], 0.0)
    days = int(dv) if np.isfinite(dv) else 0
    try:      # days_held khaali ho (manage pehle na chala) to entry_date se gino
        _ed = pd.Timestamp(str(p.loc[i, "entry_date"])); _xd = pd.Timestamp(str(now_ist().date()))
        days = max(days, int((_xd - _ed).days))
    except Exception:
        pass
    j = jrn_load()
    _jrow = pd.DataFrame([dict(
        order_id=p.loc[i, "order_id"], system=p.loc[i, "system"], family=p.loc[i, "family"], side="LONG",
        entry_date=p.loc[i, "entry_date"], entry_px=epx, exit_date=str(now_ist().date()), exit_px=round(px, 1),
        lots=lots, pnl_inr=round(gross - cost, 0), pnl_pct=round(pnl_pct, 2), why=args.why or "manual",
        days_held=days, cost_inr=cost, note="")])
    j = pd.concat([j, _jrow.reindex(columns=JRN_COLS)], ignore_index=True) if len(j) else _jrow.reindex(columns=JRN_COLS)
    jrn_save(j)
    p = p.drop(index=i); pos_save(p)
    o = orders_load()
    s2 = o.index[pd.to_numeric(o.order_id, errors="coerce") == float(args.id)] if len(o) else []
    if len(s2):
        o.loc[s2[0], "status"] = "CLOSED"; orders_save(o)
    print(f"✔ position band: {j.iloc[-1]['system']} entry ₹{epx:,.0f} -> exit ₹{px:,.0f} "
          f"| {pnl_pct:+.2f}% | ₹{gross-cost:+,.0f} (cost ₹{cost:,.0f} ke baad) | {args.why or 'manual'} | {days} din")
    print("   ⓘ Dhan me pending target/SL orders (agar alag lagaye the) CANCEL kar do.")


def manage(cfg, D):
    """Open positions: stop / target / time-exit check + P&L. Har position har haal me report hoti hai."""
    p = pos_load()
    if not len(p):
        return []
    out = []
    last_px_all = float(D.px.iloc[-1]); last_d = str(D.index[-1].date())
    for i in p.index:
        st = str(p.loc[i, "status"]).upper()
        if st not in ("OPEN", "EXIT_ADVICE", ""):
            continue
        epx = fnum(p.loc[i, "entry_px"]); tgt = fnum(p.loc[i, "target_px"]); stp = fnum(p.loc[i, "stop_px"])
        lots = fnum(p.loc[i, "lots"], 1.0); mh = fnum(p.loc[i, "max_hold"], 20.0)
        if not (np.isfinite(epx) and np.isfinite(tgt) and np.isfinite(stp)):
            out.append(dict(order_id=p.loc[i, "order_id"], system=p.loc[i, "system"], entry=epx, last=np.nan,
                            days=0, unreal=np.nan, status="ERROR",
                            note="entry/target/stop price galat hai (positions.csv dekho)"))
            continue
        ed = pd.Timestamp(str(p.loc[i, "entry_date"]))
        hist = D.loc[D.index > ed]
        if len(hist):
            hit_lo = hist.index[hist.lo <= stp]
            hit_hi = hist.index[hist.hi >= tgt]
            first_lo = hit_lo[0] if len(hit_lo) else None
            first_hi = hit_hi[0] if len(hit_hi) else None
            why = None; when = None
            if first_lo is not None and (first_hi is None or first_lo <= first_hi):
                why, when = "STOP hit", first_lo
                op_lo = float(D.loc[first_lo, "op"])
                if op_lo < stp:
                    why = f"STOP hit (gap-down open ₹{op_lo:,.0f} — asli fill isse neeche hoga)"
            elif first_hi is not None:
                why, when = "TARGET hit", first_hi
            days = int(len(hist))
            p.loc[i, ["last_px", "last_date", "days_held", "unreal_pct"]] = [
                round(last_px_all, 1), last_d, days, round((last_px_all / epx - 1) * 100, 2)]
            p.loc[i, "unreal_inr"] = round((last_px_all - epx) * lots * cfg["gram_per_lot"], 0)
            if why:
                p.loc[i, "status"] = "EXIT_ADVICE"
                p.loc[i, "note"] = f"{why} ({when.date()}) — exit karo, phir: close {p.loc[i,'order_id']} --price <aapka fill>"
            elif (bool(cfg.get("quick_book", True))
                  and days >= int(cfg.get("quick_book_day", 5) or 5)
                  and (last_px_all / epx - 1) * 100 >= float(cfg.get("quick_book_pct", 1.5) or 1.5)):
                p.loc[i, "status"] = "EXIT_ADVICE"
                p.loc[i, "note"] = (f"QUICK-BOOK: {days} din me +{(last_px_all/epx-1)*100:.2f}% ho gaya — "
                                    f"aaj close karo (2.5%+ profit lock — V5 rule): close {p.loc[i,'order_id']} --price <fill>")
            elif days >= mh:
                p.loc[i, "status"] = "EXIT_ADVICE"
                p.loc[i, "note"] = f"TIME exit ({days} din >= {int(mh)}) — aaj close karo: close {p.loc[i,'order_id']} --price <fill>"
            else:
                p.loc[i, "status"] = "OPEN"
                p.loc[i, "note"] = f"hold ({int(mh)-days} din baaki)"
            out.append(dict(order_id=p.loc[i, "order_id"], system=p.loc[i, "system"], entry=epx,
                            last=last_px_all, days=days, unreal=(last_px_all / epx - 1) * 100,
                            status=p.loc[i, "status"], note=p.loc[i, "note"]))
        else:
            p.loc[i, ["last_px", "last_date", "days_held", "unreal_pct"]] = [round(epx, 1), str(ed.date()), 0, 0.0]
            p.loc[i, "unreal_inr"] = 0.0
            if str(p.loc[i, "status"]).upper() != "EXIT_ADVICE":
                p.loc[i, "status"] = "OPEN"
                p.loc[i, "note"] = "aaj hi entry hui — hold"
            out.append(dict(order_id=p.loc[i, "order_id"], system=p.loc[i, "system"], entry=epx, last=epx,
                            days=0, unreal=0.0, status=p.loc[i, "status"] or "OPEN", note=p.loc[i, "note"]))
    pos_save(p)
    return out


def report(cfg):
    j = jrn_load()
    p = pos_load()
    print(f"\n{'='*88}\n1-MONTH TEST SCOREBOARD — capital ₹{cfg['capital']:,.0f} | {cfg['lots']:g} lot {cfg['contract']}\n{'='*88}")
    if len(j):
        j["pnl_inr"] = j.pnl_inr.astype(float); j["pnl_pct"] = j.pnl_pct.astype(float)
        wins = (j.pnl_inr > 0).sum()
        print(f"closed trades: {len(j)} | win {wins/len(j)*100:.0f}% | total ₹{j.pnl_inr.sum():+,.0f} "
              f"| avg {j.pnl_pct.mean():+.2f}%/trade | avg hold {j.days_held.astype(float).mean():.1f} din")
        print(j[["order_id", "system", "entry_date", "entry_px", "exit_date", "exit_px", "pnl_inr", "pnl_pct", "why"]].to_string(index=False))
    else:
        print("abhi koi closed trade nahi.")
    if len(p):
        print("\nopen positions:")
        print(p[["order_id", "system", "entry_date", "entry_px", "last_px", "days_held", "unreal_pct", "unreal_inr", "status"]].to_string(index=False))
    o = orders_load()
    if len(o):
        print(f"\norders: pending {int((o.status=='PENDING').sum())} | filled {int((o.status=='FILLED').sum())} "
              f"| skipped {int((o.status=='SKIPPED').sum())} | closed {int((o.status=='CLOSED').sum())}")
    print(f"\nEXPECTATION (backtest, GOLDPETAL cost ke baad): ~3.3 trade/month | win ~71% | +0.62%/trade "
          f"| 1 lot par ~₹90/trade net | worst single trade ~−₹2,100")


# ---------------------------------------------------------------- output
def console_sheet(cfg, scan, mgr, D):
    p = pending_orders()
    now = now_ist()
    print(f"\n{'='*100}")
    print(f"MS ALGO — ACTION SHEET | {now.strftime('%d-%b-%Y %H:%M IST')} | data: signal bar {scan['sig_date']}, market {scan['last_bar']}")
    print(f"{'='*100}")
    print(f"macro: gold state {scan['state']} | RSI14 {scan['r14']:.1f} | %B {scan['pb']:.2f} | 21d {scan['r21']:+.1f}% "
          f"| G/S pct {scan['gs']:.0f} | DXY {scan['dxy']:.1f} ({scan['dxy_d']:+.2f}%) | GVZ pct {scan['gvz']:.0f}")
    if scan.get("provisional"):
        print(f"⚠️  PROVISIONAL SIGNAL BAR: {scan['sig_date']} ka COMEX session abhi band nahi hua "
              f"(bar {scan['sig_date']}+1 din 02:30 IST par complete hota hai) — 02:45 IST ke baad `run` dobara chalao, "
              f"warna aaj ka signal badal sakta hai.")
    print(f"⏱ entry day: {scan['entry_day']} (MCX 9:00 AM open) | pending {scan['n_pend']} | open {scan['n_open']}")
    if scan["new"]:
        print(f"\n🟢 NAYE ORDERS ({len(scan['new'])}) — {scan['entry_day']} ke MCX open (9:00-9:15 AM) par lagao:")
        for r in scan["new"]:
            print(f"   #{r['order_id']}  {r['system']:16s} {r['rule']}")
            sec = str(r['contract_sec_id'] or "").strip()
            if sec in ("", "nan"):
                print(f"        CONTRACT: {r['contract']}  ⚠️ expiry/sec-id master se nahi mila — "
                      f"data/mcx/goldpetal_contracts.csv check karo, order se pehle Dhan app me NOV FUT confirm karo")
            else:
                print(f"        CONTRACT: {r['contract']} (sec id {sec}, expiry {r['contract_expiry']})")
            print(f"        BUY {r['lots']:g} lot {cfg['contract']} | ref ₹{r['ref_px']:,.0f}/g "
                  f"| ➜ SKIP agar MCX open ₹{r['skip_above']:,.0f} se upar ho")
            print(f"        target ₹{r['target_px']:,.0f} (+{r['tgt_pct']}%) | stop-SL-M ₹{r['stop_px']:,.0f} (−{r['stop_pct']}%) | max hold {r['max_hold']} din")
    else:
        print("\n🟡 koi naya entry signal nahi (aaj).")
    if scan.get("expired"):
        print("\n⌛ PURANE PENDING orders expire kiye (entry day nikal gaya): "
              + ", ".join(f"#{int(float(o))} {s}" for o, s, _ in scan["expired"]))
    if scan["skipped"]:
        print("\n(chhode gaye signals):")
        for s, why in scan["skipped"]:
            print(f"   - {s}: {why}")
    sil = scan.get("silver") or {}
    if sil.get("new"):
        print(f"\n👀 SILVER SIGNALS (signal-only · {cfg.get('silver_contract','SILVERMIC')} 1 kg · "
              f"margin ~₹{sil.get('margin', 0):,.0f} — cash ho to hi trade):")
        for r in sil["new"]:
            print(f"   {r['system']:11s} ref ₹{r['ref_px']:,.0f}/kg | target ₹{r['target_px']:,.0f} (+{r['tgt_pct']:g}%) | "
                  f"stop ₹{r['stop_px']:,.0f} (−{r['stop_pct']:g}%) | max {r['max_hold']} din | 1 lot risk ~₹{r['risk_inr']:,.0f}")
    elif sil.get("note"):
        print(f"\n📎 Silver: {sil['note']}")

    if mgr:
        print("\n📌 OPEN POSITIONS:")
        for m in mgr:
            flag = "🔴 CLOSE KARO" if m["status"] == "EXIT_ADVICE" else "🟢 HOLD"
            print(f"   #{m['order_id']} {m['system']:16s} entry ₹{m['entry']:,.0f} -> ab ₹{m['last']:,.0f} "
                  f"({m['unreal']:+.2f}%) {m['days']} din | {flag} — {m['note']}")
    if len(p):
        print(f"\n⏳ PENDING orders (fill hone par 'fill <id> --price <price>' chalao): "
              f"{', '.join('#'+str(int(float(x))) for x in p.order_id)}")
    if mgr:
        print("   ⓘ Protection: Super Order = automatic (target+SL ek saath) | alag orders = ROZ dobara lagao, "
              "aur ek fill ho jaye to doosra turant CANCEL karo (warna ulta position).")
    print(f"\nRules: 1 lot = {cfg['gram_per_lot']:g} g | max {cfg['max_open']} open positions | "
          f"SKIP band: open ref (₹{scan['px']:,.0f}) se +{cfg.get('gap_dead_lo',0.5):g}% se +{cfg.get('gap_dead_hi',1.0):g}% ke beech, "
          f"ya +{cfg.get('gap_hard',2.5):g}%+ upar "
          f"| cost ₹{cfg['cost_inr_per_lot']:.0f}/trade | margin ~₹{cfg.get('margin_per_lot', 1352):,.0f}/lot "
          f"(jitne lots ek saath, utna margin — cash check: Dhan app me)")
    print("Roz ka routine: subah 8:45 par `python3 scripts/ms_algo.py run` -> sheet -> 9:00 par order -> fill likho.")


def html_sheet(cfg, scan, mgr, D, path):
    p = pending_orders(); pos = pos_load(); j = jrn_load()
    def card(r):
        return (f"<div class='card in'><div class='h'><b>#{r['order_id']} {r['system']}</b>"
                f"<span class='side'>BUY</span></div><div class='rule'>{r['rule']}</div>"
                f"<table><tr><td>Contract</td><td><b>{r['contract']}</b> <span class='small'>"
                f"({'sec ' + str(r['contract_sec_id']) + ', exp ' + str(r['contract_expiry']) if str(r['contract_sec_id'] or '') not in ('','nan') else '⚠️ expiry master se nahi mila — Dhan app me confirm karo'})</span></td></tr>"
                f"<tr><td>Lots</td><td><b>{r['lots']:g} × {cfg['contract']} (1g each)</b></td></tr>"
                f"<tr><td>Ref price</td><td>₹{r['ref_px']:,.0f}/g</td></tr>"
                f"<tr><td>SKIP agar open ≥</td><td class='red'>₹{r['skip_above']:,.0f}</td></tr>"
                f"<tr><td>Target</td><td class='green'>₹{r['target_px']:,.0f} (+{r['tgt_pct']}%)</td></tr>"
                f"<tr><td>Stop (SL-M)</td><td class='red'>₹{r['stop_px']:,.0f} (−{r['stop_pct']}%)</td></tr>"
                f"<tr><td>Max hold</td><td>{r['max_hold']} din</td></tr></table></div>")
    newc = "".join(card(r) for r in scan["new"]) or "<div class='card'>Aaj koi naya entry nahi.</div>"
    sil = scan.get("silver") or {}
    silc = ""
    if sil.get("new"):
        silc = ("<div class='card'><div class='h'><b>👀 Silver signals (signal-only)</b>"
                f"<span class='small'>{cfg.get('silver_contract','SILVERMIC')} 1 kg · margin ~₹{sil.get('margin',0):,.0f}"
                " — cash ho to hi trade karo</span></div>")
        for r in sil["new"]:
            silc += (f"<table><tr><td>{r['system']} — {r['name']}</td></tr>"
                     f"<tr><td>Ref ₹{r['ref_px']:,.0f}/kg · Target <span class='green'>₹{r['target_px']:,.0f} (+{r['tgt_pct']:g}%)</span> · "
                     f"Stop <span class='red'>₹{r['stop_px']:,.0f} (−{r['stop_pct']:g}%)</span> · {r['max_hold']} din · "
                     f"1 lot risk ~₹{r['risk_inr']:,.0f}</td></tr></table>")
        silc += "</div>"
    posr = ""
    for m in mgr:
        cls = "red" if m["status"] == "EXIT_ADVICE" else "green"
        act = "CLOSE KARO ✖" if m["status"] == "EXIT_ADVICE" else "HOLD"
        posr += (f"<tr><td>#{m['order_id']} {m['system']}</td><td>₹{m['entry']:,.0f}</td><td>₹{m['last']:,.0f}</td>"
                 f"<td class='{cls}'>{m['unreal']:+.2f}%</td><td>{m['days']}d</td><td class='{cls}'>{act}</td>"
                 f"<td class='small'>{m['note']}</td></tr>")
    if not posr:
        posr = "<tr><td colspan=7 class='small'>koi open position nahi</td></tr>"
    kpi = "<div class='kpi'>abhi koi closed trade nahi</div>"
    if len(j):
        j2 = j.copy(); j2["pnl_inr"] = j2.pnl_inr.astype(float); j2["pnl_pct"] = j2.pnl_pct.astype(float)
        kpi = (f"<div class='kpi'><b>{len(j2)}</b> trades · <b>{(j2.pnl_inr>0).mean()*100:.0f}%</b> win · "
               f"<b class='{'green' if j2.pnl_inr.sum()>=0 else 'red'}'>₹{j2.pnl_inr.sum():+,.0f}</b> total · "
               f"avg <b>{j2.pnl_pct.mean():+.2f}%</b>/trade</div>")
    prov = ""
    if scan.get("provisional"):
        prov += ("<div class='warn'>⚠️ <b>PROVISIONAL</b>: signal bar ka COMEX session abhi band nahi hua — "
                 "02:45 IST ke baad sheet dobara chalao, tab final signal milega.</div>")
    prov += f"<div class='sub'>⏱ entry day <b>{scan['entry_day']}</b> (MCX 9:00 AM) · pending {len(p)} · open {scan['n_open']}</div>"
    html = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MS Algo Sheet</title><style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0f1115;color:#e6e8ee;margin:0;padding:14px}}
h1{{font-size:19px;margin:0 0 4px}} .sub{{color:#9aa3b2;font-size:12px;margin-bottom:12px}}
.card{{background:#171a21;border:1px solid #262b36;border-radius:12px;padding:12px;margin:10px 0}}
.card.in{{border-color:#2f6b46}} .h{{display:flex;justify-content:space-between;align-items:center;font-size:15px}}
.side{{background:#173d26;color:#5ce08a;padding:2px 8px;border-radius:8px;font-size:12px}}
.rule{{color:#9aa3b2;font-size:12px;margin:6px 0}}
table{{width:100%;border-collapse:collapse;font-size:13px}} td{{padding:3px 0;border-bottom:1px solid #1e2330}}
.green{{color:#5ce08a}} .red{{color:#ff6b6b}} .small{{color:#9aa3b2;font-size:11px}}
.kpi{{background:#171a21;border:1px solid #262b36;border-radius:12px;padding:10px;font-size:13px;margin:8px 0}}
.warn{{background:#3a2a12;border-left:3px solid #e0a93b;color:#f3d9a4;padding:10px;border-radius:6px;font-size:12px;margin:8px 0}}
.notebox{{background:#1b1f29;border-left:3px solid #c9a227;padding:10px;border-radius:6px;font-size:12px;color:#cfd5e2;margin-top:14px}}
</style></head><body>
<h1>🔔 MS Algo — Action Sheet</h1>
<div class="sub">{now_ist().strftime('%d-%b-%Y %H:%M IST')} · signal bar <b>{scan['sig_date']}</b> · market {scan['last_bar']} ·
state <b>{scan['state']}</b> · RSI14 {scan['r14']:.1f} · %B {scan['pb']:.2f} · G/S {scan['gs']:.0f}th · DXY {scan['dxy']:.1f} ({scan['dxy_d']:+.2f}%)</div>
{prov}
{kpi}
<h3 style="font-size:14px;color:#cbd3e1">Aaj ke orders</h3>{newc}
{silc}
<h3 style="font-size:14px;color:#cbd3e1">Open positions</h3>
<div class="card"><table><tr><th align="left">System</th><th align="left">Entry</th><th align="left">Ab</th><th align="left">P&L</th><th align="left">Din</th><th align="left">Action</th><th align="left">Note</th></tr>{posr}</table></div>
<div class="notebox"><b>Protection:</b> Super Order me target+SL automatic hote hain · agar alag orders lagaye ho (fallback) — ROZ dobara lagao, aur ek fill hone par doosra <b>turant cancel</b> karo.</div>
<div class="notebox"><b>Rules:</b> 1 lot = {cfg['gram_per_lot']:g} g {cfg['contract']} · max {cfg['max_open']} positions ·
skip band: open ref se <b>+{cfg.get('gap_dead_lo',0.5):g}% se +{cfg.get('gap_dead_hi',1.0):g}%</b> ke beech ya <b>+{cfg.get('gap_hard',2.5):g}%+</b> upar = chhod do · stop = <b>SL-M</b> order, target = limit order, dono <b>usi din</b> lagao ·
cost ₹{cfg['cost_inr_per_lot']:.0f}/trade · <b>quick-book ON:</b> din-{cfg.get('quick_book_day',5):g} par +{cfg.get('quick_book_pct',1.5):g}% ho to book kar do ·
target/time-exit par position band karke algo me `close` likho.</div>
</body></html>"""
    open(path, "w").write(html)


# ---------------------------------------------------------------- self-test
def _slots(A, K=4, add=1.0):
    keep = []
    for _, g in A.groupby(["metal", "side"]):
        acc = []
        for _, r in g.sort_values(["entry_dt", "prio"]).iterrows():
            acc = [a for a in acc if a["exit_dt"] > r.entry_dt]
            if len(acc) < K:
                keep.append(r.name); acc.append(dict(exit_dt=r.exit_dt, entry=r.entry))
            else:
                ref = acc[-1]["entry"]
                if r.entry <= ref * (1 - add / 100):
                    keep.append(r.name); acc.append(dict(exit_dt=r.exit_dt, entry=r.entry))
    return A.loc[sorted(keep)].sort_values("entry_dt").reset_index(drop=True)


def _bstat(b):
    yrs = (b.exit_dt.max() - b.entry_dt.min()).days / 365.25
    r = b.pnl_net.values
    eq = b.groupby("exit_dt").R.sum().reindex(pd.date_range(b.entry_dt.min(), b.exit_dt.max(), freq="D"), fill_value=0).cumsum()
    dd = float((eq - eq.cummax()).min())
    return dict(n=len(b), per_mo=round(len(b) / (yrs * 12), 2), win=round(100 * (r > 0).mean(), 1),
                avg=round(float(r.mean()), 2), R_yr=round(float(b.R.sum() / yrs), 2), DD_R=round(dd, 1))


def selftest(cfg):
    """Algo ki logic = published production book? (frozen panel par dobara chala ke milao)"""
    try:
        from ms_lib import m_engine, m_stats
        have_engine = True
    except Exception:
        m_engine = m_stats = None; have_engine = False
    print("=" * 100)
    print("SELF-TEST — algo ke signals/engine se production book dobara banate hain (frozen data, tail OFF)")
    print("=" * 100)
    D = build_frame(cfg, use_tail=False)
    F = fam_masks(D)
    sysdf = system_table().sort_values("prio").reset_index(drop=True)
    ref = pd.read_csv(SCREEN_CSV).set_index("family")       # standalone family stats (book-selection se pehle)
    rows, TR = [], {}
    if not have_engine:
        print("\n⚠️  ms_lib (backtest engine) is install me nahi hai — engine ke bina data-integrity check chal raha hai.")
        fams = fam_masks(build_frame(cfg, use_tail=False))
        counts = {s.fam: int(fams[s.fam].fillna(False).sum()) for _, s in sysdf.iterrows()}
        base_f = f"{MS}/data/fam_trigger_baseline.csv"
        if os.path.exists(base_f):
            base = pd.read_csv(base_f).set_index("family")["triggers"]
            cmp = pd.DataFrame([dict(family=k, triggers=c, baseline=int(base.get(k, -1)),
                                     diff=c - int(base.get(k, -1))) for k, c in counts.items()])
            print(cmp.to_string(index=False))
            ok_all = bool((cmp["diff"].abs() == 0).all())
            print((f"\n✅ DATA CHECK PASS — saari {len(cmp)} families ke triggers published baseline se EXACT match "
                   "(panel/data theek hai)" if ok_all else
                   "\n❌ MISMATCH — data ya code me kuch badla hai, upar diff dekho (signals par bharosa mat karo)"))
        else:
            print("baseline file nahi mili — abhi ke counts (data verify ke liye baseline chahiye):")
            print(pd.Series(counts).to_string())
        return
    for _, s in sysdf.iterrows():
        t = m_engine(F[s.fam], "LONG", D, s.tgt, s.stp, s.hold, cost_bps=6.0, stop_on_close=False, non_overlap=True)
        st_ = m_stats(t)
        r = ref.loc[s.fam] if s.fam in ref.index else None
        rows.append(dict(family=s.fam, cfg=f"{s.tgt:g}/{s.stp:g}/{s.hold}", n_new=st_["n"],
                         n_ref=int(r["n"]) if r is not None else -1, dn=st_["n"] - (int(r["n"]) if r is not None else -1),
                         win_new=st_["win_pct"], win_ref=float(r["win"]) if r is not None else np.nan,
                         dwin=round(st_["win_pct"] - (float(r["win"]) if r is not None else np.nan), 1),
                         avg_new=st_["avg_net_pct"], avg_ref=float(r["avg"]) if r is not None else np.nan,
                         davg=round(st_["avg_net_pct"] - (float(r["avg"]) if r is not None else np.nan), 2)))
        TR[s.fam] = t.assign(family=s.fam, metal="gold", side="LONG")
    cmp = pd.DataFrame(rows)
    print("\nper-family (standalone screen se comparison — n / win / avg):")
    print(cmp.to_string(index=False))
    ok_sys = (cmp.dn.abs() <= 3).all() and (cmp.dwin.abs() <= 1.5).all() and (cmp.davg.abs() <= 0.15).all()
    A = pd.concat([TR[s.fam].assign(prio=int(s.prio)) for _, s in sysdf.iterrows()], ignore_index=True)
    A["entry_dt"] = pd.to_datetime(A.entry_date); A["exit_dt"] = pd.to_datetime(A.exit_date)
    b = _slots(A, K=4, add=1.0)
    o = _bstat(b)
    _mf = f"{MS}/outputs/ms_gold_prod_matrix_v4.csv"
    _use = _mf if os.path.exists(_mf) else f"{MS}/outputs/ms_gold_prod_matrix.csv"
    ref_row = pd.read_csv(_use)
    _pat = "V4" if os.path.exists(_mf) else "TierC"
    ref_row = ref_row[ref_row.policy.str.contains(_pat) & ref_row.policy.str.contains("K=4")].iloc[0]
    print(f"\nBOOK ({_pat} K=4) naya     : n={o['n']} | {o['per_mo']}/mo | win {o['win']}% | avg {o['avg']}% | R/yr {o['R_yr']} | DD {o['DD_R']}R")
    print(f"BOOK ({_pat} K=4) published : n={ref_row.n} | {ref_row.per_mo}/mo | win {ref_row.win}% | avg {ref_row.avg}% | R/yr {ref_row.R_yr} | DD {ref_row.DD_R}R")
    ok_book = abs(o["per_mo"] - float(ref_row.per_mo)) <= 0.1 and abs(o["win"] - float(ref_row.win)) <= 1.0 and abs(o["avg"] - float(ref_row.avg)) <= 0.08
    print(f"\n{'✅ SELF-TEST PASS — algo production book se match karta hai' if (ok_sys and ok_book) else '❌ SELF-TEST FAIL — neeche differences dekho (script mein kuch badla gaya hai)'}")
    return ok_sys and ok_book


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    for c in ("update", "scan", "run", "manage", "report", "status", "selftest"):
        sub.add_parser(c)
    f = sub.add_parser("fill"); f.add_argument("id"); f.add_argument("--price", required=True); f.add_argument("--lots", default=None)
    s = sub.add_parser("skip"); s.add_argument("id"); s.add_argument("--why", default="")
    cl = sub.add_parser("close"); cl.add_argument("id"); cl.add_argument("--price", required=True); cl.add_argument("--why", default="")
    A = ap.parse_args()
    cfg = cfg_load()
    if A.cmd is None:
        print(__doc__); return

    if A.cmd == "fill":
        cmd_fill(cfg, A); return
    if A.cmd == "skip":
        cmd_skip(cfg, A); return
    if A.cmd == "close":
        cmd_close(cfg, A); return
    if A.cmd == "report":
        report(cfg); return
    if A.cmd == "selftest":
        selftest(cfg); return
    if A.cmd == "status":
        print(json.dumps(cfg, indent=1))
        print("\npending orders:"); print(pending_orders().to_string(index=False) if len(pending_orders()) else "  koi nahi")
        print("\nopen positions:"); print(pos_load().to_string(index=False) if len(pos_load()) else "  koi nahi")
        return

    if A.cmd in ("update", "run"):
        print("1) data refresh (yfinance)...")
        refresh_market()
    if A.cmd in ("scan", "run"):
        D = build_frame(cfg)
        # QA: live derived vs panel frozen
        scan = signal_scan(cfg, D)
        mgr = manage(cfg, D) if A.cmd == "run" else []
        console_sheet(cfg, scan, mgr, D)
        html_sheet(cfg, scan, mgr, D, f"{MS}/outputs/algo_sheet.html")
        html_sheet(cfg, scan, mgr, D, f"{MS}/outputs/algo_sheet_{now_ist().date()}.html")
        print(f"\nsaved: outputs/algo_sheet.html (+ date wala copy)")
        # DEEP HEALTH CHECK (report bhejne se pehle) — fail ho to laal nishaan
        try:
            import healthcheck as HC
            h = HC.run_health(cfg, D, scan)
            HC.print_table(h)
            HC.log_health(h)
            if h["overall"] == "RED":
                print("\n⛔⛔ RED ZONE — aaj ka order MAT lagao jab tak ye theek na ho ⛔⛔")
        except Exception as e:
            print(f"(health check nahi chala: {str(e)[:80]})")
    if A.cmd == "manage":
        D = build_frame(cfg)
        mgr = manage(cfg, D)
        for m in mgr:
            print(f"#{m['order_id']} {m['system']:16s} entry ₹{m['entry']:,.0f} -> ₹{m['last']:,.0f} "
                  f"({m['unreal']:+.2f}%) {m['days']}d | {m['status']} — {m['note']}")
        if not mgr:
            print("koi open position nahi")


if __name__ == "__main__":
    main()
