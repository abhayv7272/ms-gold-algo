#!/usr/bin/env python3
"""monitor.py — MCX hours me HAR GHANTE chalne wala live monitor.

Sirf zaroorat par message (spam nahi). Har alert din me ek baar:

  1) ⏰ ENTRY ZONE HIT  — pending order ka ref price live me mil gaya → "abhi order lagao"
  2) 🚫 HARD SKIP       — live price gap-hard se upar nikal gaya → "mat lagao"
  3) 🎯 TARGET HIT      — khuli position ka target live price se touch → "book karo"
  4) 🛑 STOP HIT        — stop lag gaya → "SL laga, gaya"
  5) 💚 QUICK-BOOK      — din-10+ par +2.5% ho gaya → "book kar sakte ho"
  6) ⏳ SETUP BAN RAHA  — aaj ke ban rahe bar me systems trigger ho rahe hain
                          (info only — final signal raat ~2:45 AM IST ke baad)

Dedup: data/algo/monitor_state.json  (ek din me ek baar per alert)
"""
import datetime as dt
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "data", "algo", "monitor_state.json")


# ---------------------------------------------------------------- helpers
def market_hours_ok(now):
    """MCX: Mon-Fri 9:00 AM - 11:30 PM IST."""
    if os.getenv("MS_IGNORE_MKT_HOURS") == "1":     # sirf test ke liye
        return True
    if now.weekday() >= 5:
        return False
    mins = now.hour * 60 + now.minute
    return (9 * 60) <= mins <= (23 * 60 + 30)


def load_state():
    try:
        d = json.load(open(STATE))
        if isinstance(d, dict):
            return d
    except Exception:
        pass
    return {}


def save_state(state):
    try:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        json.dump(state, open(STATE, "w"), indent=1)
    except Exception as e:
        print("  ! monitor_state.json likh nahi paya:", str(e)[:80])


def _today_key(now):
    return now.strftime("%Y-%m-%d")


def live_price_inr(D):
    """yfinance se GC=F ka 5-min live price → INR/g (wahi formula jo frame me hai).

    Return: (px_inr, ts_ist, note). Nahi mila to (None, None, reason).
    """
    try:
        import yfinance as yf
        t = yf.download("GC=F", period="1d", interval="5m", progress=False, auto_adjust=False)
        if t is None or len(t) == 0:
            return None, None, "intraday data nahi mila"
        close = t["Close"]
        if hasattr(close, "columns"):            # MultiIndex (naya yfinance)
            close = close.iloc[:, 0]
        val = close.dropna()
        if not len(val):
            return None, None, "intraday close khaali"
        usd = float(val.iloc[-1])
        ts = val.index[-1]
        try:
            ts_ist = ts.tz_convert("Asia/Kolkata").to_pydatetime()
        except Exception:
            ts_ist = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30)))
        usdinr = float(D.usdinr.iloc[-1])
        duty = float(D.gold_duty_pct.iloc[-1])
        tax = float(D.indirect_tax_pct.iloc[-1])
        px = usdinr * (1 + duty / 100) * (1 + tax / 100) / 31.1035 * usd
        return round(px, 1), ts_ist, f"live ${usd:,.1f}/oz"
    except Exception as e:
        return None, None, str(e)[:80]


def _days_held(pos_row, now):
    try:
        ed = dt.datetime.strptime(str(pos_row["entry_date"])[:10], "%Y-%m-%d").date()
        return max(0, (now.date() - ed).days)
    except Exception:
        return int(float(pos_row.get("days_held") or 0))


def provisional_setups(A, cfg, D):
    """Aaj ke ban rahe (incomplete) bar par kaunse systems trigger ho rahe hain."""
    try:
        F = A.fam_masks(D)
        st = A.system_table()
        out = []
        for fam in st.fam:
            m = F.get(fam)
            if m is None:
                continue
            try:
                if bool(m.iloc[-1]):
                    out.append((fam, str(st.loc[st.fam == fam, "name"].iloc[0])))
            except Exception:
                continue
        return out
    except Exception as e:
        print("  ! provisional scan fail:", str(e)[:80])
        return []


