#!/usr/bin/env python3
"""MS GOLD ALGO — daily runner (GitHub Actions / cron / manual).

Flow:  aapki commands  ->  data refresh  ->  signals  ->  positions manage
       ->  DEEP HEALTH CHECK  ->  phone message (action-first, visually clean)
       ->  state files update

  python3 run_daily.py                # asli run (message chala jayega)
  DRY_RUN=1 python3 run_daily.py      # sirf message print, bhejo mat

Message: Telegram ko HTML (bold), ntfy ko Markdown + Title/Tags/Priority, WhatsApp ko plain.
"""
import os, sys, json, traceback, datetime as dt
from argparse import Namespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ms_algo as A                     # noqa: E402
import healthcheck as H                 # noqa: E402
from notify import send                 # noqa: E402
import report_html as BH                 # noqa: E402  (visual HTML message)
import monitor as MON                    # noqa: E402  (MCX-hours live monitor)

IST = A.IST
DAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
LINE = "━━━━━━━━━━━━━━━━━━━━"


def inr(x):
    try:
        return f"₹{float(x):,.0f}"
    except Exception:
        return "₹?"


def process_user_input(cfg):
    """data/algo/user_input.txt ki lines chalata hai (fill / close / skip), phir file reset.

    Phone-friendly: workflow_dispatch ka `cmd` input (env USER_CMD) bhi yahin add ho jata hai —
    jaise "fill 1 13980" / "close 1 14100" / "skip 1" (kai ho to `|` se alag karo).

    Format (har line ek command):
        fill 1 13980      <- order laga, ₹13,980 par mila
        close 1 14100     <- bech diya ₹14,100 par
        skip 1            <- order chhod diya (jaise 1%+ kharab gap)
    """
    p = f"{A.ADIR}/user_input.txt"
    _uc = (os.getenv("USER_CMD", "") or "").strip()
    if _uc:
        try:
            with open(p, "a") as fh:
                fh.write("\n" + "\n".join(l for l in _uc.split("|") if l.strip()) + "\n")
        except Exception:
            pass
    template = ("# yahan likho (ek line me ek command) — ye file roz khaali kar di jaati hai\n"
                "# fill 1 13980      <- order laga, ₹13,980 par mila\n"
                "# close 1 14100     <- bech diya ₹14,100 par\n"
                "# skip 1            <- order chhod diya (jaise 1%+ gap up)\n")
    if not os.path.exists(p):
        open(p, "w").write(template)
        return []
    lines = [l.strip() for l in open(p).read().splitlines() if l.strip() and not l.strip().startswith("#")]
    if not lines:
        open(p, "w").write(template)
        return []
    done = []
    for ln in lines:
        parts = ln.replace(",", " ").split()
        try:
            cmd = parts[0].lower()
            if len(parts) < 2:
                done.append(f"❓ '{ln}' — format: fill 1 13980 / close 1 14100 / skip 1")
                continue
            if cmd == "fill":
                if len(parts) < 3:
                    done.append(f"❓ '{ln}' — format: fill <id> <price>  (jaise fill 1 13980)")
                    continue
                A.cmd_fill(cfg, Namespace(id=parts[1], price=parts[2], lots=None))
                done.append(f"✔ fill #{parts[1]} @ {inr(parts[2])}")
            elif cmd == "close":
                if len(parts) < 3:
                    done.append(f"❓ '{ln}' — format: close <id> <price>  (jaise close 1 14100)")
                    continue
                A.cmd_close(cfg, Namespace(id=parts[1], price=parts[2], why="user"))
                done.append(f"✔ close #{parts[1]} @ {inr(parts[2])}")
            elif cmd == "skip":
                A.cmd_skip(cfg, Namespace(id=parts[1], why="user"))
                done.append(f"✔ skip #{parts[1]}")
            else:
                done.append(f"❓ line samajh nahi aayi: {ln}")
        except Exception as e:
            done.append(f"❌ '{ln}' -> {str(e)[:80]}")
    open(p, "w").write(template)
    return done


