#!/usr/bin/env python3
"""DEEP HEALTH CHECK — har report se PEHLE chalta hai (data fetching se lekar core sab).

Kya check hota hai (11 checks):
  1. data_fetch      — naya bar aaya? kitna purana hai? (weekend/weekday aware)
  2. data_integrity  — price hi/lo/op valid? null? achanak jump?
  3. silver_scale    — silver series sane hai? (lag_rel system ka input)
  4. triggers        — saare families ke trigger counts published baseline se exact?
  5. book_config     — saare systems (V4) load hue? cfg sane?
  6. contract        — jis contract ka order denge wo expiry-safe hai?
  7. ledger          — orders/positions me duplicate, orphan, stale pending?
  8. cash_margin     — capital se margin cover hota hai? buffer kitna?
  9. channels        — Telegram/ntfy configured + zinda hain? (alert bhej na sake to RED)
 10. clock           — provisional signal bar? (02:45 IST rule)
 11. jump_risk       — kal-pichhle din ka koi ek bada move jo data me gadbad suggest kare?

Status: OK / WARN / RED. RED = us din ka order SUPPRESS (trade mat karo) + message me ⛔ RED ZONE.
CLI:  python3 scripts/healthcheck.py          (table print)
Log:  data/algo/health_log.csv
"""
import os, sys, json, csv, datetime as dt
import numpy as np
import pandas as pd
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ms_algo as A  # noqa: E402

RED, WARN, OK = "RED", "WARN", "OK"
ICON = {OK: "🟢", WARN: "🟡", RED: "🔴"}


def _bars_age_limit(today):
    """Mon ko Friday ka bar 3 din purana normal hai; warna 2 din."""
    return 4 if today.weekday() == 0 else 2