# ---------------------------------------------------------------- main collect
def collect(A, cfg, D, scan, mgr, health, err, now, fresh_minutes=120):
    """Aaj ke naye alerts (jo abhi tak nahi bheje) return karo."""
    alerts = []
    if err:
        return alerts
    if health and health.get("overall") == "RED":
        print("  ⛔ RED ZONE — koi live alert nahi (safety)")
        return alerts

    state = load_state()
    today = _today_key(now)
    if state.get("date") != today:
        state = {"date": today, "sent": []}
    sent_prev = set(state.get("sent") or [])   # jo PEHLE HI pahunch chuke (delivered)
    sent = set(sent_prev)

    # ---------------- live price
    px, ts, note = live_price_inr(D)
    in_hours = market_hours_ok(now)
    if px is not None and ts is not None:
        age = (now - ts).total_seconds() / 60 if ts.tzinfo else 0
        fresh = age <= fresh_minutes
    else:
        age, fresh = None, False
    print(f"  monitor: live px = {px} ({note}) · ts {ts} · fresh {fresh} · market hours {in_hours}")

    def add(key, kind, title, lines, prio=3, tag="information_source", payload=None):
        if key in sent:
            return
        alerts.append(dict(key=key, kind=kind, title=title, lines=lines, prio=prio, tag=tag,
                            payload=payload or {}))
        sent.add(key)

    # ---------------- 1/2) pending orders: entry zone / hard skip
    try:
        pend = A.pending_orders()
    except Exception:
        pend = []
    order_rows = []
    for _, o in pend.iterrows():
        key_ = f"entry:{int(float(o.order_id))}"
        key_s = f"skip:{int(float(o.order_id))}"
        if key_ in sent and key_s in sent:
            continue
        entry_day = str(o.get("entry_day", ""))[:10]
        if entry_day and entry_day != today:
            continue                                   # kal ka order (aaj ka nahi)
        ref = float(o["ref_px"])
        hard = float(o.get("gap_hard_px") or ref * 1.025)
        row = {
            "order_id": int(float(o.order_id)), "system": str(o.system), "family": str(o.get("family", "")),
            "side": "BUY", "rule": str(o.get("rule", "")), "lots": int(float(o.get("lots", 1) or 1)),
            "contract": str(o.get("contract", "")), "contract_sec_id": str(o.get("contract_sec_id", "")),
            "contract_expiry": str(o.get("contract_expiry", "")), "ref_px": ref,
            "target_px": float(o["target_px"]), "stop_px": float(o["stop_px"]),
            "tgt_pct": float(o.get("tgt_pct", 0) or 0), "stop_pct": float(o.get("stop_pct", 0) or 0),
            "max_hold": float(o.get("max_hold", 20) or 20),
            "skip_above": float(o.get("skip_above", 0) or 0),
            "gap_lo_px": o.get("gap_lo_px", ""), "gap_hi_px": o.get("gap_hi_px", ""),
            "gap_hard_px": o.get("gap_hard_px", ""),
        }
        if px is None or not in_hours or not fresh:
            continue                                   # price bharosa layak nahi → koi alert nahi
        if px <= ref * 1.002 and key_ not in sent:
            pct = (px / ref - 1) * 100
            add(key_, "entry", f"⏰ ENTRY ZONE — ABHI ORDER LAGAO (#{row['order_id']} {row['system']})",
                [f"Live price ₹{px:,.0f}/g aa gaya (ref ₹{ref:,.0f} se {pct:+.2f}%)",
                 f"{note} · {ts:%H:%M} IST",
                 f"BUY {row['lots']:g} lot {row['contract']} · target ₹{row['target_px']:,.0f} (+{row['tgt_pct']:g}%) · SL ₹{row['stop_px']:,.0f} (−{row['stop_pct']:g}%)",
                 f"Dhan app → Super Order (entry+target+SL ek saath) → phir likho: fill {row['order_id']} <aapka fill>"],
                prio=4, tag="rotating_light", payload={"order": row, "px": px})
        elif px >= hard and key_s not in sent:
            pct = (px / ref - 1) * 100
            add(key_s, "skip", f"🚫 MAT LAGAO — price bahut upar (#{row['order_id']} {row['system']})",
                [f"Live price ₹{px:,.0f}/g — ref ₹{ref:,.0f} se {pct:+.2f}% upar (skip limit +{cfg.get('gap_hard',2.5):g}%)",
                 f"Ise chhod do — likho: skip {row['order_id']}",
                 "Peeche bhagne se entry kharab hoti hai (backtest me ye band tha)"],
                prio=4, tag="no_entry", payload={"order": row, "px": px})

    # ---------------- 3/4/5) open positions: target / stop / quick-book
    try:
        pos = A.pos_load()
    except Exception:
        pos = []
    for _, p in (pos.iterrows() if len(pos) else []):
        if str(p.get("status", "")).upper() not in ("OPEN", "EXIT_ADVICE"):
            continue
        try:
            oid = int(float(p["order_id"])); epx = float(p["entry_px"])
            tgt = float(p["target_px"]); stp = float(p["stop_px"]); lots = float(p.get("lots", 1) or 1)
        except Exception:
            continue
        if px is None or not in_hours or not fresh:
            continue
        days = _days_held(p, now)
        lot_g = float(cfg.get("gram_per_lot", 1) or 1)
        base = {"order_id": oid, "system": str(p.get("system", "")), "entry": epx,
                "days": days, "px": px}
        if px >= tgt:
            gain = (tgt - epx) * lots * lot_g - float(cfg.get("cost_inr_per_lot", 46) or 46)
            add(f"target:{oid}", "target", f"🎯 TARGET HIT — BOOK KARO (#{oid} {base['system']})",
                [f"Live price ₹{px:,.0f} chala gaya — target ₹{tgt:,.0f} chhua (+{(tgt/epx-1)*100:.2f}%)",
                 f"Sehda faayda: +₹{gain:,.0f} (charges ke baad) · {days} din me",
                 f"Bech do aur likho: close {oid} <aapka fill>",
                 "Target aaya to book karna hi rule hai — lalach nahi"],
                prio=4, tag="tada", payload=base)
        elif px <= stp:
            loss = (epx - stp) * lots * lot_g + float(cfg.get("cost_inr_per_lot", 46) or 46)
            add(f"stop:{oid}", "stop", f"🛑 STOP LAGA — position gaya (#{oid} {base['system']})",
                [f"Live price ₹{px:,.0f} — stop ₹{stp:,.0f} ke neeche",
                 f"Nuksan: −₹{loss:,.0f} (plan me tha — control me hai)",
                 f"Exit karo aur likho: close {oid} <aapka fill>",
                 "Stop hit hona normal hai — 100 me se ~5 trade. Next signal ka wait karo"],
                prio=4, tag="octagonal_sign", payload=base)
        else:
            qb_day = int(cfg.get("quick_book_day", 10) or 10)
            qb_pct = float(cfg.get("quick_book_pct", 2.5) or 2.5)
            if cfg.get("quick_book", True) and days >= qb_day and (px / epx - 1) * 100 >= qb_pct:
                add(f"qb:{oid}", "quickbook", f"💚 QUICK-BOOK — abhi book kar sakte ho (#{oid} {base['system']})",
                    [f"{days} din ho gaye aur abhi +{(px/epx-1)*100:.2f}% hai (rule: din-{qb_day} par +{qb_pct:g}%)",
                     f"Book value: +₹{(px-epx)*lots*lot_g:,.0f} (approx) · target ₹{tgt:,.0f} abhi baaki hai",
                     f"Book karo aur likho: close {oid} <aapka fill>"],
                    prio=4, tag="moneybag", payload=base)

    # ---------------- 6) provisional setups (aaj ka ban raha bar)
    prov_key = "prov"
    if prov_key not in sent and in_hours and (scan is not None):
        try:
            prov = provisional_setups(A, cfg, D)
        except Exception:
            prov = []
        if prov:
            names = ", ".join(f"{nm} ({fam})" for fam, nm in prov[:6])
            add(prov_key, "prov", f"⏳ SETUP BAN RAHA HAI — {len(prov)} system trigger me",
                [f"Aaj ke bar (abhi ban raha hai) me ye systems trigger ho rahe hain: {names}",
                 "⚠️ Ye ADHOORA hai — bar aaj raat ~2:30 AM IST par band hoga, tab final signal banega",
                 "Abhi ORDER MAT lagao. Final signal raat ke run me aayega (entry kal MCX open par).",
                 "Fayda: margin ready rakho + aaj raat ka message zaroor dekho"],
                prio=3, tag="hourglass", payload={"fams": [f for f, _ in prov]})

    # NOTE: sirf delivered keys save hote hain — bhejna fail ho to agla run dobara koshish karega
    state["sent"] = sorted(sent_prev)
    state["last_px"] = px
    state["last_check"] = now.strftime("%Y-%m-%d %H:%M")
    save_state(state)
    return alerts