def _scoreboard(cfg):
    """1-month test ka scoreboard (agar koi trade band ho chuka hai)."""
    try:
        j = A.jrn_load()
        if not len(j):
            return None
        j = j.copy()
        j["pnl_inr"] = j.pnl_inr.astype(float)
        j["pnl_pct"] = j.pnl_pct.astype(float)
        n = len(j); wins = int((j.pnl_inr > 0).sum())
        return dict(n=n, win=round(100 * wins / n), pnl=float(j.pnl_inr.sum()), best=float(j.pnl_inr.max()),
                    worst=float(j.pnl_inr.min()), avg_pct=round(float(j.pnl_pct.mean()), 2))
    except Exception:
        return None


def build_messages(cfg, scan, mgr, applied, health, err=None, refresh_note=None):
    """(plain, telegram_html, ntfy_md, meta) — teen render, ek hi content se."""
    now = dt.datetime.now(IST)
    L = []                       # (style, text) ; style: h=bold heading, n=normal, c=code/number line

    def h(t): L.append(("h", t))
    def n(t): L.append(("n", t))
    def c(t): L.append(("c", t))
    def gap(): L.append(("n", ""))

    red = bool(health and health["overall"] == "RED")
    new = (scan or {}).get("new") or []
    sig_day = bool(new)
    exit_adv = [m for m in (mgr or []) if m["status"] == "EXIT_ADVICE"]

    # ---------------- subject/priority (ntfy)
    if err or red:
        subj, tags, prio = "🔴 DHYAN DO — algo problem", "rotating_light,warning", 4
    elif sig_day or exit_adv:
        subj, tags, prio = "🎯 AAJ TRADE HAI", "dart,chart_with_upwards_trend", 4
    else:
        subj, tags, prio = "✅ Aaj koi trade nahi", "white_check_mark,sleeping", 3

    if err:
        h(f"🔴 MS GOLD ALGO — PROBLEM ({now:%d %b %H:%M} IST)")
        gap(); n(LINE); gap()
        h("👉 ABHI KYA KARNA HAI")
        n("   ✋ Aaj kuch bhi mat karo — algo chalte waqt error aaya hai.")
        n("   Mujhe message karo (\"health dekho\"), main check karke theek karta hoon.")
        gap(); n("Error: " + str(err).strip().splitlines()[-1][:160])
        plain, html, md = _render(L)
        return plain, html, md, subj, tags, prio

    h(f"🎯 MS GOLD ALGO · {now:%d %b} ({DAY[now.weekday()]}) · {now:%H:%M} IST")
    gap(); n(LINE); gap()

    # ---------------- ACTION FIRST
    h("👉 ABHI KYA KARNA HAI")
    if red:
        n("   ⛔ AAJ KOI TRADE MAT KARO (RED ZONE — pehle problem theek ho).")
        if (scan or {}).get("suppressed"):
            n(f"   🛡️ Safety: aaj ke {len(scan['suppressed'])} signal maine khud SKIP kar diye (#{', #'.join(str(int(float(x))) for x in scan['suppressed'])}).")
        n("   Mujhe message karo: \"health dekho\".")
    elif sig_day:
        n(f"   🟢 AAJ {len(new)} TRADE HAI — MCX open (9:00–9:15 AM) par lagao:")
    else:
        n("   ✅ KUCH NAHI — aaj koi naya trade nahi. Aaj free ho.")
    if exit_adv:
        n(f"   🔴 {len(exit_adv)} POSITION BAND KARNI HAI — neeche POSITIONS dekho.")
        if not sig_day and not red:
            n("      (aaj naya trade nahi, sirf purana band karna hai)")
    gap()

    # ---------------- SIGNAL CARDS
    if sig_day and not red:
        for i, r in enumerate(new, 1):
            h(f"🟢 TRADE #{i} · {r['system']}")
            n(f"   📖 {r.get('rule', '')}")
            sec = str(r.get("contract_sec_id") or "").strip()
            exp = f" (exp {r['contract_expiry']})" if sec and sec != "nan" else ""
            n(f"   🛒 Dhan app me: BUY {r['lots']:g} lot  {r['contract']}{exp}  ·  product NRML")
            c(f"   Entry {inr(r['ref_px'])}  |  TARGET {inr(r['target_px'])} (+{r['tgt_pct']:g}%)  |  SL {inr(r['stop_px'])} (−{r['stop_pct']:g}% SL-M)")
            n(f"   🧾 Super Order me entry + target + SL ek saath daalo (phir bhool jao)")
            lot_g = float(cfg.get("gram_per_lot", 1) or 1)
            win_amt = (r["target_px"] - r["ref_px"]) * float(r["lots"]) * lot_g
            lose_amt = (r["ref_px"] - r["stop_px"]) * float(r["lots"]) * lot_g
            n(f"   💰 Jeet (target): +{inr(win_amt)}   |   Haar (stop): −{inr(lose_amt)}   (1 lot = {lot_g:g} g)")
            if r.get("gap_lo_px") not in (None, "", "nan"):
                n(f"   ⚠️ SKIP karo agar open {inr(r['gap_lo_px'])}–{inr(r['gap_hi_px'])} ke BEECH, ya {inr(r['gap_hard_px'])} se UPAR ho")
            else:
                n(f"   ⚠️ SKIP karo agar open {inr(r['skip_above'])} se UPAR ho")
            n(f"   ⏱ max {r['max_hold']} din hold  ·  📋 ref {inr(r['ref_px'])}/g")
            gap()
    elif scan and scan.get("skipped"):
        whys = {}
        for _, w in scan["skipped"]:
            whys[w.split("(")[0].strip()] = whys.get(w.split("(")[0].strip(), 0) + 1
        n("   ⓘ trigger tha par trade nahi liya: " + ", ".join(f"{k} ×{v}" for k, v in whys.items()))
        gap()

    # ---------------- BOOK SUMMARY (kitna degi)
    bs = {}
    try:
        bs = A.book_summary()
    except Exception:
        bs = {}
    if bs:
        gap(); h("📊 AAPKA BOOK — kitna deta hai (backtest 2003→2026)")
        n(f"   {bs.get('systems', 11)} systems · ~{bs.get('per_mo', 3)} trade/month · win {bs.get('win', 75.5)}% · avg +{bs.get('avg', 1.16)}%/trade")
        n(f"   → {inr(bs.get('inr_mo', 372))}/month (₹{cfg.get('capital', 0):,.0f} capital par) · "
          f"per trade ~{inr(bs.get('inr_per_trade', 123))} · max ghera {bs.get('dd', -6.7)}R")
        n(f"   {bs.get('hit25', 72)}% trades 2.5%+ tak jaate hain · average hold {bs.get('hold', 9)} din")
        cap = float(cfg.get("capital", 0) or 0)
        if bs.get("inr_mo") and cap > 0:
            n(f"   📈 capital par ROI: {100 * float(bs['inr_mo']) / cap:.1f}%/month")
        sb = _scoreboard(cfg)
        if sb:
            n(f"   🧪 TEST SCOREBOARD: {sb['n']} band trades · win {sb['win']}% · total {inr(sb['pnl'])} "
              f"(best {inr(sb['best'])} / worst {inr(sb['worst'])})")
        gap()

    # ---------------- SILVER (signal-only)
    sil = (scan or {}).get("silver") or {}
    if sil.get("new"):
        h("👀 SILVER SIGNAL — sirf dekhne ke liye (trade nahi)")
        for r in sil["new"]:
            n(f"   {r['system']} — {r['name']}")
            n(f"   ref ₹{r['ref_px']:,.0f}/kg · target ₹{r['target_px']:,.0f} (+{r['tgt_pct']:g}%) · "
              f"stop ₹{r['stop_px']:,.0f} (−{r['stop_pct']:g}%) · max {r['max_hold']} din")
            n(f"   ⓘ {cfg.get('silver_contract','SILVERMIC')} 1 kg: margin ~₹{float(cfg.get('silver_margin_per_lot',19082) or 0):,.0f}, "
              f"risk ~₹{r['risk_inr']:,.0f} — aapke paas {inr(cfg.get('capital', 0))} hai, isliye trade NAHI.")
        gap()
    elif sil.get("inactive"):
        n(f"   ⓘ silver ki {len(sil['inactive'])} family data ke bina band hai: {', '.join(sil['inactive'])}")
        gap()

    if (scan or {}).get("expired"):
        n(f"   ⌛ purana pending #{', #'.join(str(int(float(o))) for o, _, _ in scan['expired'])} expire (slot free)")
        gap()
    if applied:
        n("📝 aapki commands:"); [n("   " + a) for a in applied]; gap()
    if refresh_note:
        n(f"   ⚠️ data refresh: {refresh_note}")
        gap()

    # ---------------- POSITIONS
    if mgr:
        n(LINE); gap()
        h("📌 POSITIONS (aapke khule trade)")
        for m in mgr:
            act = "🔴 BAND KARO" if m["status"] == "EXIT_ADVICE" else "🟢 HOLD karo"
            un = m.get("unreal")
            uns = f"{un:+.2f}%" if isinstance(un, (int, float)) else "?"
            try:
                pinr = (float(m["last"]) - float(m["entry"])) * float(cfg.get("gram_per_lot", 1) or 1) * float(cfg.get("lots", 1) or 1)
                ps = f" ({pinr:+,.0f})"
            except Exception:
                ps = ""
            n(f"   #{m['order_id']} {m['system']} · {inr(m['entry'])} → {inr(m['last'])} = {uns}{ps} · {m['days']} din · {act}")
            n(f"      ➜ {m['note']}")
        gap()

    # ---------------- HEALTH
    n(LINE); gap()
    h("🩺 SEHAT (deep check)")
    if health:
        try:
            nsys = len(A.system_table())
        except Exception:
            nsys = 11
        n(f"   {H.summary_line(health)} · {nsys} systems · signal bar {scan['sig_date'] if scan else '?'}")
        for c_ in health["reds"]:
            n(f"   ⛔ RED · {c_['check']}: {c_['detail']}")
        for c_ in health["warns"]:
            n(f"   ⚠️ {c_['check']}: {c_['detail']}")
    else:
        n("   ⚪ health check nahi chala")
    gap()
    pend = A.pending_orders()
    if len(pend):
        n("⏳ PENDING: " + ", ".join(f"#{int(float(x))}" for x in pend.order_id)
          + " — fill hone par likho: fill <id> <price>")

    # ---------------- FOOTER
    gap(); n(LINE); gap()
    n("👉 Order lagne par → Run workflow → cmd box: fill 1 13980   (1 = order ka number)")
    n("👉 Bechte waqt     → cmd box: close 1 14100")
    n("👉 Order nahi lagaya → cmd box: skip 1")
    if cfg.get("quick_book", True):
        n(f"👉 QUICK-BOOK: din-{cfg.get('quick_book_day',10):g} tak +{cfg.get('quick_book_pct',2.5):g}% ho jaye to book kar do (V5 rule)")
    n(f"👉 Agla message: kal subah ~8:30 · kharcha {inr(cfg['cost_inr_per_lot'])}/trade · margin {inr(cfg.get('margin_per_lot', 1352))}/lot")

    plain, html, md = _render(L)
    return plain, html, md, subj, tags, prio


