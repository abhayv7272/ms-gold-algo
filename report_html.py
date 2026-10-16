#!/usr/bin/env python3
"""report_html.py — Daily message ka VISUALLY STUNNING HTML version.

Ab text message ki jagah ek HTML file jaati hai (Telegram document + ntfy attachment).
Content bilkul same: ABHI KYA KARNA HAI (banner) -> TRADE cards -> BOOK -> SILVER
-> POSITIONS -> SEHAT -> commands.

Telegram : HTML file + chhota caption (notification me dikhne ke liye)
ntfy     : waahi caption text + HTML file attach

Sirf standard library (repo me naya dependency nahi).
"""
import os, json, uuid, urllib.request, urllib.parse, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------------ helpers

# ---------------------------------------------------------------- setup bhasha
# Har system ka "setup" simple bhasha me — trade card isi se banta hai.
SETUP = {
 "r5_deep": dict(
   name="Washout Bounce",
   setup="Gold 5 din me ~6% gir chuka hai — log dar ke bech rahe hain",
   why="Itni tez giri ke baad aksar bounce aata hai: 38 me se 34 baar jeeta (89%). Sabse bharosemand system.",
   do="1 lot buy + target 3% / stop 8% / max 4 din — bas itna."),
 "pb20": dict(
   name="Deep Dip",
   setup="Gold girke RSI 35 se neeche + 21-din minus + price band ke bilkul neeche",
   why="Gehra dip jab sab indicator thake hue hon — wapas upar aane ka mauka (63 me se 49 jeete).",
   do="1 lot buy + target 3.5% / stop 6% / max 10 din."),
 "lag_gs80pct": dict(
   name="Ratio Stretch",
   setup="Gold/Silver ratio 80th percentile se upar + gold 5 din se neeche",
   why="Gold silver ke mukable mehnga ho gaya — ratio wapas normal hota hai to gold bhaagta hai (77.5%).",
   do="1 lot buy + target 4% / stop 10% / max 16 din."),
 "dxy_dn": dict(
   name="Dollar Kamzor",
   setup="Dollar index (DXY) ek din me −0.6% + gold 3 din se neeche",
   why="Dollar kamzor = gold mehnga. Dono ek saath mile to gold ka bounce strong hota hai (75.3%).",
   do="1 lot buy + target 3% / stop 12% / max 8 din."),
 "gaprsi": dict(
   name="Sasta Gap-Down",
   setup="Gold gap-down me khula + RSI 45 se kam (subah thaka hua)",
   why="Panic open par gold sasta milta hai; RSI thaka hone se bounce jaldi aata hai (75%, 60 trades).",
   do="1 lot buy + target 2.5% / stop 6% / max 8 din."),
 "gvz_spike": dict(
   name="Darr Ka Spike",
   setup="GVZ (gold ka darr index) 70th percentile se upar + gold 1 din me −1%",
   why="Market me darr chaar taraf hai — aisi panic me gold aksar wapas upar aata hai (74.4%, 90 trades).",
   do="1 lot buy + target 3% / stop 12% / max 11 din."),
 "mm_capit": dict(
   name="Sabse Bada Washout",
   setup="Bade players (MM positioning) 10th percentile se neeche — sabne gold chhod diya",
   why="Jab sab bahar ho jaate hain (capitulation) — wahi sabse acha entry hota hai (73.8%).",
   do="1 lot buy + target 4% / stop 10% / max 14 din."),
 "trend_pull_rsi": dict(
   name="Up-Trend Pullback",
   setup="Gold UP trend me hai + RSI 50 ke neeche thoda dip aaya",
   why="Upar wale trend me chhota dip sasta milta hai; trend wapas chal padta hai (73.6%).",
   do="1 lot buy + target 2.5% / stop 8% / max 8 din."),
 "dip_above_mean": dict(
   name="Strong Me Dip",
   setup="1 din me −1.5% gira par price abhi bhi MA20 ke UPAR hai",
   why="Strong gold me ek din ka girawat jaldi bharpai ho jaati hai (73.5%, 117 trades).",
   do="1 lot buy + target 3% / stop 10% / max 8 din."),
 "r21pb": dict(
   name="21-Din Giri",
   setup="21 din me 6%+ giri + band ke bilkul neeche (pctB < 0.15)",
   why="Lambi giri ke baad mean-reversion — 73 me se 27+ jeete, average +1.38% per trade.",
   do="1 lot buy + target 3% / stop 12% / max 13 din."),
 "gapdown_up": dict(
   name="Gap Down = Sasta",
   setup="UP trend me gold gap-down khula (subah sasta mila)",
   why="Trend upar ka hai par gap se sasta mila — gap bharne ka mauka (72.6%).",
   do="1 lot buy + target 3% / stop 10% / max 12 din."),
}


def _fam_of(r):
    """System code se family nikaalo: G-r5_deep -> r5_deep."""
    fam = str(r.get("family") or "").strip()
    if fam:
        return fam.replace("G-", "").replace("S-", "")
    return str(r.get("system", "")).replace("G-", "").replace("S-", "").strip()


def _stats_strip(meta):
    """Is strategy ka 22-saal ka record — chhoti chips me."""
    if not meta:
        return ""
    ok = lambda k: meta.get(k) not in (None, "", "nan")
    ch = []
    if ok("win"):
        ch.append(f'<span class="chip good">win <b>{float(meta["win"]):.0f}%</b></span>')
    if ok("avg"):
        ch.append(f'<span class="chip">avg <b>+{float(meta["avg"]):.2f}%</b></span>')
    if ok("n"):
        ch.append(f'<span class="chip">{int(float(meta["n"]))} trades (2004 se)</span>')
    if ok("hold_med"):
        ch.append(f'<span class="chip">hold <b>{float(meta["hold_med"]):.0f} din</b></span>')
    if ok("per_mo"):
        ch.append(f'<span class="chip">{float(meta["per_mo"]):.2f}/mahina</span>')
    if ok("tgt_hit"):
        ch.append(f'<span class="chip">{float(meta["tgt_hit"]):.0f}% baar 2.5%+ chhua</span>')
    return f'<div class="chips" style="margin-top:10px">{"".join(ch)}</div>'

def _inr(x):
    try:
        return f"₹{float(x):,.0f}"
    except Exception:
        return "₹?"


