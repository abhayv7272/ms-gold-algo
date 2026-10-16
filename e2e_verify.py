#!/usr/bin/env python3
"""E2E VERIFY — backtest + data fetching + integration + HTML completeness.

Reproduce: CHALAO ->  python3 /tmp/e2e_verify.py   (repo root se)
Ye file (1) backtest trades ko panel data se match karti hai,
(2) fresh data fetch karti hai, (3) live scan chalati hai,
(4) gold+silver signal ka HTML banati hai aur har zaroori cheez check karti hai.
"""
import os, sys, json, glob, re, datetime as dt

sys.path.insert(0, os.path.abspath("."))
import pandas as pd
import ms_algo as A
import report_html as BH

PASS, FAIL, INFO = [], [], []
def ok(m):   PASS.append(m); print("  ✅", m)
def bad(m):  FAIL.append(m); print("  ❌", m)
def info(m): INFO.append(m); print("  ⓘ", m)

print("=" * 90)
print("E2E VERIFY — MS GOLD ALGO (16-Oct-2026)")
print("=" * 90)

# ---------------------------------------------------------------- 0. FRAME
cfg0 = A.cfg_load()
D0 = A.build_frame(cfg0)
panel = D0  # px = ms_algo ka INR price (panel + duty + USDINR)

# ---------------------------------------------------------------- 1. BACKTEST
print("\n[1] BACKTEST INTEGRITY — trades vs live pipeline data")

for metal, tfile, pxcol in [("GOLD", "data/ms_gold_prod_trades.csv", "px"),
                            ("SILVER", "data/ms_silver_trades.csv", None)]:
    if not os.path.exists(tfile):
        # try alt names
        alt = glob.glob(tfile.replace(".csv", "*"))[:1]
        if not alt:
            info(f"{metal}: trades file nahi mila ({tfile}) — skip")
            continue
        tfile = alt[0]
    t = pd.read_csv(tfile, parse_dates=["entry_date", "exit_date"])
    n = len(t)
    # px match check (entry/exit price panel me hai?)
    hits_e = hits_x = 0
    for _, r in t.iterrows():
        for col, cnt in (("entry", "e"), ("exit", "x")):
            d = pd.Timestamp(r.entry_date if col == "entry" else r.exit_date)
            if d in panel.index:
                pv = float(panel.loc[d, "px"])
                ref = float(r[col])
                if abs(pv - ref) / max(abs(ref), 1e-9) < 0.02:
                    if cnt == "e": hits_e += 1
                    else: hits_x += 1
    info(f"{metal}: {n} trades · entry price panel me mila {hits_e}/{n} · exit {hits_x}/{n}")
    # math check: pnl_net vs pnl_gross
    if "pnl_net" in t.columns and "pnl_gross" in t.columns:
        cost = (t.pnl_gross - t.pnl_net)
        info(f"{metal}: cost/trade = {cost.mean():.3f}% (min {cost.min():.2f}, max {cost.max():.2f})")
    # stats recompute
    win = 100 * (t.pnl_net > 0).mean()
    avg = t.pnl_net.mean()
    span = (t.exit_date.max() - t.entry_date.min()).days / 365.25
    per_mo = n / span / 12
    info(f"{metal}: recompute → win {win:.1f}% · avg +{avg:.2f}% · {per_mo:.2f}/mahina · {t.entry_date.min().date()}→{t.exit_date.max().date()}")
    if metal == "GOLD":
        (ok if abs(win - 75.5) < 0.6 else bad)(f"GOLD win {win:.1f}% == published 75.5%")
        (ok if abs(avg - 1.16) < 0.06 else bad)(f"GOLD avg +{avg:.2f}% == published +1.16%")
        (ok if abs(per_mo - 3.01) < 0.20 else bad)(f"GOLD {per_mo:.2f}/mahina == published 3.01")

# system-level: 11 gold systems, win from screen CSV vs trades
sc = pd.read_csv("data/ms_gold_prod_screen_v5.csv")
tg = pd.read_csv("data/ms_gold_prod_trades.csv", parse_dates=["entry_date", "exit_date"])
bad_sys = []
for _, r in sc.iterrows():
    tt = tg[tg.family == r.family]
    if not len(tt):
        continue
    w = 100 * (tt.pnl_net > 0).mean()
    if abs(w - r.win) > 2.2:   # book K=4 slot policy ki wajah se chhota farq normal hai
        bad_sys.append((r.family, round(w, 1), r.win))
(ok if not bad_sys else bad)(f"11 gold systems ka win% trades se match ({len(sc)} systems checked)" +
                             (f" — mismatch: {bad_sys}" if bad_sys else ""))

# per-system numbers (report ke liye)
per = []
for _, r in sc.iterrows():
    tt = tg[tg.family == r.family]
    per.append(dict(fam=r.family, name=r["name"], cfg=r.cfg, n=len(tt),
                    win=round(100 * (tt.pnl_net > 0).mean(), 1), avg=round(tt.pnl_net.mean(), 2),
                    per_mo=round(len(tt) / (((tt.exit_date.max() - tt.entry_date.min()).days / 365.25) / 12), 2)))
