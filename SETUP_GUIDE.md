# SETUP GUIDE — GitHub par buy-side algo (5 minute ka kaam)

Is bundle ko GitHub par daalne ke baad **roz subah signal aapke phone par** aayega (Telegram + ntfy push), aur aap Dhan app me order laga paoge. Algo khud kuch trade nahi karta — sirf signal + hisaab rakhta hai.

---

## 📦 Aapko kya chahiye
1. **GitHub account** (free) — pehle se hai to theek, warna github.com par bana lo.
2. **Ye zip file** (`ms-gold-algo-repo-rev10.zip`) — pehle **laptop/PC par unzip** kar lo. (GitHub par folder upload phone se mushkil hota hai — **pehli setup ek baar PC/laptop se** karo, uske baad sab kuch phone se chalega.)

---

## STEP 1 — Naya repo banao
1. Browser me kholo: **github.com/new**
2. **Repository name:** `ms-gold-algo`
3. **Private** select karo (🔒 zaroori — bahut private data hai)
4. "Add a README file" ko **chhoda hua** rakho (tick mat karo)
5. **Create repository** dabao

## STEP 2 — Files upload karo
1. Naye repo me **"uploading an existing file"** link dabao (ya Add file → Upload files)
2. Unzipped folder ke **andar ke saare files/folders select karo** aur drag-and-drop karo
   - ⚠️ **`.github` folder bhi upload hona chahiye** (isame daily automatic run ka setup hai). Ye folder PC par hidden ho sakta hai — View → Hidden items on karo.
3. Neeche **Commit changes** dabao. (Upload me 1–2 minute lagenge.)

## STEP 3 — Secrets daalo (3 minute) ⚠️ yahi asli step hai
Repo me: **Settings → Secrets and variables → Actions → New repository secret**

Teen secret banao (naam bilkul waise hi likho):

| Name | Value (aapki private details — `GITHUB_SETUP_BUY_SIDE.md` me di hui hain) |
|---|---|
| `TELEGRAM_BOT_TOKEN` | (alag file me) |
| `TELEGRAM_CHAT_ID` | (alag file me) |
| `NTFY_TOPIC` | dono topic comma se: `topic1,topic2` |

*(Optional) WhatsApp chahiye to `WHATSAPP_PHONE` + `WHATSAPP_APIKEY` bhi add kar sakte ho — CallMeBot free hai par unofficial.*

> 🔒 Ye values kabhi kisi file me ya chat me na likhna. Sirf GitHub Secrets me.

## STEP 4 — Chalao aur test karo
1. Repo me **Actions** tab kholo
2. Green button: **"I understand my workflows, go ahead and enable them"** dabao
3. Left me **"MS Gold Algo — daily signal"** select karo
4. Right me **Run workflow ▾ → Run workflow** dabao
5. 1–2 minute baad: Telegram/ntfy par **aaj ka action sheet** aa jayega ✅
   - Message ki pehli line: **"ABHI KYA KARNA HAI"**

---

## 🔁 Roz ka flow (sirf phone se)

| Kab | Kya |
|---|---|
| Subah ~8:30 (automatic) | Message aata hai: naya signal hai ya nahi, entry/target/stop, RED ZONE warning |
| Signal ho to | Dhan app me **1 lot GOLDPETAL** order lagao (target + stop bhi lagao) |
| Order lagne ke baad | GitHub app → Actions → **MS Gold Algo** → Run workflow → `cmd` box me likho: **`fill 1 13975`** (apna asli price) → Run |
| Bechte waqt | Wahi tarika: Run workflow → **`close 1 14100`** |
| Order nahi lagaya | **`skip 1`** |
| Kai command ek saath | `fill 1 13975 \| close 2 14100` (beech me `\|`) |
| Kabhi bhi status | Run workflow → `cmd` khaali chhod do (roz ka normal sheet aata hai) |

`1` = order ka ID jo message me aata hai (jaise "order #1").

---

## 🧠 Kya yaad rakhna hai
- Algo **long-only** hai (buy side). Short band hai (backtest me −ve).
- **Silver signals** message me aate hain, par **trade nahi** karna — SILVERMIC ka margin ~₹19,082 hai, aapke cash se bahar.
- **Quick-book (V5)**: din-10 par profit **+2.5% yaa zyada** ho to book kar do (2.5%+ lock).
- SKIP band: open ref se **+0.5% se +1% ke beech ka gap** ya **+2.5%+ gap** ho to us din entry skip — algo khud "skip" likh dega.
- 1 lot = 1 gram (GOLDPETAL). Margin ~₹1,352/lot, max 4 open.
- GitHub Actions free minutes: private repo me 2,000 min/month milte hain — hamare runs ~100 min/month lete hain, so free.
- Cron me 5–30 minute ki delay ho sakti hai. Isliye 3 automatic run (03:00 / 08:30 / 00:30 IST) + aapka manual button hai.

---