def _esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ring(pct, color="#f2c14e", size=58, label=None):
    import math
    r, sw = 24, 6
    c = 2 * math.pi * r
    dash = c * max(0.0, min(float(pct), 100.0)) / 100
    return (f'<svg viewBox="0 0 58 58" width="{size}" height="{size}" style="flex:0 0 {size}px">'
            f'<circle cx="29" cy="29" r="{r}" fill="none" stroke="#1c2534" stroke-width="{sw}"/>'
            f'<circle cx="29" cy="29" r="{r}" fill="none" stroke="{color}" stroke-width="{sw}" '
            f'stroke-linecap="round" stroke-dasharray="{dash:.1f} {c:.1f}" transform="rotate(-90 29 29)"/>'
            f'<text x="29" y="34" text-anchor="middle" font-size="14.5" font-weight="700" fill="#e8eef7">{label or f"{float(pct):.1f}%"}</text>'
            f'</svg>')


CSS = """
:root{--bg:#070a10;--card:#0e141f;--bd:#1b2433;--bd2:#141c28;--tx:#e8eef7;--mu:#93a3ba;--mu2:#6f8098;
--gold:#f2c14e;--gold2:#ffd479;--grn:#46e08a;--red:#ff6b6b;--blu:#6cc4ff}
*{box-sizing:border-box}html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,
"Noto Sans",Arial,sans-serif;-webkit-font-smoothing:antialiased;line-height:1.55;font-size:15.5px}
.glow{position:fixed;inset:0;pointer-events:none;z-index:0;background:
radial-gradient(900px 420px at 12% -6%,rgba(242,193,78,.15),transparent 62%),
radial-gradient(760px 420px at 96% 4%,rgba(108,196,255,.09),transparent 60%)}
.wrap{position:relative;z-index:1;max-width:900px;margin:0 auto;padding:22px 14px 60px}
h1,h2,h3{margin:0;line-height:1.25}h1{font-size:clamp(22px,4.6vw,30px);letter-spacing:-.4px}
.kicker{font-size:11.5px;letter-spacing:2.2px;text-transform:uppercase;color:var(--mu2);font-weight:800}
.sub{color:var(--mu);font-size:13.5px;margin:6px 0 0}
.chip{display:inline-block;font-size:12px;padding:4px 10px;border-radius:20px;background:#131a26;border:1px solid var(--bd);color:var(--mu)}
.chip b{color:var(--tx)}.chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px}
.chip.good{background:#0f2a1b;border-color:#1d4a2f;color:#7ee2a8}
.chip.red{background:#2a1414;border-color:#4a1f1f;color:#ff9b95}
.chip.tgt{background:#2a2210;border-color:#4a3a13;color:var(--gold2)}
.chip.stp{background:#2a1414;border-color:#4a1f1f;color:#ff9b95}
.chip.b{background:#0f2233;border-color:#1d4257;color:#8ed2ff}
/* banner */
.banner{margin:20px 0 6px;border-radius:16px;padding:18px 18px 16px;border:1px solid var(--bd);
background:linear-gradient(160deg,#121a27,#0b1017)}
.banner .lab{font-size:12px;letter-spacing:2px;font-weight:800;color:var(--mu2)}
.banner .big{font-size:clamp(22px,4.4vw,30px);font-weight:800;letter-spacing:-.5px;margin:4px 0 2px}
.banner .note{color:var(--mu);font-size:14.5px}
.banner.go{border-color:#1d4a2f;background:linear-gradient(160deg,#0f2018,#0b1017)}
.banner.go .big{color:#68e69b}
.banner.stop{border-color:#4a1f1f;background:linear-gradient(160deg,#1c1112,#0b1017)}
.banner.stop .big{color:#ff8f87}
.banner.idle{border-color:#2a3342}
.banner.idle .big{color:#cfe0f5}
/* sections */
section{margin:30px 0 0}
.stitle{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:10px}
.stitle h2{font-size:clamp(18px,3.2vw,22px);letter-spacing:-.3px}
.ssub{color:var(--mu);font-size:13.5px;margin:-4px 0 12px}
/* trade card */
.tcard{background:linear-gradient(180deg,#0f1b16,#0a0f18);border:1px solid #1d4a2f;border-radius:16px;
padding:16px;position:relative;overflow:hidden}
.tcard::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:linear-gradient(180deg,#7ee2a8,#1f7a4a)}
.tcard .tno{font-size:12px;letter-spacing:1.6px;color:#7ee2a8;font-weight:800}
.tcard h3{font-size:19px;margin:2px 0 2px}
.tcard .rule{color:var(--mu);font-size:13.5px}
.trow{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:14px 0 6px}
.tbox{background:#0b1119;border:1px solid var(--bd2);border-radius:12px;padding:10px 11px}
.tbox .k{font-size:11px;color:var(--mu2);text-transform:uppercase;letter-spacing:.7px}
.tbox .v{font-size:17.5px;font-weight:800;font-variant-numeric:tabular-nums}
.tbox.e .v{color:#cfe0f5}.tbox.t .v{color:var(--gold2)}.tbox.s .v{color:#ff9b95}
.money{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0 4px}
.mchip{font-size:13.5px;padding:6px 11px;border-radius:10px;background:#0b1119;border:1px solid var(--bd2)}
.mchip.win{color:#7ee2a8;border-color:#1d4a2f}.mchip.lose{color:#ff9b95;border-color:#4a1f1f}
.steps{margin:12px 0 2px;padding:0;list-style:none}
.steps li{display:flex;gap:9px;font-size:14px;padding:4px 0;color:var(--mu)}
.steps b{color:var(--tx)}
.steps .n{width:20px;height:20px;flex:0 0 20px;border-radius:6px;background:#182130;display:flex;align-items:center;
justify-content:center;font-size:11.5px;font-weight:800;color:var(--gold2)}
/* kpis */
.kpis{display:grid;grid-template-columns:repeat(2,1fr);gap:11px;margin:14px 0 0}
@media(min-width:720px){.kpis{grid-template-columns:repeat(4,1fr)}}
.kpi{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:12px 13px}
.kpi .n{font-size:22px;font-weight:800;letter-spacing:-.5px}
.kpi .l{font-size:12px;color:var(--mu);margin-top:1px}
.kpi.g .n{color:var(--grn)}.kpi.y .n{color:var(--gold2)}.kpi.b .n{color:var(--blu)}.kpi.r .n{color:var(--red)}
/* card w/ ring */
.box{background:linear-gradient(180deg,#0f1622,#0a0f18);border:1px solid var(--bd);border-radius:16px;padding:14px}
.box.silv{border-color:#1d3b52;background:linear-gradient(180deg,#0d1a24,#0a0f18)}
.box h3{font-size:16px}
.metaline{display:flex;gap:12px;align-items:center;margin-top:12px}
.mini{display:grid;grid-template-columns:1fr 1fr;gap:5px 12px;flex:1}
.mini .k{display:block;font-size:11px;color:var(--mu2)}.mini .v{font-size:14.5px;font-weight:700;font-variant-numeric:tabular-nums}
/* table */
table{width:100%;border-collapse:collapse;font-size:14px;margin-top:8px}
th,td{text-align:left;padding:9px 8px;border-bottom:1px solid var(--bd2)}
th{color:var(--mu2);font-size:11.5px;text-transform:uppercase;letter-spacing:.8px}
td.n{font-variant-numeric:tabular-nums}
.pos{color:#7ee2a8}.neg{color:#ff9b95}
/* health */
.hgrid{display:grid;grid-template-columns:1fr;gap:8px;margin-top:10px}
@media(min-width:680px){.hgrid{grid-template-columns:1fr 1fr}}
.hrow{display:flex;gap:9px;font-size:13.5px;background:#0b1119;border:1px solid var(--bd2);border-radius:11px;padding:9px 11px}
.hrow .d{width:9px;height:9px;border-radius:50%;flex:0 0 9px;margin-top:5px}
.hrow.warn{border-color:#4a3a13}.hrow.red{border-color:#4a1f1f}
.overall{display:flex;align-items:center;gap:10px;font-size:15px}
.overall .dot{width:12px;height:12px;border-radius:50%}
/* footer */
footer{margin-top:34px;padding-top:16px;border-top:1px solid var(--bd2);color:var(--mu2);font-size:13px}
footer .cmd{display:flex;gap:10px;align-items:flex-start;padding:5px 0;color:var(--mu)}
code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;background:#131a26;border:1px solid var(--bd);
border-radius:7px;padding:2px 7px;font-size:13px;color:var(--gold2)}
.note{color:var(--mu);font-size:13.5px}
details.more{margin-top:12px;border-top:1px dashed #1d4a2f;padding-top:10px}
details.more summary{cursor:pointer;font-size:13.5px;color:#7ee2a8;font-weight:700;list-style:none}
details.more summary::-webkit-details-marker{display:none}
details.more summary::before{content:"▸ "}
details.more[open] summary::before{content:"▾ "}
details.more .dbody{margin-top:8px}
details.more table{margin-top:4px;font-size:13.5px}
.exitbox{margin-top:11px;background:#0b1119;border:1px solid #1d4a2f;border-radius:11px;padding:10px 12px;
display:flex;flex-direction:column;gap:3px;font-size:13.3px;color:var(--mu)}
.exitbox b{color:var(--tx);font-size:13.6px}
.exitbox span b{color:#cfe0f5}
.acard{margin:14px 0 0;border-radius:16px;padding:15px 16px;border:1px solid var(--bd);
background:linear-gradient(180deg,#101722,#0a0f18);position:relative;overflow:hidden}
.acard::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--acc,#f2c14e)}
.acard.entry{--acc:#46e08a;border-color:#1d4a2f;background:linear-gradient(180deg,#0f1b16,#0a0f18)}
.acard.skip,.acard.stop{--acc:#ff6b6b;border-color:#4a1f1f;background:linear-gradient(180deg,#1a1113,#0a0f18)}
.acard.target,.acard.quickbook{--acc:#ffd479;border-color:#4a3a13;background:linear-gradient(180deg,#1a1710,#0a0f18)}
.acard.prov{--acc:#6cc4ff;border-color:#1d3b52;background:linear-gradient(180deg,#0f1a24,#0a0f18)}
.acard h3{font-size:17px;letter-spacing:-.2px;margin-bottom:4px}
.acard ul{margin:8px 0 0;padding-left:18px;color:var(--mu);font-size:14px}
.acard li{margin:3px 0}
.acard .lead{color:var(--tx);font-size:14.5px;margin:2px 0 0}
.srow{display:grid;grid-template-columns:1fr;gap:4px;padding:11px 0;border-bottom:1px dashed #141c28}
.srow:last-child{border-bottom:0}
.sname{display:flex;flex-wrap:wrap;gap:10px;align-items:baseline}
.sname b{font-size:15.5px}
.sname .fam{font-size:11.5px;color:var(--mu2);font-family:ui-monospace,Consolas,monospace}
.sinfo{color:var(--mu);font-size:13.5px}
.schips{display:flex;flex-wrap:wrap;gap:6px;margin-top:3px}
.ok{color:var(--grn)}.warnc{color:#ffce54}.bad{color:#ff9b95}
"""


