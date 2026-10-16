# MS GOLD ALGO — GitHub + Phone Alerts (Stage-1 automation)

Ye ek **chhota package** hai jo khud-ba-khud (GitHub ke server par, 24x7) roz chalta hai aur
**aapke phone par message** bhej deta hai:

- 🟢 **NAYA ORDER** — kaunsa contract, kitne lot, entry, **target**, **stop**, aur SKIP price
- 📌 **OPEN POSITIONS** — HOLD ya **CLOSE KARO** (+ P&L %)
- 🟡 **"Aaj koi trade nahi"** — aise din aap kuch nahi karte

Aapko na laptop chalu rakhna hai, na koi app chalani hai. Sirf **GitHub account** chahiye (free).

---

## 0) Isme kya hai (files)

| File | Kaam |
|---|---|
| `ms_algo.py` | Asli algo (11 gold systems, entry/target/stop/positions) |
| `run_daily.py` | Roz ka runner: data → signals → message → state save |
| `notify.py` | Message bhejne wala (Telegram / ntfy / WhatsApp) |
| `.github/workflows/algo.yml` | GitHub ka timer (roz 3 baar apne aap chalta hai) |
| `data/` | Panel data + algo ki state (orders, positions, journal, user_input.txt) |

---

## 1) GitHub repo banao (5 minute)