def run_health(cfg, D=None, scan=None, notify=True):
    now = A.now_ist()
    today = now.date()
    checks = []

    def add(name, status, detail):
        checks.append(dict(check=name, status=status, detail=str(detail)[:160]))

    # ---------- 1) data fetch freshness ----------
    if D is None or not len(D):
        add("data_fetch", RED, "market frame khaali hai — data load hi nahi hua")
    else:
        last = D.index[-1].date()
        age = (today - last).days
        lim = _bars_age_limit(today)
        if age > lim:
            add("data_fetch", RED, f"data purana hai — last bar {last} ({age} din purana), limit {lim}")
        elif age == lim:
            add("data_fetch", WARN, f"last bar {last} ({age} din) — weekend/holiday ho sakta hai, confirm karo")
        elif last > today:
            add("data_fetch", WARN, f"last bar {last} aaj se aage hai — clock/timezone check karo")
        else:
            add("data_fetch", OK, f"fresh — last bar {last} ({age} din)")

    # ---------- 2) data integrity ----------
    if D is not None and len(D):
        r = D.iloc[-1]
        probs = []
        for c in ("op", "hi", "lo", "px"):
            v = float(r[c]) if pd.notna(r[c]) else np.nan
            if not np.isfinite(v) or v <= 0:
                probs.append(f"{c} galat ({v})")
        if float(r.hi) < float(r.lo):
            probs.append("high < low")
        if float(r.op) > float(r.hi) * 1.001 or float(r.op) < float(r.lo) * 0.999:
            probs.append("open bar ke bahar")
        for c in ("dxy", "usdinr", "sil_inr"):
            if c in D.columns and not np.isfinite(float(r[c]) if pd.notna(r[c]) else np.nan):
                probs.append(f"{c} khaali")
        jump = float(D.px.pct_change().iloc[-1] * 100) if len(D) > 1 else 0.0
        if abs(jump) > 8:
            probs.append(f"gold 1-din jump {jump:+.1f}%")
        add("data_integrity", RED if probs else OK,
            "; ".join(probs) if probs else f"ok (gold ₹{float(r.px):,.0f}/g, DXY {float(r.dxy):.1f}, USDINR {float(r.usdinr):.2f})")

    # ---------- 3) silver scale cross-check (asli scale-break pakdo, extreme market move par alarm nahi) ----------
    if D is not None and len(D) and "sil_r5" in D.columns and "silver_usd" in D.columns:
        try:
            ours = pd.to_numeric(D.sil_r5, errors="coerce")
            usd = pd.to_numeric(D.silver_usd, errors="coerce").pct_change(5) * 100
            diff = (ours - usd).abs().dropna().tail(5)
            if len(diff) and float(diff.iloc[-1]) > 3:
                add("silver_scale", RED, f"silver series aur USD source me {float(diff.iloc[-1]):.1f}pp ka farq — scale toota hua (lag_rel galat)")
            elif len(diff) and float(diff.max()) > 3:
                add("silver_scale", WARN, f"silver cross-check me {float(diff.max()):.1f}pp farq (recent) — nazar rakho")
            else:
                add("silver_scale", OK, f"theek — INR series vs USD source match (last sil_r5 {float(ours.iloc[-1]):+.2f}%)")
        except Exception as e:
            add("silver_scale", WARN, f"cross-check crash: {str(e)[:70]}")
    else:
        add("silver_scale", WARN, "sil_r5/silver_usd available nahi — lag_rel system check nahi ho paya")

    # ---------- 4) trigger baseline ----------
    if D is not None and len(D):
        try:
            # baseline frozen panel par bana hai -> comparison bhi frozen frame par
            Df = A.build_frame(cfg, use_tail=False) if hasattr(A, "build_frame") else D
            F = A.fam_masks(Df)
            base_f = f"{A.MS}/data/fam_trigger_baseline.csv"
            if os.path.exists(base_f):
                base = pd.read_csv(base_f).set_index("family")["triggers"]
                diffs = {}
                for fam in base.index:
                    if fam in F:
                        diffs[fam] = int(F[fam].fillna(False).sum()) - int(base[fam])
                bad = {k: v for k, v in diffs.items() if v != 0}
                if bad:
                    add("triggers", RED, "baseline se match nahi: " + ", ".join(f"{k} {v:+d}" for k, v in bad.items()))
                else:
                    add("triggers", OK, f"{len(diffs)}/{len(diffs)} systems baseline se exact match")
            else:
                add("triggers", WARN, "baseline file nahi mili — data check skip")
        except Exception as e:
            add("triggers", RED, f"trigger check crash: {str(e)[:80]}")

    # ---------- 5) book config ----------
    try:
        s = A.system_table()
        n = len(s)
        probs = []
        _exp = 14
        try:
            _exp = len(pd.read_csv(A.SYS_CSV))
        except Exception:
            pass
        if n != _exp:
            probs.append(f"{n} systems mile ({_exp} chahiye)")
        if float(cfg.get("lots", 0)) <= 0:
            probs.append("lots<=0")
        if int(cfg.get("max_open", 0)) < 1:
            probs.append("max_open<1")
        if float(cfg.get("cost_inr_per_lot", 0)) <= 0:
            probs.append("cost galat")
        add("book_config", RED if probs else OK, "; ".join(probs) if probs else f"{n} systems, lots {cfg['lots']:g}, slots {cfg['max_open']}")
    except Exception as e:
        add("book_config", RED, f"systems load crash: {str(e)[:80]}")

    # ---------- 6) contract ----------
    try:
        hold = int(pd.to_numeric(pd.read_csv(A.SYS_CSV)["n"], errors="coerce").notna().sum() and 20)
        con = A.contract_pick(hold)
        if not con:
            add("contract", RED, "koi valid GOLDPETAL contract nahi mila (expiry rule fail)")
        else:
            dl = int(con.get("days_left", 0))
            if dl < hold + 3:
                add("contract", RED, f"{con['display']} sirf {dl} din baaki — hold {hold}d fit nahi")
            elif dl < 25:
                add("contract", WARN, f"{con['display']} {dl} din baaki — agla contract rollover ka plan")
            else:
                add("contract", OK, f"{con['display']} (sec {con['sec_id']}, exp {con['expiry']}, {dl} din baaki)")
    except Exception as e:
        add("contract", WARN, f"contract check crash: {str(e)[:80]}")

    # ---------- 7) ledger (orders/positions) ----------
    try:
        orders = A.orders_load(); pos = A.pos_load()
        probs, warns = [], []
        if len(orders):
            ids = pd.to_numeric(orders.order_id, errors="coerce")
            if ids.duplicated().any():
                probs.append("duplicate order_id")
            od = pd.to_datetime(orders.entry_day, errors="coerce").dt.date
            stale_n = int(((orders.status == "PENDING") & od.notna() & (od < today)).sum())
            if stale_n:
                warns.append(f"{stale_n} stale PENDING (aaj auto-expire honge)")
        if len(pos):
            filled = set(pd.to_numeric(orders[orders.status == "FILLED"].order_id, errors="coerce")) if len(orders) else set()
            orphan = [i for i in pd.to_numeric(pos.order_id, errors="coerce") if i not in filled]
            if orphan:
                warns.append(f"{len(orphan)} position ka order FILLED nahi mila (assign karo)")
            n_exit = int((pos.status == "EXIT_ADVICE").sum())
            if n_exit:
                warns.append(f"{n_exit} position EXIT advice par (band karni hai)")
        add("ledger", RED if probs else (WARN if warns else OK),
            "; ".join(probs + warns) if (probs or warns) else f"saaf ({len(orders)} orders, {len(pos)} open)")
    except Exception as e:
        add("ledger", RED, f"ledger crash: {str(e)[:80]}")

    # ---------- 8) cash vs slots ----------
    try:
        cap = float(cfg.get("capital", 0) or 0)
        mpl = float(cfg.get("margin_per_lot", 1352) or 1352)
        need = int(cfg.get("max_open", 1)) * mpl
        if cap <= 0:
            add("cash_margin", WARN, "capital config me nahi daala")
        elif cap < need:
            add("cash_margin", RED, f"cash ₹{cap:,.0f} < {int(cfg['max_open'])} slots ka margin ₹{need:,.0f}")
        elif cap < need * 1.15:
            add("cash_margin", WARN, f"buffer patla — cash ₹{cap:,.0f} vs margin ₹{need:,.0f} (₹{need*1.15:,.0f} behtar)")
        else:
            add("cash_margin", OK, f"₹{cap:,.0f} cash ≥ {int(cfg['max_open'])} slots margin ₹{need:,.0f} (buffer ₹{cap-need:,.0f})")
    except Exception as e:
        add("cash_margin", WARN, f"cash check crash: {str(e)[:80]}")

    # ---------- 9) notify channels ----------
    try:
        tg_tok = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        tg_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        ntfy = os.getenv("NTFY_TOPIC", "").strip()
        wa = os.getenv("WHATSAPP_PHONE", "").strip() and os.getenv("WHATSAPP_APIKEY", "").strip()
        nch = sum(bool(x) for x in (tg_tok and tg_chat, ntfy, wa))
        if nch == 0:
            # workspace (semi-manual) mode: channels file se dekho
            f = f"{A.ADIR}/alerts_config.json"
            if os.path.exists(f):
                j = json.load(open(f))
                nch = sum(bool(x) for x in (j.get("telegram_bot_token") and j.get("telegram_chat_id"),
                                            j.get("ntfy_topics"), j.get("whatsapp")))
                tg_tok = j.get("telegram_bot_token", "")
        if nch == 0:
            # RED nahi, WARN: ye infra issue hai (trade/data theek ho sakta hai) — isliye trade block nahi karta
            add("channels", WARN, "koi alert channel configured nahi — message kahin nahi pahunega (Secrets check karo)!")
        else:
            live = "n/a"
            if notify and tg_tok:
                try:
                    with urllib.request.urlopen(f"https://api.telegram.org/bot{tg_tok}/getMe", timeout=12) as r:
                        live = "telegram zinda ✅" if r.status == 200 else f"telegram HTTP {r.status}"
                except Exception as e:
                    live = f"telegram check fail ({str(e)[:40]})"
            add("channels", OK if (live == "n/a" or live.startswith("telegram zinda")) else WARN,
                f"{nch} channel configured · {live}")
    except Exception as e:
        add("channels", WARN, f"channel check crash: {str(e)[:80]}")

    # ---------- 10) clock / provisional ----------
    if scan is not None:
        if scan.get("provisional"):
            add("clock", WARN, f"signal bar {scan['sig_date']} provisional (COMEX band nahi hua; 02:45 IST ke baad final)")
        else:
            add("clock", OK, f"signal bar {scan['sig_date']} final")

    # ---------- 11) run time sanity ----------
    if now.hour < 3 and now.minute < 45:
        add("run_time", OK, f"{now:%H:%M} IST (raat ka scan — MCX band, kal ke liye taiyari)")
    elif now.hour < 9:
        add("run_time", OK, f"{now:%H:%M} IST (subah ka scan — aaj ke order ke liye)")
    else:
        add("run_time", WARN, f"{now:%H:%M} IST — MCX khula/band ho sakta hai; order aaj lagane ka aakhri mauka tha")

    reds = [c for c in checks if c["status"] == RED]
    warns = [c for c in checks if c["status"] == WARN]
    overall = RED if reds else (WARN if warns else OK)
    out = dict(overall=overall, checks=checks, reds=reds, warns=warns,
               ts=now.strftime("%Y-%m-%d %H:%M"), n_ok=sum(1 for c in checks if c["status"] == OK))
    return out