def _trade_card(i, r, cfg, meta=None):
    lot_g = float(cfg.get("gram_per_lot", 1) or 1)
    win_amt = (r["target_px"] - r["ref_px"]) * float(r["lots"]) * lot_g
    lose_amt = (r["ref_px"] - r["stop_px"]) * float(r["lots"]) * lot_g
    sec = str(r.get("contract_sec_id") or "").strip()
    exp = f" · exp {_esc(r['contract_expiry'])}" if sec and sec != "nan" else " · expiry app me confirm karo"
    if r.get("gap_lo_px") not in (None, "", "nan"):
        skip = (f"SKIP agar open {_inr(r['gap_lo_px'])}–{_inr(r['gap_hi_px'])} ke BEECH, "
                f"ya {_inr(r['gap_hard_px'])} se UPAR ho")
    else:
        skip = f"SKIP agar open {_inr(r['skip_above'])} se UPAR ho"

    fam = _fam_of(r)
    info = SETUP.get(fam, {})
    rule_txt = str(r.get('rule', '') or '')
    simple_fb, _, stat = rule_txt.partition(' — ')
    simple = info.get("name") or simple_fb.strip() or str(r['system'])
    setup_line = info.get("setup", "")
    why_line = info.get("why", stat or rule_txt)
    do_line = info.get("do", "")
    tech = f'{fam} — {stat.strip()}' if stat.strip() else fam
    strip = _stats_strip(meta)
    return f"""
    <div class="tcard">
      <div class="tno">TRADE #{i} · {_esc(r['system'])} · {_esc(r.get('side','BUY'))} · setup: {_esc(tech)}</div>
      <h3>{_esc(simple)}</h3>
      {f'<div class="rule">🎯 <b>Aaj ka setup:</b> {_esc(setup_line)}</div>' if setup_line else ''}
      {f'<div class="rule">💡 <b>Kyun kaam karti hai:</b> {_esc(why_line)}</div>' if why_line else ''}
      {strip}
      <div class="trow">
        <div class="tbox e"><div class="k">🛒 BUY ZONE (ref)</div><div class="v">{_inr(r['ref_px'])}</div></div>
        <div class="tbox t"><div class="k">🎯 TARGET +{r['tgt_pct']:g}%</div><div class="v">{_inr(r['target_px'])}</div></div>
        <div class="tbox s"><div class="k">🛑 STOPLOSS −{r['stop_pct']:g}%</div><div class="v">{_inr(r['stop_px'])}</div></div>
      </div>
      <div class="money">
        <span class="mchip win">💰 Jeet: +{_inr(win_amt)}</span>
        <span class="mchip lose">💔 Haar: −{_inr(lose_amt)}</span>
        <span class="mchip">⏱ max {r['max_hold']:g} din</span>
        <span class="mchip">📦 {_esc(r['contract'])}{exp}</span>
      </div>
      <div class="exitbox">
        <b>🚪 EXIT kab (bahar kaise nikalna hai):</b>
        <span>① target {_inr(r['target_px'])} chhua → <b>book karo</b></span>
        <span>② stop {_inr(r['stop_px'])} ya neeche gaya → <b>SL-M lag chuki hai, gaya</b></span>
        <span>③ {r['max_hold']:g} din me target nahi mila → <b>{r['max_hold']:g}ve din time-exit par bech do</b></span>
        <span>④ QUICK-BOOK: din-{float(cfg.get('quick_book_day',10)):g} tak +{float(cfg.get('quick_book_pct',2.5)):g}% ho gaya → <b>pehle hi book</b> (message me alert aayega)</span>
      </div>
      <ul class="steps">
        <li><span class="n">1</span><span>Dhan app → <b>BUY {r['lots']:g} lot</b> {_esc(r['contract'])} · product <b>NRML</b></span></li>
        <li><span class="n">2</span><span><b>Super Order</b> me entry + target + SL (−{r['stop_pct']:g}% SL-M) ek saath daalo</span></li>
        <li><span class="n">3</span><span>Lag jaane par batao: cmd box me <code>fill {r['order_id']} {r['ref_px']:g}</code></span></li>
        <li><span class="n">4</span><span class="bad">⚠️ {skip}</span></li>
      </ul>
      {f'<details class="more"><summary>📖 Is strategy ka poora record (22 saal)</summary><div class="dbody">{_detail_table(r, meta)}</div></details>' if meta else ''}
      {f'<p class="note" style="margin:10px 0 0">👉 <b>Karna sirf itna:</b> {_esc(do_line)}</p>' if do_line else ''}
    </div>"""