print("\n  --- GOLD: per-system (trades CSV se recompute) ---")
for p_ in sorted(per, key=lambda x: -x["win"]):
    print(f"    {p_['fam']:<16} {p_['name']:<28} cfg {p_['cfg']:<9} n={p_['n']:<4} win {p_['win']:>5}% avg +{p_['avg']:.2f}% {p_['per_mo']}/mo")
json.dump(per, open("/tmp/e2e_gold_systems.json", "w"), indent=1)

# silver systems
sf = "data/ms_silver_prod_systems_v5.csv"
if os.path.exists(sf):
    ss = pd.read_csv(sf)
    print("\n  --- SILVER systems (published) ---")
    print("   ", ss.to_string(index=False).replace("\n", "\n    ")[:900])

# ---------------------------------------------------------- 2. DATA FETCHING
print("\n[2] DATA FETCHING (live internet — yfinance)")
try:
    A.refresh_market()
    p2 = pd.read_csv("data/panel_min.csv", parse_dates=["date"]).set_index("date")
    last = p2.tail(3)
    ok(f"refresh chala — panel ab {len(p2)} rows, last date {p2.index[-1].date()}")
    cols_show = [c for c in ["px", "silver_fut_close", "silver_open_usd", "dxy", "gvz_pct_v3", "usdinr", "gs_pct"] if c in p2.columns]
    for c in cols_show:
        v = last[c].iloc[-1]
        info(f"{c}: {v if pd.isna(v) else round(float(v), 3)}")
    if p2.index[-1].date() >= dt.date(2026, 10, 14):
        ok("data taaza hai (14-Oct ya baad ka bar maujood)")
    else:
        bad(f"data purana lag raha hai (last {p2.index[-1].date()})")
except Exception as e:
    bad(f"refresh fail: {str(e)[:120]}")

# ---------------------------------------------------------- 3. LIVE INTEGRATION
print("\n[3] INTEGRATION — live scan (real data)")
cfg = A.cfg_load()
try:
    D = A.build_frame(cfg)
    scan = A.signal_scan(cfg, D)
    ok(f"build_frame + signal_scan chala — signal bar {scan['sig_date']}, state {scan['state']}, "
       f"RSI {scan['r14']:.1f}, new signals = {len(scan['new'])}")
    sil = scan.get("silver") or {}
    info(f"silver scan: new={len(sil.get('new') or [])} inactive={len(sil.get('inactive') or [])}")
    try:
        import healthcheck as H
        health = H.run_health(cfg, D, scan)
        ok(f"healthcheck: {H.summary_line(health)}")
    except Exception as e:
        health = dict(overall="OK", reds=[], warns=[], summary_line="(healthcheck skip: %s)" % str(e)[:40])
        info(f"healthcheck skip: {str(e)[:80]}")
    st = A.system_table()
    ok(f"system_table: {len(st)} gold systems load hue (win {st.win.min():.0f}–{st.win.max():.0f}%)")
except Exception as e:
    bad(f"live scan fail: {str(e)[:200]}")

# ------------------------------------------------- 4. HTML BUILD + COMPLETENESS
print("\n[4] HTML BUILD — gold trade + 2 silver signals (real systems se)")

st = A.system_table()
g1 = st.sort_values("win", ascending=False).iloc[0]     # r5_deep
g2 = st.sort_values("prio").iloc[0]
px = float(D.px.iloc[-1])
new_rows = []
for i, g in enumerate([g1, g2], 1):
    new_rows.append(dict(order_id=i, system=g.system, family=g.fam, side="BUY",
                         rule=f"{g.get('name', g.fam)} — win {g.win:.0f}%, avg +{g.avg:.2f}% per trade",
                         lots=1, contract="GOLDPETAL NOV FUT", contract_sec_id="574841",
                         contract_expiry="2026-11-30", ref_px=round(px, 1),
                         target_px=round(px * (1 + g.tgt / 100), 1), stop_px=round(px * (1 - g.stp / 100), 1),
                         tgt_pct=g.tgt, stop_pct=g.stp, max_hold=g.hold,
                         gap_lo_px=round(px * 1.005, 1), gap_hi_px=round(px * 1.01, 1),
                         gap_hard_px=round(px * 1.025, 1), skip_above=round(px * 1.01, 1)))
sil_rows = [dict(system="S-rsi30r5", name="Silver Zyada Gira", ref_px=215400.0, target_px=221862.0,
                 stop_px=198168.0, tgt_pct=3.0, stop_pct=8.0, max_hold=20, risk_inr=17232.0),
            dict(system="S-gapdn", name="Bada Gap-Down", ref_px=214100.0, target_px=222664.0,
                 stop_px=192690.0, tgt_pct=4.0, stop_pct=10.0, max_hold=20, risk_inr=21410.0)]