## 🆘 Kuch galat lage to
- Message me **"RED ZONE"** likha ho → us din trade mat karo, pehle health theek karo.
- "koi alert channel configured nahi" aaye → Step 3 ke secrets dobara check karo.
- Actions me run **fail** dikhe → run kholo → error line copy karke mujhe bhejo, main theek kar dunga.

---
*(V5 book: 11 gold systems, 3.0 trades/month, 75.5% win, target 2.5-4%, avg +1.16%/trade)*

---

## 🎨 Message kaisa aayega (dono channel — Telegram + ntfy)

**1) Jab trade ho:**
```
🎯 MS GOLD ALGO · 16 Oct (Fri) · 08:30 IST
👉 ABHI KYA KARNA HAI
   🟢 AAJ 2 TRADE HAI — MCX open (9:00-9:15 AM) par lagao

🟢 TRADE #1 · G-r5_deep
   📖 5 din me gold 6% gira (washout) — win 89%, avg +1.84% per trade
   🛒 Dhan app me: BUY 1 lot GOLDPETAL NOV FUT (exp 2026-11-30) · NRML
   Entry ₹13,976 | TARGET ₹14,395 (+3%) | SL ₹12,858 (−8% SL-M)
   🧾 Super Order me entry + target + SL ek saath
   💰 Jeet: +₹419 | Haar: −₹1,118 (1 lot = 1 g)
   ⚠️ SKIP agar open ₹14,046–₹14,116 ke beech ya ₹14,326 se upar
   ⏱ max 4 din

📊 AAPKA BOOK: 11 systems · ~3 trades/month · win 75.5% · avg +1.16%/trade
   → ₹371/month (₹6,380 par = 5.8%/month) · per trade ₹123
🩺 SEHAT: 🟢 sab theek
```
**2) Jab trade nahi ho:** pehli line `✅ KUCH NAHI — aaj free ho.` (baaki report same).
**3) Jab purani position band karni ho:** `🔴 1 POSITION BAND KARNI HAI` + neeche position ka P&L.
**4) Jab algo me problem ho:** `⛔ AAJ KOI TRADE MAT KARO` + RED reason (aur aaye signals khud skip ho jaate hain).

ntfy par yahi message markdown me aata hai, aur notification ke title/tag/priority se pata chal jata hai:
- `🎯 AAJ TRADE HAI` (high priority)
- `✅ Aaj koi trade nahi` (normal)
- `🔴 DHYAN DO — algo problem` (high)

---

## 🧾 Report me kya-kya hota hai (aapka sawaal: "sab include hai na?")

| Cheez | Kahan | Status |
|---|---|---|
| Data fetching | Roz yfinance se gold/silver/DXY/GVZ/USDINR download (GitHub runner par) | ✅ |
| Diagnosis test + message | Deep health check (11 checks: data freshness, price sanity, triggers vs baseline, ledger, cash/margin, channels, clock) + message me sehat section + RED ZONE block | ✅ |
| Win rate | `📊 AAPKA BOOK` line: 75.5% win | ✅ |
| Kitna profit | `₹371/month`, per trade ₹123, capital par ROI 5.8%/month, 2.5%+ wale trades 72% | ✅ |
| Simple steps per strategy | Har TRADE card me: system ka simple naam + kyun trigger hua + Dhan app me kya karna hai + target/SL + jeet/haar ke ₹ | ✅ |
| Visually stunning | Telegram HTML bold/monospace, ntfy markdown + title/tags/priority, emoji sections | ✅ |
| Record | `outputs/algo_sheet.html` (HTML sheet), `data/algo/journal.csv` (band trades), `daily_log.txt` | ✅ |
---

## 📄 Naya: message HTML file me aata hai (16-Oct)

Ab Telegram/ntfy par **plain text nahi**, ek **HTML file** aati hai — wahi content, par design ke saath:
- Telegram me file par **tap** karo → Google/Chrome me khul jaati hai (offline bhi chalti hai).
- Notification me pehli line hi kaam ki hoti hai: “🟢 AAJ 1 TRADE HAI — entry ₹x · target ₹y · SL ₹z”.
- GitHub → Actions → run kholo → **Artifacts** me `ms-gold-message` download bhi kar sakte ho (30 din rehta hai).

Kuch aur set karne ki zaroorat nahi — same 3 secrets, same timings.

---

## ⏱️ Timing + duplicate — naya (rev15)

- **Ab 4 runs hain:** 03:00, **05:30 (naya safety-net)**, 08:30, 00:30 IST — GitHub ke delay se bachne ke liye.
- Same message **do baar nahi** aayega — duplicate guard hai. Zaroorat par Run workflow me **`force: true`** daalo.
- Message kholo → **SEHAT** section me "Run timing" line: scheduled vs actual (delay kitna hua).
- Trade-day par message 9 baje ke baad aaye to banner me khud likha hoga: **abhi ka price dekh ke order lagao**.