def _num(v, d=0.0):
    try:
        return float(v)
    except Exception:
        return float(d)


def _detail_table(r, meta):
    if not meta:
        return ""
    pm = meta.get("per_mo")
    pm_s = f" · {float(pm):.2f}/mahina" if pm not in (None, "", "nan") else ""
    rows = [
        ("Trigger rule", f"{_esc(_fam_of(r))}"),
        ("Purane trades", f"{int(_num(meta.get('n')))} {pm_s}"),
        ("Win rate", f"{_num(meta.get('win')):.1f}%"),
        ("Average per trade", f"+{_num(meta.get('avg')):.2f}%"),
        ("Aaj ka target / stop", f"+{_num(r.get('tgt_pct')):g}% / −{_num(r.get('stop_pct')):g}%"),
        ("Max holding", f"{_num(r.get('max_hold')):g} din (median {_num(meta.get('hold_med'), _num(r.get('max_hold'))):.0f} din)"),
        ("2.5%+ touch hua", f"{_num(meta.get('tgt_hit')):.0f}% trades me"),
        ("Risk ek trade par", f"−{_inr(_num(r['ref_px']) - _num(r['stop_px']))} (1 lot)"),
    ]
    return "<table>" + "".join(f"<tr><td>{k}</td><td class='n'><b>{v}</b></td></tr>" for k, v in rows) + "</table>"


def _silver_card(r, cfg):
    marg = float(cfg.get("silver_margin_per_lot", 19082) or 0)
    return f"""
    <div class="box silv">
      <h3>{_esc(r['system'])} — {_esc(r.get('name',''))}</h3>
      <div class="metaline">
        <div class="mini" style="grid-template-columns:repeat(2,1fr);gap:8px 14px">
          <div><span class="k">🛒 BUY ZONE (ref, ₹/kg)</span><span class="v">₹{float(r['ref_px']):,.0f}</span></div>
          <div><span class="k">🎯 TARGET +{r['tgt_pct']:g}%</span><span class="v">₹{float(r['target_px']):,.0f}</span></div>
          <div><span class="k">🛑 STOPLOSS −{r['stop_pct']:g}%</span><span class="v">₹{float(r['stop_px']):,.0f}</span></div>
          <div><span class="k">⏱ max hold</span><span class="v">{r['max_hold']:g} din</span></div>
        </div>
      </div>
      <div class="exitbox" style="border-color:#1d3b52">
        <b>🚪 EXIT kab:</b>
        <span>① target ₹{float(r['target_px']):,.0f} → bahar</span>
        <span>② stop ₹{float(r['stop_px']):,.0f} → bahar</span>
        <span>③ {r['max_hold']:g} din me kuch nahi hua → time-exit</span>
      </div>
      <p class="note" style="margin:10px 0 0">ⓘ {_esc(cfg.get('silver_contract','SILVERMIC'))} 1 kg: margin ~{_inr(marg)},
      risk ~{_inr(r['risk_inr'])} — aapke paas {_inr(cfg.get('capital',0))} hai, isliye <b>sirf signal</b> (trade nahi).</p>
    </div>"""