def _render(L):
    plain = "\n".join(t for _, t in L)
    html = "\n".join(f"<b>{_esc(t)}</b>" if st == "h" else (f"<code>{_esc(t)}</code>" if st == "c" else _esc(t))
                     for st, t in L)
    md = "\n".join(f"**{t}**" if st == "h" else (f"`{t}`" if st == "c" else t) for st, t in L)
    return plain, html, md


def _esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


MODE = (os.getenv("MS_MODE", "daily") or "daily").strip().lower()
SENT_FILE = f"{A.MS}/data/algo/last_sent.json"

# GitHub cron kab fire hona chahiye tha (UTC cron -> IST) — delay dikhane ke liye
SCHED_IST = {"30 21 * * 0-4": "03:00", "0 0 * * 1-5": "05:30",
             "0 3 * * 1-5": "08:30", "0 19 * * 1-5": "00:30"}


def sched_delay_note(now=None):
    """SCHED_CRON env se: scheduled IST time vs actual — GitHub cron late chalta hai, wo saaf dikhao."""
    cron = (os.getenv("SCHED_CRON", "") or "").strip()
    if not cron or cron not in SCHED_IST:
        return None
    exp = SCHED_IST[cron]
    now = now or dt.datetime.now(IST)
    hh, mm = (int(x) for x in exp.split(":"))
    exp_t = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    diff = int((now - exp_t).total_seconds() // 60)
    if abs(diff) <= 5:
        return f"scheduled {exp} IST par hi chala ✅"
    if diff < 0:                        # normal me nahi hota (schedule se pehle) — manual run maano
        return f"scheduled {exp} IST · actual {now:%H:%M} IST (schedule se pehle — manual/early run)"
    return f"scheduled {exp} IST tha · actual {now:%H:%M} IST (delay +{diff} min)"


def fingerprint(scan, mgr, applied, err, health):
    """Message ka 'content hash' — same haalat dobara aayi to dobara bhejna hi nahi."""
    import hashlib, json as _json
    sil = (scan or {}).get("silver") or {}
    fp = {
        "sig_date": str((scan or {}).get("sig_date") or ""),
        "new": sorted(str(x.get("order_id")) for x in ((scan or {}).get("new") or [])),
        "suppressed": sorted(str(x) for x in ((scan or {}).get("suppressed") or [])),
        "exit": sorted(f"{m.get('order_id')}:{m.get('days')}" for m in (mgr or [])
                       if m.get("status") == "EXIT_ADVICE"),
        "silver": sorted(str(x.get("system")) for x in (sil.get("new") or [])),
        "applied": [str(a) for a in (applied or [])],
        "err": bool(err),
        "health": (health or {}).get("overall"),
    }
    return hashlib.sha1(_json.dumps(fp, sort_keys=True).encode()).hexdigest()[:16], fp


def sent_state():
    try:
        return json.load(open(SENT_FILE))
    except Exception:
        return {}


def mark_sent(fp, extra=None):
    try:
        os.makedirs(os.path.dirname(SENT_FILE), exist_ok=True)
        json.dump({"fp": fp, "at": f"{dt.datetime.now(IST):%Y-%m-%d %H:%M} IST",
                   "extra": extra or {}}, open(SENT_FILE, "w"), indent=1)
    except Exception as e:
        print("  ! last_sent.json likh nahi paya:", str(e)[:80])


def main():
    cfg = A.cfg_load()
    A.ensure_dirs()
    os.makedirs(f"{A.MS}/outputs", exist_ok=True)
    applied, scan, mgr, health, err, refresh_note = [], None, [], None, None, None
    try:
        applied = process_user_input(cfg)
        print("1) data refresh (yfinance)...")
        try:
            A.refresh_market()
        except Exception as e:
            refresh_note = f"fresh data nahi aaya ({str(e)[:60]}) — purane data par chal raha hoon"
            print("   !", refresh_note)
        D = A.build_frame(cfg)
        print("2) signals + positions...")
        scan = A.signal_scan(cfg, D)
        mgr = A.manage(cfg, D)
        print("3) DEEP HEALTH CHECK (report se pehle)...")
        health = H.run_health(cfg, D, scan)
        H.print_table(health)
        H.log_health(health)
        A.console_sheet(cfg, scan, mgr, D)
        A.html_sheet(cfg, scan, mgr, D, f"{A.MS}/outputs/algo_sheet.html")
        with open(f"{A.MS}/outputs/daily_log.txt", "a") as fh:
            fh.write(f"\n===== {dt.datetime.now(IST):%Y-%m-%d %H:%M} IST =====\n"
                     f"health={health['overall']} state={scan['state']} rsi={scan['r14']:.1f} "
                     f"sig_bar={scan['sig_date']} new={len(scan['new'])} open={len(mgr)} applied={applied}\n")
    except Exception:
        err = traceback.format_exc()[-900:]
    if (health and health["overall"] == "RED" and scan and scan.get("new")):
        reason = "; ".join(f"{c['check']}" for c in health["reds"]) or "health RED"
        ids = A.suppress_new(cfg, scan["new"], reason)
        scan["new"] = []
        scan["suppressed"] = ids
        print(f"⛔ RED ZONE -> aaj ke {len(ids)} order khud SKIP kar diye (safety): {ids}")
    delay_note = sched_delay_note()
    if delay_note:
        print("⏱", delay_note)
    plain, html, md, subj, tags, prio = build_messages(cfg, scan, mgr, applied, health, err, refresh_note)

    # ---- DUPLICATE GUARD: same haalat me dobara message mat bhejo (03:00 + 05:30 + 08:30 sab chalte hain) ----
    fp, fpmeta = fingerprint(scan, mgr, applied, err, health)
    force = (os.getenv("FORCE_SEND", "") or "").strip().lower() not in ("", "0", "false", "no")
    last = sent_state()
    fp_same = (not force) and last.get("fp") == fp

    # ---- LIVE MONITOR (hourly runs): sirf zaroorat par alert ----
    alerts = []
    if MODE == "monitor":
        try:
            alerts = MON.collect(A, cfg, D if "D" in dir() else None, scan, mgr, health, err,
                                 dt.datetime.now(IST))
        except Exception as e:
            print("  ! monitor collect fail:", str(e)[:120])
            alerts = []
        print(f"  monitor: {len(alerts)} naya alert" + ("" if alerts else " (kuch bhejne layak nahi)"))

    # ---- MONITOR MODE: sirf alert bhejta hai, warning-free chup rehta hai ----
    if MODE == "monitor" and not alerts and not force:
        print("🔇 monitor: koi alert-worthy cheez nahi — chup (koi message nahi bheja)")
        if err:
            print(err)
            sys.exit(1)
        return

    if fp_same and not alerts and MODE != "monitor":
        print(f"⏭️ yahi message pehle bhej diya tha ({last.get('at','?')}) — duplicate skip")
        if err:
            print(err)
            sys.exit(1)
        return
    if force:
        print("⚡ FORCE_SEND — duplicate guard skip kiya")

    # ---- message HTML file me jaata hai (text ki jagah) ----
    try:
        if MODE == "monitor":
            # monitor mode: sirf alert HTML bhejta hai — last_sent.json ko chhedta nahi
            if alerts:
                path, caption = BH.build_alert_html(cfg, alerts, scan, mgr)
                res = BH.send_report(path, caption, title=alerts[0].get("title", "MS Gold Algo alert")[:120],
                                     tags=str(alerts[0].get("tag", "rotating_light")),
                                     priority=int(alerts[0].get("prio", 3)))
                print(f"🚨 ALERT HTML: {path}")
                if "✅" in str(res):
                    st_m = MON.load_state()
                    st_m["sent"] = sorted(set((st_m.get("sent") or []) + [a["key"] for a in alerts]))
                    st_m.setdefault("date", dt.datetime.now(IST).strftime("%Y-%m-%d"))
                    MON.save_state(st_m)
            else:
                # force=true par bhi monitor me poora daily message bhejna hai to yahan aata hai
                path, caption = BH.build_daily_html(cfg, scan, mgr, applied, health, err, refresh_note,
                                                    delay_note=delay_note, alerts=alerts)
                BH.send_report(path, caption, title=subj,
                               tags=",".join(tags) if isinstance(tags, (list, tuple)) else str(tags),
                               priority=prio)
                print(f"📄 force monitor run — daily message bheja: {path}")
        elif alerts and fp_same:
            # sirf alert bhejna hai (full daily message pehle hi ja chuka hai)
            path, caption = BH.build_alert_html(cfg, alerts, scan, mgr)
            res = BH.send_report(path, caption, title=alerts[0].get("title", "MS Gold Algo alert")[:120],
                                 tags=str(alerts[0].get("tag", "rotating_light")),
                                 priority=int(alerts[0].get("prio", 3)))
            print(f"🚨 ALERT HTML: {path}")
            if "✅" in str(res):
                MON.save_state({**MON.load_state(), "sent": sorted(set((MON.load_state().get("sent") or [])
                                                                      + [a["key"] for a in alerts]))})
        else:
            path, caption = BH.build_daily_html(cfg, scan, mgr, applied, health, err, refresh_note,
                                                delay_note=delay_note, alerts=alerts)
            res = BH.send_report(path, caption,
                                 title=subj, tags=",".join(tags) if isinstance(tags, (list, tuple)) else str(tags),
                                 priority=prio)
            print(f"📄 HTML message: {path}")
            if "✅" in str(res):
                mark_sent(fp, {"sig_date": fpmeta["sig_date"], "new": len(fpmeta["new"]),
                               "exit": len(fpmeta["exit"]), "applied": len(fpmeta["applied"]),
                               "delay": delay_note or ""})
                if alerts:
                    MON.save_state({**MON.load_state(),
                                    "sent": sorted(set((MON.load_state().get("sent") or [])
                                                       + [a["key"] for a in alerts]))})
            elif not os.getenv("DRY_RUN"):
                print("  ! kisi bhi channel par nahi pahuncha — fingerprint save nahi kiya (agle run par phir koshish hoga)")
    except Exception as e:
        import traceback as _tb
        print("! HTML report fail — purane text par fallback:", str(e)[:120])
        print(_tb.format_exc()[-500:])
        send(plain, html=html, md=md, title=subj, tags=tags, priority=prio)
    if err:
        print(err)
        sys.exit(1)


if __name__ == "__main__":
    main()