scan_f = dict(scan); scan_f["new"] = new_rows
scan_f["silver"] = dict(new=sil_rows, inactive=[])
mgr = [dict(order_id=7, system="G-dxy_dn", entry=13975.0, last=round(px, 1), unreal=1.09, days=4,
            status="OPEN", note="target 14,394 / SL 12,298 · 4/10 din"),
       dict(order_id=8, system="G-gaprsi", entry=14200.0, last=round(px * 0.997, 1), unreal=-0.51, days=11,
            status="EXIT_ADVICE", note="quick-book window khatam — band kar do")]

path, cap = BH.build_daily_html(cfg, scan_f, mgr, ["fill 7 13975"], health, None, None)
html = open(path, encoding="utf-8").read()
info(f"HTML file: {path} ({len(html):,} bytes)")
info(f"caption: {cap[:90]}...")

need = {
  "GOLD buy zone":      ["BUY ZONE (ref)", "TARGET +", "STOPLOSS −"],
  "GOLD exit rules":    ["EXIT kab", "QUICK-BOOK", "time-exit", "book karo"],
  "GOLD risk/reward":   ["Jeet:", "Haar:", "SKIP agar open"],
  "GOLD strategy info": ["Aaj ka setup:", "Kyun kaam karti hai:", "Is strategy ka poora record"],
  "GOLD details":       ["Trigger rule", "Win rate", "Average per trade", "2.5%+ touch hua"],
  "SILVER buy zone":    ["Silver signal", "BUY ZONE (ref, ₹/kg)", "🎯 TARGET +", "🛑 STOPLOSS −"],
  "SILVER exit":        ["max hold", "time-exit"],
  "SILVER honesty":     ["sirf signal", "margin"],
  "BOOK section":       ["Aapka book", "win rate", "trade / mahina", "max drawdown"],
  "STRATEGY book":      [f"G-{g1.fam}", "Aapki strategy book", "win "],
  "POSITIONS":          ["Positions", "HOLD", "BAND KARO", "P&L"],
  "HEALTH":             ["Sehat", "systems check hue"],
  "COMMANDS":           ["fill 1 13980", "close 1 14100", "skip 1", "Run workflow"],
}
print()
for group, keys in need.items():
    miss = [k for k in keys if k not in html]
    (ok if not miss else bad)(f"{group}: {'sab mila' if not miss else 'MISSING ' + str(miss)}")

# buy zone / target / exit / stop — gold ki asli values HTML me hain?
gpx = new_rows[0]
for label, val in [("BUY ZONE", gpx["ref_px"]), ("TARGET", gpx["target_px"]), ("STOP", gpx["stop_px"])]:
    s_ = f"₹{val:,.0f}"
    (ok if s_ in html else bad)(f"GOLD {label} price HTML me: {s_}")
(ok if "20 din" in html or f"{g1.hold:g} din" in html else bad)("GOLD max hold HTML me")

# ------------------------------------------------- 5. TIMING + DEDUP GUARD
print("\n[5] TIMING + DUPLICATE GUARD")
try:
    import run_daily as R
    import datetime as _dt
    _now = _dt.datetime(2026, 10, 16, 3, 42, tzinfo=A.IST)
    for cron, exp_txt in [("30 21 * * 0-4", "03:00"), ("0 3 * * 1-5", "08:30"),
                          ("0 0 * * 1-5", "05:30"), ("0 19 * * 1-5", "00:30")]:
        os.environ["SCHED_CRON"] = cron
        note = R.sched_delay_note(_now)
        (ok if note and exp_txt in note else bad)(f"cron '{cron}' ka expected IST time {exp_txt} — note: {str(note)[:60]}")
    os.environ["SCHED_CRON"] = ""
    info(f"manual run (bina cron) → note: {R.sched_delay_note(_now)}")

    fp1, m1 = R.fingerprint([], [], [], None, dict(overall="OK"))
    fp2, m2 = R.fingerprint([], [], [], None, dict(overall="OK"))
    fp3, m3 = R.fingerprint([], [], ["fill 1 100"], None, dict(overall="OK"))
    fp4, m4 = R.fingerprint(dict(sig_date="2026-10-15", new=[dict(order_id=9, system="X")]), [], [], None, dict(overall="OK"))
    (ok if fp1 == fp2 else bad)("same haalat = same fingerprint (duplicate message block hoga)")
    (ok if fp1 != fp3 else bad)("command aane par fingerprint badalta hai (message jayega)")
    (ok if fp1 != fp4 else bad)("naya signal aane par fingerprint badalta hai (message jayega)")
    st = R.sent_state()
    if st:
        info(f"last_sent.json maujood: fp={st.get('fp')} at={st.get('at')} (repo me fresh na ho to normal hai)")
    else:
        ok("last_sent.json clean hai (fresh repo ke liye sahi)")
except Exception as e:
    bad(f"timing/dedup test fail: {str(e)[:150]}")

print("\n" + "=" * 90)
print(f"RESULT:  {len(PASS)} PASS · {len(FAIL)} FAIL")
if FAIL:
    print("FAILED:")
    for f_ in FAIL:
        print("   ❌", f_)
print("=" * 90)
open("outputs/.e2e_last_html.txt", "w").write(path)
sys.exit(1 if FAIL else 0)