def build_daily_html(cfg, scan, mgr, applied, health, err=None, refresh_note=None,
                     out_dir=None, now=None, delay_note=None, alerts=None):
    """HTML file banao aur uska path return karo (content text message jaisa hi, bas stunning)."""
    import ms_algo as A                       # noqa: E402
    now = now or dt.datetime.now(A.IST)
    out_dir = out_dir or os.path.join(HERE, "outputs")
    os.makedirs(out_dir, exist_ok=True)
    red = bool(health and health["overall"] == "RED")
    new = (scan or {}).get("new") or []
    sig_day = bool(new)
    exit_adv = [m for m in (mgr or []) if m.get("status") == "EXIT_ADVICE"]
    sil = (scan or {}).get("silver") or {}

    # ---------------- banner
    if err:
        cls, lab, big = "stop", "DHYAN DO", "🔴 ALGO PROBLEM"
        note = "Aaj kuch bhi mat karo — maine error log kar diya hai. Mujhe message karo: \"health dekho\"."
    elif red:
        cls, lab, big = "stop", "RED ZONE", "⛔ AAJ KOI TRADE MAT KARO"
        supp = (scan or {}).get("suppressed") or []
        note = ("Data/channel me gadbad hai — pehle theek hone do. "
                + (f"Aaj ke {len(supp)} signal maine khud SKIP kar diye." if supp else ""))
    elif sig_day:
        cls, lab = "go", "ABHI KYA KARNA HAI"
        big = f"🟢 AAJ {len(new)} TRADE HAI"
        note = "MCX open (9:00–9:15 AM) par order lagao — neeche card me sab detail hai."
    else:
        cls, lab, big = "idle", "ABHI KYA KARNA HAI", "✅ KUCH NAHI — AAJ FREE HO"
        note = "Aaj koi naya trade nahi. Kal subah phir message aayega."
    if exit_adv and not red:
        note += f" 🔴 {len(exit_adv)} position band karni hai — POSITIONS dekho."
    if sig_day and not red and now.hour >= 9:
        note += (" ⚠️ Ye message MCX khulne (9:00 AM) ke BAAD aaya hai (GitHub delay) — "
                 "order lagane se pehle abhi ka price dekh lo aur SKIP band zaroor check karo.")

    # ---------------- header chips
    chips = []
    if scan:
        chips.append(f'<span class="chip">signal bar <b>{_esc(scan.get("sig_date","?"))}</b></span>')
        chips.append(f'<span class="chip">RSI14 <b>{scan.get("r14", float("nan")):.0f}</b></span>')
        chips.append(f'<span class="chip">state <b>{_esc(scan.get("state","?"))}</b></span>')
        chips.append(f'<span class="chip">open <b>{len(mgr or [])}</b>/4</span>')
    if sig_day:
        chips.append(f'<span class="chip good">🟢 {len(new)} naya signal</span>')
    if sil.get("new"):
        chips.append(f'<span class="chip b">👀 silver signal</span>')

    # ---------------- trade cards (system_table se strategy stats)
    sysmap, screenmap = {}, {}
    try:
        st = A.system_table()
        sysmap = {str(r_.fam): r_ for _, r_ in st.iterrows()}
    except Exception:
        sysmap = {}
    try:
        import pandas as _pd
        sc = _pd.read_csv(os.path.join(HERE, "data", "ms_gold_prod_screen_v5.csv"))
        screenmap = {str(r_.family): r_ for _, r_ in sc.iterrows()}
    except Exception:
        screenmap = {}

    def _meta_for(r):
        fam = _fam_of(r)
        row = sysmap.get(fam)
        scr = screenmap.get(fam)
        if row is None and scr is None:
            return None
        g = lambda k, src, d=None: (src.get(k) if src is not None else None) or d
        return dict(win=g("win", row, g("win", scr)),
                    avg=g("avg", row, g("avg", scr)),
                    n=g("n", row, g("n", scr)),
                    per_mo=g("per_mo", scr),
                    hold_med=g("hold", row) or g("hold_med", scr),
                    tgt_hit=g("tgt_hit", row, g("tgt_hit", scr)))

    cards = "".join(_trade_card(i, r, cfg, _meta_for(r)) for i, r in enumerate(new, 1))
    if not sig_day and scan and scan.get("skipped"):
        whys = {}
        for _, w in scan["skipped"]:
            k = w.split("(")[0].strip()
            whys[k] = whys.get(k, 0) + 1
        cards = ('<div class="box"><p class="note" style="margin:0">ⓘ Trigger tha par trade nahi liya: '
                 + ", ".join(f"{_esc(k)} ×{v}" for k, v in whys.items()) + "</p></div>")

    # ---------------- book
    bs = {}
    try:
        bs = A.book_summary()
    except Exception:
        bs = {}
    book_html = ""
    if bs:
        cap = float(cfg.get("capital", 0) or 0)
        roi = f"{100 * float(bs.get('inr_mo', 0)) / cap:.1f}%" if cap > 0 and bs.get("inr_mo") else "—"
        book_html = f"""
        <section>
          <div class="stitle"><h2>📊 Aapka book — kitna deta hai</h2></div>
          <p class="ssub">Yahi 11 systems aapke phone par signal bhej rahe hain (backtest 2003→2026).</p>
          <div class="kpis">
            <div class="kpi g"><div class="n">{bs.get('win',75.5)}%</div><div class="l">win rate</div></div>
            <div class="kpi y"><div class="n">{bs.get('per_mo',3)}</div><div class="l">trade / mahina</div></div>
            <div class="kpi b"><div class="n">{_inr(bs.get('inr_mo',372))}</div><div class="l">per mahina ({roi}/mo ROI)</div></div>
            <div class="kpi r"><div class="n">{bs.get('dd',-6.7)}R</div><div class="l">max drawdown</div></div>
          </div>
          <p class="note" style="margin-top:10px">avg +{bs.get('avg',1.16)}%/trade · per trade ~{_inr(bs.get('inr_per_trade',123))} ·
          {bs.get('hit25',72)}% trades 2.5%+ tak jaate hain · average hold {bs.get('hold',9)} din</p>
          {_scoreboard_html(cfg)}
        </section>"""

    # ---------------- strategy book (saare 11 setups)
    book_cards = ""
    try:
        st = A.system_table()
        for _, r_ in st.iterrows():
            fam = str(r_.fam)
            info = SETUP.get(fam, {})
            nm = info.get("name") or str(r_.get("name") or fam)
            scr = screenmap.get(fam)
            pm = scr.get("per_mo") if scr is not None else None
            pm_s = f" · {float(pm):.2f}/mahina" if pm not in (None, "", "nan") else ""
            book_cards += f"""
            <div class="srow">
              <div class="sname"><b>{_esc(nm)}</b><span class="fam">G-{_esc(fam)} · tgt {_num(r_.get('tgt')):g}% / SL {_num(r_.get('stp')):g}% / max {_num(r_.get('hold')):g} din</span></div>
              <div class="sinfo">{_esc(info.get('setup', ''))}</div>
              <div class="schips">
                <span class="chip good">win {_num(r_.get('win')):.0f}%</span>
                <span class="chip">avg +{_num(r_.get('avg')):.2f}%</span>
                <span class="chip">{int(_num(r_.get('n'))) } trades{pm_s}</span>
              </div>
            </div>"""
    except Exception:
        book_cards = ""

    strategy_html = f"""
    <section>
      <div class="stitle"><h2>📚 Aapki strategy book — ye 11 setups</h2></div>
      <p class="ssub">Gold sasta hone ki 11 alag-alag haalat. Jab bhi inme se koi haalat banti hai, phone par signal aata hai —
        entry/target/stop ke saath. Neeche har setup simple bhasha me.</p>
      <div class="box">{book_cards}</div>
    </section>""" if book_cards else ""

    # ---------------- silver
    silver_html = ""
    if sil.get("new"):
        silver_html = f"""
        <section>
          <div class="stitle"><h2>👀 Silver signal — sirf dekhne ke liye</h2></div>
          <p class="ssub">Silver ka margin bada hai (~{_inr(cfg.get('silver_margin_per_lot',19082))}), isliye trade nahi — sirf signal.</p>
          {''.join(_silver_card(r, cfg) for r in sil['new'])}
        </section>"""

    # ---------------- positions
    pos_html = ""
    if mgr:
        rows = ""
        for m in mgr:
            un = m.get("unreal")
            unc = "" if not isinstance(un, (int, float)) else ("pos" if un >= 0 else "neg")
            uns = f"{un:+.2f}%" if isinstance(un, (int, float)) else "?"
            try:
                pinr = (float(m["last"]) - float(m["entry"])) * float(cfg.get("gram_per_lot", 1) or 1) * float(cfg.get("lots", 1) or 1)
                ps = f"{pinr:+,.0f}"
            except Exception:
                ps = "?"
            act = "🔴 BAND KARO" if m["status"] == "EXIT_ADVICE" else "🟢 HOLD"
            rows += (f"<tr><td class='n'>#{int(float(m['order_id']))}</td><td>{_esc(m['system'])}</td>"
                     f"<td class='n'>{_inr(m['entry'])} → {_inr(m['last'])}</td>"
                     f"<td class='n {unc}'>{uns} ({_inr(ps)})</td><td class='n'>{m['days']} din</td>"
                     f"<td>{act}</td></tr>")
        pos_html = f"""
        <section>
          <div class="stitle"><h2>📌 Positions — aapke khule trade</h2></div>
          <div class="box"><table>
            <tr><th>#</th><th>system</th><th>entry → abhi</th><th>P&L</th><th>din</th><th>karna kya</th></tr>
            {rows}</table>
            <p class="note" style="margin:10px 0 0">Bechte waqt cmd box me: <code>close &lt;id&gt; &lt;price&gt;</code></p>
          </div>
        </section>"""

    # ---------------- health
    health_html = ""
    if health:
        try:
            nsys = len(A.system_table())
        except Exception:
            nsys = 11
        ov = health["overall"]
        dot = {"OK": "#46e08a", "WARN": "#f2c14e", "RED": "#ff6b6b"}.get(ov, "#93a3ba")
        rows = ""
        for c_ in health["reds"]:
            rows += (f'<div class="hrow red"><span class="d" style="background:#ff6b6b"></span>'
                     f'<span><b>⛔ {_esc(c_["check"])}</b> — {_esc(c_["detail"])}</span></div>')
        for c_ in health["warns"]:
            rows += (f'<div class="hrow warn"><span class="d" style="background:#f2c14e"></span>'
                     f'<span>⚠️ <b>{_esc(c_["check"])}</b> — {_esc(c_["detail"])}</span></div>')
        rows += (f'<div class="hrow"><span class="d" style="background:#46e08a"></span>'
                 f'<span>{nsys} systems check hue · signal bar {_esc((scan or {}).get("sig_date","?"))} · '
                 f'data {_esc((scan or {}).get("last_bar","?"))}</span></div>')
        if delay_note:
            dcol = "#f2c14e" if "delay" in delay_note else "#46e08a"
            rows += (f'<div class="hrow" style="border-color:#2a3342"><span class="d" style="background:{dcol}"></span>'
                     f'<span>⏱ <b>Run timing</b> — {_esc(delay_note)}</span></div>')
        health_html = f"""
        <section>
          <div class="stitle"><h2>🩺 Sehat — deep check</h2></div>
          <div class="box">
            <div class="overall"><span class="dot" style="background:{dot}"></span>
              <b>{_esc(ov)}</b> <span class="note">— {_esc(health.get('summary_line') or H_line(health))}</span></div>
            <div class="hgrid">{rows}</div>
          </div>
        </section>"""

    # ---------------- commands / footer
    pend = []
    try:
        pend = list(A.pending_orders().order_id) if hasattr(A.pending_orders(), "order_id") else []
    except Exception:
        pend = []
    pend_html = (f'<p class="note">⏳ PENDING: ' + ", ".join(f"#{int(float(x))}" for x in pend)
                 + " — fill hone par likho <code>fill &lt;id&gt; &lt;price&gt;</code></p>") if pend else ""
    applied_html = ""
    if applied:
        applied_html = ('<p class="note">📝 Aapki commands: ' + " · ".join(_esc(a) for a in applied) + "</p>")
    refresh_html = f'<p class="note warnc">⚠️ Data refresh: {_esc(refresh_note)}</p>' if refresh_note else ""
    qb = (f'<b>Quick-book:</b> din-{cfg.get("quick_book_day",10):g} tak +{cfg.get("quick_book_pct",2.5):g}% ho jaye to book kar do'
          if cfg.get("quick_book", True) else "")

    html = f"""<!doctype html><html lang="hi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MS Gold Algo — {now:%d %b %Y %H:%M} IST</title><style>{CSS}</style></head>
<body><div class="glow"></div><div class="wrap">

  <div class="kicker">MS GOLD ALGO · GOLDPETAL · MCX · backtest se seekha hua</div>
  <h1>🎯 Aaj ka message — {now:%d %b (%a)} · {now:%H:%M} IST</h1>
  <p class="sub">Ye wahi message hai jo pehle text me aata tha — ab poora design ke saath. Kholne ke liye file tap karo.</p>
  <div class="chips">{''.join(chips)}</div>

  {f'<section style="margin:6px 0 0">{_alert_cards(alerts, cfg)}</section>' if alerts else ''}

  <div class="banner {cls}">
    <div class="lab">{lab}</div>
    <div class="big">{big}</div>
    <div class="note">{ note }</div>
  </div>

  {f'<section><div class="stitle"><h2>🟢 Trade card — 1 lot GOLDPETAL</h2></div>{cards}</section>' if sig_day and not red else (f'<section>{cards}</section>' if cards else '')}

  {book_html}
  {strategy_html}
  {silver_html}
  {pos_html}
  {health_html}

  <footer>
    {applied_html}{pend_html}{refresh_html}
    <p class="cmd">👉 Order lagne par → <code>Run workflow</code> → cmd box: <code>fill 1 13980</code> (1 = order ka number)</p>
    <p class="cmd">👉 Bechte waqt → cmd box: <code>close 1 14100</code> · 👉 Order nahi lagaya → <code>skip 1</code></p>
    {f'<p class="cmd">👉 {qb}</p>' if qb else ''}
    <p class="cmd">👉 Agla message: kal subah ~8:30 IST · kharcha {_inr(cfg.get('cost_inr_per_lot',46))}/trade ·
       margin {_inr(cfg.get('margin_per_lot',1352))}/lot</p>
    <p class="note" style="margin-top:10px">File: <b>MS_Gold_Algo_message</b> (HTML) — offline khulti hai, internet ki zaroorat nahi.
       Ye backtest + system ka hisaab hai, future guarantee nahi. 1 lot, 1 mahina test — phir quantity badhao.</p>
  </footer>
</div></body></html>"""

    fn = f"MS_Gold_Algo_{now:%Y-%m-%d_%H%M}.html"
    path = os.path.join(out_dir, fn)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    latest = os.path.join(out_dir, "daily_message.html")
    with open(latest, "w", encoding="utf-8") as f:
        f.write(html)
    # purani files saaf karo — sirf latest 10 rakho (repo halka rahe)
    try:
        import glob as _glob
        old_files = sorted(_glob.glob(os.path.join(out_dir, "MS_Gold_Algo_*.html")))
        for old_f in old_files[:-10]:
            os.remove(old_f)
    except Exception:
        pass

    # ---------------- caption (notification me dikhne ke liye, max 1000 chars)
    if err:
        cap = "🔴 MS GOLD ALGO — problem. Aaj kuch mat karo. HTML file kholo."
    elif red:
        cap = "⛔ RED ZONE — aaj koi trade nahi. HTML file me detail hai."
    elif sig_day:
        first = new[0]
        head = (f"🟢 AAJ {len(new)} TRADE HAI" if len(new) == 1
                else f"🟢 AAJ {len(new)} TRADE HAIN")
        extra = f" ({first['system']} +{len(new)-1} aur)" if len(new) > 1 else f" ({first['system']})"
        cap = (f"{head}{extra} · entry {_inr(first['ref_px'])} · target {_inr(first['target_px'])} · "
               f"SL {_inr(first['stop_px'])} · max {first['max_hold']:g} din\n"
               f"👉 poora message HTML file me (tap karke kholo)")
    elif exit_adv:
        cap = f"🔴 {len(exit_adv)} POSITION BAND KARNI HAI — HTML file kholo."
    else:
        cap = "✅ KUCH NAHI — aaj koi naya trade nahi. HTML file me poora message (book, sehat, positions)."
    if delay_note and "delay" in delay_note:
        cap += f"\n⏱ {delay_note}"
    return path, cap[:1000]