1. [github.com](https://github.com) par account banao / login karo
2. Top-right **+** → **New repository**
   - Name: `ms-gold-algo`
   - **Private** ✅ (zaroori — aapki trades kisi ko nahi dikhni chahiye)
   - Create repository
3. Repo me **"uploading an existing file"** link par click karo
4. Is folder ki **saari files/folders** (`.github`, `data`, `ms_algo.py`, `run_daily.py`, `notify.py`, `requirements.txt`, `README.md`) **drag & drop** karke **Commit changes**
   - ⚠️ Agar `.github` folder upload na ho: **Add file → Create new file** → naam me type karo
     `.github/workflows/algo.yml` → (slash type karte hi folder ban jayega) → content paste → Commit
5. **Settings → Actions → General → Workflow permissions** → **Read and write permissions** → Save
   *(ye state save karne ke liye zaroori hai)*

---

## 2) Phone par message — Telegram (recommended, free, 3 minute)

1. Phone/desktop me Telegram kholo → search **@BotFather** → `/newbot`
   - Naam: `MS Gold Algo` · username: `msgold_algo_bot` (unique hona chahiye)
   - BotFather ek **token** dega: `123456789:AAH...` → copy karo
2. Apne naye bot ko kholo (link BotFather ne diya hoga) → **START** dabao (ya "hi" bhejo)
3. Browser me kholo: `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - JSON me `"chat":{"id":123456789` — **wahi number** aapka CHAT_ID hai
4. GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**
   - `TELEGRAM_BOT_TOKEN` = token
   - `TELEGRAM_CHAT_ID` = wahi number
5. **Actions** tab → "MS Gold Algo — daily signal" → **Enable** → **Run workflow** (test)
   - 1 minute me phone par message aa jayega ✅

### ntfy — 2 minute (free, koi signup nahi, sabse aasan)
1. Phone me **ntfy** app install karo (Play Store / App Store, developer: *binwiederhier*)
2. App kholo → notification permission → **Allow**
3. Neeche daayein **"+"** dabao → Topic name me likho (exact): **msgold-abhay-k9x2** → **Subscribe**
4. Phone Settings → Apps → ntfy → Battery → **Unrestricted** (warna notification late aayegi)
5. GitHub Secrets me daalo: `NTFY_TOPIC` = `msgold-abhay-k9x2`

### WhatsApp (CallMeBot — unofficial; kabhi kaam karta hai kabhi nahi)
1. Contact save karo: **+34 644 51 95 23** (naam: CallMeBot)
2. WhatsApp se us number ko **bilkul yahi** message bhejo: `I allow callmebot to send me messages`
3. 1–3 minute me reply: `APIKEY is 123456` → wahi 6-digit key
4. Secrets: `WHATSAPP_PHONE` = `+91XXXXXXXXXX`, `WHATSAPP_APIKEY` = key
5. Reply na aaye to doosra number try karo: **+34 621 01 86 45** (wahi message). Wo bhi na chale → WhatsApp abhi band hai, **Telegram** use karo.

### Telegram — 3 minute, sabse bharosemand (recommended)
1. Telegram me **@BotFather** → `/newbot` → naam `MS Gold Algo`, username `msgold_abhay_bot`
2. BotFather ka **token** copy karo (`123456789:AAH...`)
3. Apne naye bot ko kholo → **START** dabao
4. Secrets: `TELEGRAM_BOT_TOKEN` = token, `TELEGRAM_CHAT_ID` = apna chat id
   *(chat id nikalne ka aasan tareeka: browser me `https://api.telegram.org/bot<TOKEN>/getUpdates` kholo → `"chat":{"id":123456789` — wahi number)*

*(Teenon / sab ek saath bhi rakh sakte ho — jo bhi configured hoga, sab par message jayega.)*

---

## 3) Roz ka schedule (apne aap)

| Time (IST) | Kya hota hai |
|---|---|
| **03:00** | Data refresh → COMEX bar final → signal check → **message** (naya order / no trade) |
| **08:30** | Backup run (agar 03:00 wala delay/fail ho gaya ho) |
| **00:30** | MCX band hone ke baad summary: positions ka update + aapki likhi commands apply |

Time thoda idhar-udhar ho sakta hai (GitHub free service me 10-30 min ka delay normal hai) — isliye 03:00 + 08:30 **dono** rakhe hain.

---

## 4) Aapke 3 kaam

1. **Order lagana** (jab message me aaye) — Dhan app me: Super Order (entry + target + SL ek saath), product **NRML**, qty 1
2. **Fill likhna** — repo me `data/algo/user_input.txt` kholo → pencil (edit) → likho:
   ```
   fill 1 13980
   ```
   (`1` = order number, `13980` = aapko mila bhav) → **Commit changes**
3. **Bechne par** — wahi file:
   ```
   close 1 14100
   ```
   File agli run me khud khaali ho jaati hai aur aapko message me confirmation mil jaata hai.

> File phone ke browser se bhi edit ho jaati hai (github.com → repo → data/algo → user_input.txt → ✏️ → commit).

---

## 5) Dhyan rakhne wali baatein

- **SKIP rule (naya, 16-Oct — improvement phase 2):** MCX open aur ref (signal close) ka gap dekhna:
  **+0.5% se +1.0% ke beech** ho → order **chhod do** (dead-zone: backtest me 144 trades, sirf 58% win, +0.11% avg),
  **+2.5% se upar** ho → **chhod do** (bahut bada jump, avg −1.93%). Baaki sab gaps OK hain (ref−0 se +0.5%, aur +1.0% se +2.5%).
  Purana rule (open 1%+ upar = skip) **hata diya** — usme paisa bans raha tha. Message me ab teenon price (band-lo, band-hi, hard) diye aate hain.

- **QUICK-BOOK (naya, 16-Oct):** har position par rule — **din-5 par +1.5% ho gaya to turant book kar do** (`quick_book`, `quick_book_day`, `quick_book_pct` config me). Backtest: win **70.6% → 77%**, avg +0.99% → +1.16%/trade, DD same (−5.4R). Algo ka `manage` step khud "🔴 CLOSE KARO — QUICK-BOOK" advice deta hai.
- **SILVER SIGNALS (naya, 16-Oct — signal-only):** silver ke 3 book systems (`lag_gs80`, `rsi30r5`, `dxy_dn`) ka roz check + message me entry/target/stop. **Trade nahi** — `SILVERMIC` 1 kg ka margin ~₹19,082 aur 1 lot ka risk ~₹23,000 hai, jo abhi ke ₹6,380 cash se bahar hai. Sirf track karne ke liye (jab cash badhega to `silver_*` config se trade mode on ho sakta hai). Signals `data/algo/silver_signals.csv` me log hote hain.
- **Super Order:** MCX par iske target/SL legs **sirf usi din** valid hote hain. Roj subah check kar lo ki legs zinda hain; warna alag **SL-M** + limit target lagao (ek fill ho to doosra **turant cancel**).
- **Paise:** 1 lot margin ≈ ₹1,352. Message me jo bhi order aaye, pehle fund check (`python3 dhan_check.py` aapke computer par, ya Dhan app me) kar lo.
- **Ye package order khud NAHI lagata** — sirf batata hai. (Order khud lagane wala Stage-2 hai: uske liye static IP + roz naya token chahiye.)
- **Secrets** kabhi code me mat likho — sirf GitHub Secrets me.

- **V4 BOOK (naya, 16-Oct — HIGH-WIN + FAST):** book ab **14 systems** = 11 purane + 3 naye fast families
  (**drip1** = 1 din −1.8% dip & RSI14<55, cfg 3.0/10/15 · **core** = RSI14<40 & pctB<0.30, cfg 2.5/12/15 ·
  **up_dip1** = UP trend me 1 din −1.0% dip, cfg 2.5/10/15). Backtest (1,097 trades): **77.7% win · +1.00%/trade ·
  med hold 7 din · 4.00 trades/month · R/yr +4.26 · DD −7.2R** (purana TierC: 70.6% / +0.99% / 13 din / 3.33/mo / +3.40).
  IS +0.98 / OOS +1.01 → overfit nahi. Files: `data/ms_gold_prod_systems_v4.csv`, `data/ms_gold_prod_screen_v4.csv`.

---

## 6) Test / troubleshooting

- **Test run:** Actions tab → workflow → **Run workflow**. Log me `===== MESSAGE =====` dikhega, aur phone par message aayega.
- **Message nahi aaya?** Secrets ki spelling check karo (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`), aur bot ko phone se ek baar "START" bheja hua hona chahiye.
- **Actions fail?** Log kholo; 99% case me `pip install` ya `yfinance` ka net issue hota hai — dobara Run workflow kar do.
- **Local test (computer par):** `pip install -r requirements.txt` phir `DRY_RUN=1 python run_daily.py` (message sirf print hoga).

---

*Algo: GOLD-only book (11 systems, 3.33 trades/month, win 70.6%, avg +0.99%/trade, DD −7.0R).
Ye Stage-1 (semi-manual) hai — order aap lagate ho, algo batata hai. Aage Stage-2 (order auto-lagana) ke liye static IP + roz naya token chahiye.*

---

## 7) DEEP CHECK (16-Oct) — kya verify hua

- ✅ **Data completeness:** panel (5,319 trading bars) + parity + 6 GOLDPETAL contracts + silver series — sab repo me hain; yfinance se roz naya data khud aa jata hai.
- ✅ **Trigger baseline exact match:** saare 11 families ke triggers published book se **EXACT** match (lag_gs80pct 527 · lag_rel 309 · coil_r3 284 · pb20 250 · dxy_dn 138 · gaprsi 83 …) — matlab GitHub par jo signal banega, wahi book wala hai.
- ✅ **Lifecycle test:** order ticket → fill → manage → close → journal (P&L sahi: 2% par ₹234 net) — poora cycle chala kar dekha.
- ✅ **2 run ek saath:** tail data duplicate nahi hota; state file sahi commit hoti hai; workspace par koi extra likhai nahi hoti.
- 🐛 **Fix 1 (bada):** `lag_rel` family GitHub par **dead** thi (silver series module missing) → ab canonical silver series `data/silver_inr.csv` bundle ki hai + naye dinon ke liye parity ratio se same-scale update (pehle naye din par ±96% ka fake jump aa jata).
- 🐛 **Fix 2:** purane PENDING orders (jinka entry day nikal gaya, fill/skip nahi hua) ab **auto-EXPIRED** hote hain — slot block nahi rehta; message me bata bhi deta hai.
- 🐛 **Fix 3:** self-test GitHub par crash hota tha (backtest engine missing) → ab data-integrity check (baseline comparison) chalta hai.
- 🐛 **Fix 4:** naye (live tail) dinon ke silver scale consistency + chhote message/log text fix.

**Test command (repo me):** `python3 -c "import ms_algo as A; A.selftest(A.cfg_load())"` → "DATA CHECK PASS" aana chahiye.

---

## 8) 🩺 DEEP HEALTH CHECK + RED ZONE (naya)

**Har report se PEHLE** 11-point deep diagnosis chalti hai (`healthcheck.py`) — data fetching se lekar core sab:

| # | Check | RED kab |
|---|---|---|
| 1 | data_fetch — naya bar aaya? kitna purana? | data bahut purana |
| 2 | data_integrity — OHLC valid? null? ±8% jump? | kuch bhi galat |
| 3 | silver_scale — INR vs USD source cross-check | scale toota (lag_rel galat) |
| 4 | triggers — 11 families baseline se match | koi diff |
| 5 | book_config — 11 systems + sane settings | load fail |
| 6 | contract — expiry hold me fit hai? | fit nahi |
| 7 | ledger — duplicate/orphan/stale pending | duplicate/orphan |
| 8 | cash_margin — capital ≥ slots × margin | cash kam |
| 9 | channels — Telegram **live getMe** + ntfy | koi channel dead |
| 10-11 | clock (provisional bar) + run_time | WARN |

**Safety gate:** koi bhi RED → message sabse pehle: **"⛔ AAJ KOI TRADE MAT KARO"** + red item 👇 me mark. Signal order hold par chala jata hai — galat data par trade nahi hoti.

**Message ka naya look (Telegram par bold, ntfy par same text):**
```
🎯 MS GOLD ALGO — 16 Oct (Fri) · 3:18 AM
━━━━━━━━━━━━━━━━━━━━
👉 ABHI KYA KARNA HAI
   ✅ KUCH NAHI — aaj koi trade nahi.
   — ya —
   🟢 AAJ 1 TRADE: BUY 1 lot GOLDPETAL NOV FUT · Target ₹14,481 · STOP ₹12,312 · SKIP ₹14,131
━━━━━━━━━━━━━━━━━━━━
🩺 SEHAT: 🟢 sab theek (11 checks pass) · data kal ka · 11/11 systems
━━━━━━━━━━━━━━━━━━━━
👉 "fill 1 13980" / "close 1 14100" · Agla message: kal subah ~8:30
```
Health history: `data/algo/health_log.csv` (har run ki entry).

**Test command:** `python3 healthcheck.py` → table (exit code 1 agar RED).

## V5 BOOK (REDESIGN, 16-Oct-2026) — DEFAULT

Chaaron side (gold buy / gold sell / silver buy / silver sell) ka redesign. Rules jo user ne diye:
**win ~75%+, mahine me 2+ trade (gold+silver ka same setup = 1), har trade me 2.5-3%+ ka target.**

| Side | Book | Trades/mo | Win | Avg | 2.5%+ touch | Verdict |
|---|---|---|---|---|---|---|
| GOLD BUY  | 11 systems (K=4) | **3.01** | **75.5%** | +1.16% | 72.1% | ✅ LIVE |
| SILVER BUY| 6 systems (K=3) | 2.41 | 76.1% | +0.74% | 79.6% | ✅ signal-only |
| GOLD SELL | 27 families scanned | — | best 72.5% | +0.14% | — | ❌ band |
| SILVER SELL| 29 families scanned | — | best 74.4% | −0.26% | — | ❌ band |

- Files: `data/ms_gold_prod_systems_v5.csv`, `data/ms_gold_prod_screen_v5.csv`, `data/ms_silver_prod_systems_v5.csv`
- Naye gold families: `r5_deep`, `mm_capit`, `gvz_spike`, `dip_above_mean`, `trend_pull_rsi`, `gapdown_up`, `r21pb`
- Naya silver book: `gapdn`, `rsi30r5`, `up_pb`, `up_gap`, `gs_ext_dip`, `mm_capit` (pehle: lag_gs80/dxy_dn/rsi30r5)
- Purana book chahiye to: `MS_BOOK=v4 python3 ms_algo.py run` (dono files repo me hain)
- Panel me `mm_pct_v3` + silver OHLC add hua (silver ke gap/state wale masks ab live chalte hain)
- Trigger baseline ab **21 families** ka (data-drift check)


## 9) MESSAGE ka naya look (16-Oct, ultra-deep audit ke baad)

Dono channel par same content, par apne-2 style me:

| Channel | Format | Extra |
|---|---|---|
| **Telegram** | HTML — bold headings, monospace numbers | 4096+ char ho to auto 2 message; HTML fail ho to plain fallback |
| **ntfy** | Markdown (**bold**, `code`) | Title + Tags + Priority (signal day = high) + byte-safe chunks |
| **WhatsApp** (optional) | plain text | CallMeBot |

**Message ke sections (upar se neeche):**
1. `👉 ABHI KYA KARNA HAI` — pehli line me seedha kaam (aaj trade hai / nahi / position band karni hai)
2. `🟢 TRADE #n` — har signal ka card: system ka simple naam + win% + avg% (kitna deta hai), Dhan app me kya order lagana hai, Entry/Target/SL, **jeet kitne ₹ / haar kitne ₹**, skip-band, max hold
3. `📊 AAPKA BOOK` — 11 systems · ~3 trades/month · **win 75.5%** · avg +1.16% · **₹371/month (5.8% ROI)** · per trade ₹123 · DD −6.7R · 72% trades 2.5%+ touch · + **TEST SCOREBOARD** (band trades ka win% + ₹)
4. `👀 SILVER SIGNAL` — signal-only (trade nahi; margin ₹19,082 > cash)
5. `📌 POSITIONS` — khule trade: entry → aaj, P&L ₹, HOLD/BAND karo
6. `🩺 SEHAT` — deep health check (RED ZONE warning bhi)
7. Footer — commands ka reminder + quick-book rule + agla message ka time

**Safety:** RED ZONE ho to naye signals **khud SKIP** mark ho jaate hain (safety), message me batata hai.
**Duplicate fix:** silver ka same signal 7 din me dobara nahi bhejta (pehle roz bhej deta tha).

## 10) Ultra-deep audit (16-Oct) — bugs jo fix hue

| # | Bug | Asar | Fix |
|---|---|---|---|
| 1 | Silver ka `gap` formula galat tha (close-to-close ban raha tha) | `gapdn` + `up_gap` (1.55 trades/mo) live me kabhi fire nahi karte the | gap = open / pichhla close (USD, currency cancel) — backtest se exact match; tail ke liye SI=F ka Open fetch |
| 2 | Silver signal **har run** dobara bhejta tha (3 run/din) | phone par spam | 7-din dedupe (family-wise) + test suite me naya test |
| 3 | `mm_capit` family live me dead thi (mm_pct tail me NaN) | 0.23 trade/mo gayab | tail rows par panel ki last value ffill |
| 4 | **ntfy emoji Title** = HTTP 0 (latin-1 header error) | ntfy par message **pahunchta hi nahi tha** | ntfy ab JSON publish (Unicode + markdown + priority) — 200 OK |
| 5 | Telegram HTML fail hone par silently 0/1 | message gayab | HTML → auto plain fallback + asli error text |
| 6 | Refresh fail = poora run "PROBLEM" | internet hiccup par trade block | refresh non-fatal + message me ⚠️ note |
| 7 | `channels` RED → trade block | sirf secret missing hone par din kharab | WARN (infra) — RED sirf data/ledger issues par |
| 8 | Message me `11/11 systems` hardcoded | naye systems add karne par galat | dynamic count |
| 9 | "abhi ₹6,380 hai" hardcoded | capital badalne par galat | config se |
| 10 | `close` par days_held 0 aata tha | scoreboard stats galat | entry_date se compute |
| 11 | pandas concat FutureWarning (fill/close) | log ganda | column-reindex se fix |
| 12 | `fill 1` (price missing) par confusing error | user confuse | clear format message |
| 13 | 60-din inactivity par GitHub cron band | signal band ho jaate | daily state commit (activity) + manual Run workflow; README me note |
| 14 | requirements unpinned | yfinance/pandas breaking upgrade | version ranges pin |

**Verification (16-Oct):** workspace tests **45/45 PASS** · healthcheck **11 OK / 0 WARN / 0 RED** (secrets ke saath) · repo selftest **DATA CHECK PASS** · healthcheck **21/21 triggers exact** · fresh-clone dry run OK · Telegram + ntfy dono par live message ✅

## 11. 📄 Message ab HTML file me (16-Oct-2026) — text ki jagah

Pehle roz ka message **plain text** me aata tha. Ab **wahi message ek visually stunning HTML file** me aata hai:

| Kahan | Kya milta hai |
|---|---|
| **Telegram** | 📄 HTML file + chhota caption (notification me: “🟢 AAJ 1 TRADE HAI — entry/target/SL”) |
| **ntfy** | caption text + 📄 HTML file attach (tap karke khulti hai) |
| **GitHub Actions** | artifact `ms-gold-message` (30 din) — phone/PC par download karke dekh sakte ho |

File me kya hai (sab kuch bilkul pehle jaisa, bas design ke saath):
1. 🌅 **ABHI KYA KARNA HAI** banner — 🟢 trade / ✅ free / ⛔ RED ZONE / 🔴 problem (sabse upar, bada)
2. 🟢 **TRADE cards** — entry / target / stop boxes, ₹jeet–₹haar, max din, 4 seedhe step (Dhan app → Super Order → fill likho → skip rule)
3. 📊 **Aapka book** — win 75.5% · 3.01 trade/mo · ₹371/mo · DD −6.7R + test scoreboard
4. 👀 **Silver signal** (sirf dekhne ke liye) · 📌 **Positions** P&L · 🩺 **Sehat** deep check
5. Footer me aapki commands (fill/close/skip) + quick-book rule

Technical: `report_html.py` (naya module, sirf standard library) `run_daily.py` se call hota hai.
Text send fail ho jaye to purana text message **fallback** ban jaata hai (message kabhi chupta nahi).
Files: `outputs/MS_Gold_Algo_YYYY-MM-DD_HHMM.html` + `outputs/daily_message.html` (latest).

## 12. 🧪 e2e_verify.py — poora system ek command me test karo

`python3 e2e_verify.py` chalane par 4 layer check hoti hain (~10 sec):

| Layer | Kya check hota hai |
|---|---|
| **1. Backtest integrity** | `data/ms_gold_prod_trades.csv` (821 trades) ko live pipeline (`build_frame`) ke prices se match karta hai + win/avg/per-month recompute (75.5% · +1.16% · 3.01/mo) + 11 systems ka win% screen CSV se |
| **2. Data fetching** | yfinance refresh chalta hai? panel me taaza bar (gold $, DXY, USDINR, silver) aaya? |
| **3. Integration** | `build_frame` → `signal_scan` → `healthcheck` → `system_table` — sab chalta hai? aaj ke signals/silver status |
| **4. HTML completeness** | gold card (BUY ZONE/TARGET/STOPLOSS/EXIT/₹jeet-₹haar/skip), silver card (BUY ZONE/TARGET/STOP/EXIT/sirf-signal note), BOOK, STRATEGY BOOK, POSITIONS, SEHAT, COMMANDS — har section maujood hai? |

End me `RESULT: N PASS · M FAIL` print hota hai. Fail hone par wahi line dikhati hai jahan dikkat hai.

### 16-Oct (rev14) me 2 fix
1. **`data/ms_gold_prod_trades.csv` purani V3 book ki thi** (914 trades, `dxy_z`/`up_gap` jaise purane families) — V5 live book se match nahi karti thi (win 70.6% vs 75.5%). Ab **V5 ki 821 trades** se regenerate ki gayi hai (win 75.5% · avg +1.16% · 3.01/mo) — per-system win% bhi screen se match (r5_deep 89.5, pb20 77.8, lag_gs80pct 77.3 …).
2. **HTML cards me explicit BUY ZONE + EXIT block** — pehle entry/target/stop the, ab:
   - 🛒 **BUY ZONE (ref)** — kahan se kharidna hai (+ SKIP band: kaunsa open skip karna hai)
   - 🚪 **EXIT kab** — ① target chhua → book ② stop laga → gaya ③ max din par time-exit ④ quick-book (din-10 +2.5%)
   - Silver card me bhi wahi (BUY ZONE / TARGET / STOPLOSS / EXIT), saath me "sirf signal, trade nahi" ka kaaran.

## 13. ⏱️ Timing delay + duplicate guard + 4th cron (17-Oct rev15)

### A) Timing delay (GitHub cron late chalta hai)
GitHub ke scheduled runs **5–30 min late** (kabhi zyada) chal sakte hain — iska official fix nahi hai.
Solution (3 layer):

| Layer | Kya hota hai |
|---|---|
| **4th cron "safety net"** | `0 0 * * 1-5` = **05:30 IST** — agar 03:00 aur 08:30 wale delay/fail ho gaye, ye bacha lega (aap 7:30 tak jaag rahe ho → 8:30 se pehle message) |
| **⏱ Run timing line** | Har message ki SEHAT section me: *"scheduled 08:30 IST tha · actual 09:40 IST (delay +70 min)"* — pata chalta hai script time par chali ya late |
| **⚠️ Late warning** | Agar trade-day par message **9:00 AM ke baad** aaya → banner me: *"Ye message MCX khulne ke BAAD aaya — order se pehle abhi ka price dekho + SKIP band check karo"* |

### B) Duplicate guard (03:00 + 08:30 + 05:30 — teen runs, ek hi message)
Pehle 03:00 aur 08:30 wale dono apna-apna message bhej dete the (same content, do baar).
Ab `data/algo/last_sent.json` me message ka **fingerprint** (sig_date + naye orders + exits + silver + commands + health) save hota hai:
- Same haalat → **duplicate skip** (kuch bhejta hi nahi, chup-chaap khatam)
- Naya signal / exit / command / health badla / error → fingerprint badalta hai → **message jaata hai**
- Jaan-boojh kar bhejna ho: workflow me **`force: true`** (naya input)
- Message kisi channel par na pahuncha ho → fingerprint **save nahi** hota (agla run phir koshish karega)

### C) State commit ke 3 layer
"Save state" ab run ke **pehle** aur **baad** dono hota hai + `git pull --rebase --autostash` (race-safe) — aapki `fill`/`close`/`skip` commands aur naye orders kabhi lose nahi honge.

### D) Auto cleanup
`outputs/` me sirf **latest 10** HTML messages rakhte hain (baaki delete) — repo halka rehta hai.

## 🔴 Live Monitor — MCX hours me har ghante check (NAYA)

Market khula hone par (Mon–Fri, 9:00 AM – 11:30 PM IST) **har ghante** khud check hota hai aur **sirf tab message** aata hai jab kuch karne layak ho:

| Alert | Kab | Message me kya |
|---|---|---|
| ⏰ ENTRY ZONE | pending order ho aur live price ref par aa jaye | "ABHI ORDER LAGAO" + target/SL |
| 🚫 HARD SKIP | price gap zone ke upar chala jaye | "aaj ye trade chhod do" |
| 🎯 TARGET HIT | open position ka target chhu jaye | "BOOK KARO" + ₹ faayda |
| 🛑 STOP HIT | stop tak aa jaye | "BAHAR NIKAL JAO" |
| 💚 QUICK-BOOK | din-10+ aur +2.5% (rule) | "abhi book kar sakte ho" |
| ⏳ SETUP BAN RAHA | bar ke andar setup trigger ho jaye | "adhoora hai — order mat lagao, confirm hone do" |

- **Spam nahi:** ek din me ek hi alert ek baar (dedup). Kuch nahi hua to **koi message nahi**.
- **RED ZONE** me koi alert nahi aata (naye signal band rehte hain).
- Alert ke saath **HTML file** aati hai (Telegram + ntfy dono par) — entry price, target, SL, ₹ jeet/haar, kya karna hai.
- **Khud test karna ho:** Actions → Run workflow → `mode = monitor` → Run. (Manual default `daily` rehta hai.)

Crons: 4 daily (03:00 / 05:30 / 08:30 / 00:30 IST) + 15 hourly monitor (09:00 se 23:00 IST tak).
