# ✅ GITHUB LIVE — MS GOLD ALGO (16-Oct-2026)

## 🟢 Status: POORA AUTOMATION LIVE HAI

| Cheez | Status |
|---|---|
| **Repo** | `github.com/abhayv7272/ms-gold-algo` (main branch) |
| **Project push** | ✅ **rev16** — monitor.py + build_alert_html + hourly crons + docs/LIVE_MONITOR.md (43+ files) |
| **Secrets** | ✅ 3 set: TELEGRAM_BOT_TOKEN · TELEGRAM_CHAT_ID · NTFY_TOPIC (updated 00:42 UTC) |
| **Workflow** | ✅ `MS Gold Algo — daily signal` · state = **active** |
| **Run #1** | ✅ SUCCESS (workflow_dispatch force=true) — 12/12 steps pass |
| **Message delivery** | ✅ ntfy dono topics par (00:42:28 IST) text + **HTML attach** (`MS_Gold_Algo_2026-10-16_0612.html`) |
| **State auto-commit** | ✅ workflow ne khud commit kiya: `state(after): 2026-10-16 00:42 UTC` |
| **Duplicate guard LIVE** | ✅ Run #2 (force=false) chala par **naya message NAHI bheja** (last_sent.json same) |
| **Monitor LIVE (16-Oct)** | ✅ run #4/#5 monitor chup rahe (koi spam nahi) · demo alert TG+ntfy HTML ✅ |

## ⏰ Ab kya hota hai (kuch nahi karna)

4 automatic runs (IST):
| Run | Time | Kaam |
|---|---|---|
| 1 | **03:00** | Raat ka main scan (COMEX band hone ke baad) |
| 2 | **05:30** | Safety-net (agar #1 delay/fail ho) |
| 3 | **08:30** | Subah ka final — MCX 9:00 open se pehle |
| 4 | **00:30** | Raat ka summary + aapki commands |

Har run: data fetch → 21 triggers → RED ZONE check → **HTML message Telegram + ntfy**.
Same haalat me dobara message **nahi** aata (duplicate guard).

## 📲 Aapka kaam (sirf 3 command)

| Kab | Kya | Kahan |
|---|---|---|
| Signal aaye + order laga liya | `fill 1 13980` (1 = order no., 13980 = aapka fill price) | GitHub → **Actions** → *MS Gold Algo* → **Run workflow** → cmd box |
| Position bech di | `close 1 14100` | wahi |
| Order nahi lagaya (gap kharab) | `skip 1` | wahi |
| Jaan-boojh kar message dobara chahiye | `force` = **true** | wahi |

Kai commands ek saath: `fill 1 13980 | fill 2 13960` (| se alag).

## ⚠️ AAPKE 2 KAAM (baaki kuch nahi)

1. **Repo PRIVATE karo** (abhi public hai — signals sabko dikh rahe hain):
   GitHub → repo → **Settings** → neeche **Danger Zone** → **Change repository visibility** → **Make private** → naam type karke confirm.
   *(Mere token me Administration permission nahi thi, isliye main nahi kar saka.)*

2. **14-Nov-2026**: token expire hoga. Us din naya fine-grained token banao (same settings) —
   mujhe do, main phir se sab sambhal lunga. (Ya repo Settings → Secrets se khud bhi badal sakte ho.)

## 🔐 Security note
- Token: sirf is ek repo ka access, 30-din expiry, permissions = Contents + Actions + Workflows + Secrets.
- Token **workspace snapshot me save nahi** hota (`.cache` excluded) — sirf is session me hai.
- Secrets GitHub me **encrypted** hain (libsodium sealed box) — main wapas padh nahi sakta, sirf naam dekh sakta hoon.
- Kabhi share MAT karna: Dhan API secret / TOTP / PIN / netbanking password.

## 🧪 Verification commands (kabhi bhi khud check karo)
```
GitHub → Actions → MS Gold Algo → Run workflow → cmd box me:
   (khaali chhodo)  -> normal run
   force = true     -> message zabardasti bhejo
```
Repo me `e2e_verify.py` hai — Actions run ke logs me ya locally: `python3 e2e_verify.py` (34 checks).

## 📌 Agli baar ke liye
- Main GitHub se **directly** kaam kar sakta hoon (push/fix/test) — jab chaaho bolo "github se ye change karo".
- Pending ideas: WhatsApp CallMeBot keys, silver trade (margin ₹19k se bahar), Stage-2 auto order placement (static IP + Dhan order API).

## 🔴 Live Monitor — hourly MCX alert (LIVE)

| Cheez | Detail |
|---|---|
| Kab check | Mon–Fri **09:00–23:00 IST** (15 hourly crons) |
| Kya aata hai | ⏰ entry zone · 🚫 hard skip · 🎯 target · 🛑 stop · 💚 quick-book · ⏳ adhoora setup |
| Kya bhejta hai | Telegram + ntfy dono par **HTML file** |
| Spam? | Nahi — 1 din me 1 alert ek hi baar (`monitor_state.json`) |
| Fallback | Delivery fail ho to agle ghante dobara try (alert jal nahi jata) |
| Daily reports | 4 purane crons waise hi (03:00 / 05:30 / 08:30 / 00:30 IST) |
| Manual test | Actions → Run workflow → `mode = monitor` (khaali chhodne par `daily`) |