def _alert_cards(alerts, cfg=None):
    out = ""
    for a in alerts or []:
        lines = "".join(f"<li>{_esc(l)}</li>" for l in (a.get("lines") or []))
        out += f'''
        <div class="acard {a.get('kind','info')}">
          <h3>{_esc(a.get('title',''))}</h3>
          <ul>{lines}</ul>
        </div>'''
        if a.get("kind") == "entry" and a.get("payload", {}).get("order") and cfg is not None:
            try:
                out += _trade_card(0, a["payload"]["order"], cfg, None).replace("TRADE #0", "AAJ KA ORDER")
            except Exception:
                pass
    return out


def build_alert_html(cfg, alerts, scan=None, mgr=None, now=None, out_dir=None):
    """Live alert (entry zone / target / skip / quick-book / provisional) — compact stunning HTML."""
    import ms_algo as A
    now = now or dt.datetime.now(A.IST)
    out_dir = out_dir or os.path.join(HERE, "outputs")
    os.makedirs(out_dir, exist_ok=True)
    prio = max([int(a.get("prio", 3)) for a in alerts] or [3])
    head = alerts[0].get("title", "Live alert") if alerts else "Live alert"
    cards = _alert_cards(alerts, cfg)
    px = None
    for a in alerts:
        if a.get("payload", {}).get("px"):
            px = a["payload"]["px"]; break
    chips = f'<span class="chip good">live ₹{px:,.0f}/g</span>' if px else ""
    if scan:
        chips += f'<span class="chip">signal bar <b>{_esc(scan.get("sig_date","?"))}</b></span>'
    html = f"""<!doctype html><html lang="hi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MS Gold Algo — LIVE ALERT {now:%H:%M} IST</title><style>{CSS}</style></head>
<body><div class="glow"></div><div class="wrap">
  <div class="kicker">MS GOLD ALGO · LIVE MONITOR (MCX hours · har ghante)</div>
  <h1>⏰ Live alert — {now:%d %b (%a)} · {now:%H:%M} IST</h1>
  <p class="sub">Ye alert live price ke hisaab se aaya hai. Neeche kya karna hai — saaf likha hai.</p>
  <div class="chips">{chips}</div>
  {cards}
  <footer style="margin-top:26px">
    <p class="cmd">👉 Kuch bhi kiya to GitHub → Actions → Run workflow → <code>cmd</code> box me likho:
      <code>fill &lt;id&gt; &lt;price&gt;</code> · <code>close &lt;id&gt; &lt;price&gt;</code> · <code>skip &lt;id&gt;</code></p>
    <p class="note">Ye live monitor hai — sirf tab message aata hai jab sach me kuch kaam ki baat ho
      (entry zone, target, stop, quick-book, ya setup ban raha ho). Din me ek hi alert ek baar aata hai.</p>
    <p class="note">Backtest 2004→2026: win 75.5% · +1.16%/trade · 3.01/mahina. Ye guarantee nahi — plan follow karo.</p>
  </footer>
</div></body></html>"""
    fn = f"MS_Gold_Algo_ALERT_{now:%Y-%m-%d_%H%M}.html"
    path = os.path.join(out_dir, fn)
    open(path, "w", encoding="utf-8").write(html)
    open(os.path.join(out_dir, "daily_message.html"), "w", encoding="utf-8").write(html)
    try:
        import glob as _glob
        for old_f in sorted(_glob.glob(os.path.join(out_dir, "MS_Gold_Algo*.html")))[:-10]:
            os.remove(old_f)
    except Exception:
        pass
    cap = f"{head}\n" + "\n".join((alerts[0].get("lines") or [])[:3]) + "\n👉 HTML file me poora detail (tap karke kholo)"
    return path, cap[:1000]