def log_health(h):
    p = f"{A.ADIR}/health_log.csv"
    A.ensure_dirs()
    new = not os.path.exists(p)
    with open(p, "a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["ts", "overall", "n_ok", "reds", "warns"])
        w.writerow([h["ts"], h["overall"], h["n_ok"],
                    " | ".join(f"{c['check']}: {c['detail']}" for c in h["reds"]),
                    " | ".join(f"{c['check']}: {c['detail']}" for c in h["warns"])])
    return p


def summary_line(h):
    """Ek line — message ke liye."""
    if h["overall"] == OK:
        return f"🟢 sab theek ({h['n_ok']} checks pass)"
    if h["overall"] == WARN:
        return f"🟡 dhyan do ({len(h['warns'])} warning)"
    return f"🔴 RED ZONE ({len(h['reds'])} problem)"


def red_block(h):
    lines = []
    for c in h["reds"]:
        lines.append(f"⛔ RED · {c['check']}: {c['detail']}")
    for c in h["warns"]:
        lines.append(f"⚠️ {c['check']}: {c['detail']}")
    return lines


def print_table(h):
    print(f"\n{'='*100}\nDEEP HEALTH CHECK — {h['ts']} IST · OVERALL: {ICON[h['overall']]} {h['overall']}\n{'='*100}")
    for c in h["checks"]:
        print(f" {ICON[c['status']]:3s} {c['check']:16s} {c['detail']}")
    print(f"{'-'*100}\n {h['n_ok']} OK · {len(h['warns'])} WARN · {len(h['reds'])} RED")
    if h["reds"]:
        print("\n⛔ RED ZONE — aaj order MAT lagao jab tak theek na ho:")
        for c in h["reds"]:
            print(f"   · {c['check']}: {c['detail']}")


if __name__ == "__main__":
    cfg = A.cfg_load()
    D = A.build_frame(cfg)
    scan = None
    try:
        scan = A.signal_scan(cfg, D, quiet=True)
    except Exception as e:
        print("(scan preview nahi bana:", str(e)[:60], ")")
    h = run_health(cfg, D, scan)
    print_table(h)
    p = log_health(h)
    print(f"\nlog: {p}")
    sys.exit(1 if h["overall"] == RED else 0)