def H_line(health):
    r, w = len(health.get("reds", [])), len(health.get("warns", []))
    return f"{health.get('overall','?')} — {r} red, {w} warn"


def _scoreboard_html(cfg):
    """Test scoreboard (band trades) — journal se."""
    try:
        import pandas as pd
        import ms_algo as A
        j = A.journal_load() if hasattr(A, "journal_load") else None
        if j is None or not len(j):
            return ""
        j = j.copy()
        j["pnl_inr"] = j.pnl_inr.astype(float)
        n = len(j); wins = int((j.pnl_inr > 0).sum())
        return (f'<p class="note" style="margin-top:6px">🧪 TEST SCOREBOARD: {n} band trades · '
                f'win {round(100*wins/n)}% · total {_inr(j.pnl_inr.sum())}</p>')
    except Exception:
        return ""


# ------------------------------------------------------------------ sending
def _multipart(fields, file_field, file_path, ctype):
    b = "----MSAlgo" + uuid.uuid4().hex
    out = b""
    for k, v in fields.items():
        out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8")
    with open(file_path, "rb") as f:
        data = f.read()
    out += (f'--{b}\r\nContent-Disposition: form-data; name="{file_field}"; '
            f'filename="{os.path.basename(file_path)}"\r\nContent-Type: {ctype}\r\n\r\n').encode("utf-8")
    out += data + f"\r\n--{b}--\r\n".encode("utf-8")
    return out, f"multipart/form-data; boundary={b}"


def send_report(path, caption, title="MS Gold Algo", tags=None, priority=3):
    """Telegram = HTML document (+caption) · ntfy = caption text + HTML attach.

    Env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, NTFY_TOPIC (comma se kai), NOTIFY_CHANNEL,
         DRY_RUN=1 -> kuch nahi bhejta.
    """
    if os.getenv("DRY_RUN"):
        print(f"[DRY] report file: {path}\n[DRY] caption: {caption}")
        return "dry-run"
    out = []

    # ---- Telegram
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if tok and chat and os.getenv("NOTIFY_CHANNEL", "").lower() not in ("ntfy", "whatsapp"):
        body, ctype = _multipart({"chat_id": chat, "caption": caption}, "document", path, "text/html")
        req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendDocument", data=body,
                                     headers={"Content-Type": ctype}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                ok = r.status == 200
            out.append("telegram:" + ("✅" if ok else "❌"))
        except Exception as e:
            out.append(f"telegram:❌ {str(e)[:80]}")

    # ---- ntfy (text + attachment)
    topics = [t.strip() for t in (os.getenv("NTFY_TOPIC", "") or "").split(",") if t.strip()]
    if topics and os.getenv("NOTIFY_CHANNEL", "").lower() not in ("telegram", "whatsapp"):
        tag_list = ([t.strip() for t in str(tags or "").split(",") if t.strip()]
                    if not isinstance(tags, (list, tuple)) else list(tags))
        if not tag_list:
            tag_list = ["chart_with_upwards_trend"]
        payload = {"topic": None, "message": caption, "title": title, "tags": tag_list,
                   "priority": int(priority), "markdown": True}
        for t in topics:
            p = dict(payload); p["topic"] = t
            okn = False
            try:
                r = urllib.request.Request("https://ntfy.sh/", data=json.dumps(p).encode("utf-8"),
                                           headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(r, timeout=30) as resp:
                    okn = resp.status == 200
            except Exception:
                okn = False
            # attachment (ASCII headers — emoji se latin-1 crash hota hai)
            ascii_ok = lambda s: s.encode("ascii", "ignore").decode()
            try:
                with open(path, "rb") as f:
                    r2 = urllib.request.Request(
                        f"https://ntfy.sh/{t}", data=f.read(),
                        headers={"Filename": os.path.basename(path), "Title": ascii_ok("MS Gold Algo message"),
                                 "Message": ascii_ok("HTML message attached - tap to open"), "Priority": "3",
                                 "Tags": "page_facing_up"}, method="PUT")
                with urllib.request.urlopen(r2, timeout=60) as resp2:
                    oka = resp2.status == 200
            except Exception:
                oka = False
            out.append(f"ntfy[{t}]:" + ("✅" if okn else "❌") + "/" + ("✅" if oka else "❌"))
    res = " ".join(out) or "kuch bhi configured nahi"
    print("send:", res)
    return res
