# 🔴 Live Monitor — MCX hours me har ghante check

**Kaam kya karta hai:** jab MCX khula ho (Mon–Fri, 9:00 AM – 11:30 PM IST), GitHub khud har ghante algo chalata hai
aur **sirf tab message bhejta hai jab kuch karne layak ho**. Kuch nahi hua to **koi message nahi** (spam nahi).

## Kab message aata hai (6 alert)

| Alert | Matlab | Aapko kya karna hai |
|---|---|---|
| ⏰ **ENTRY ZONE** | pending order ka ref price aa gaya | Dhan app → Super Order lagao → `fill 1 <price>` |
| 🚫 **HARD SKIP** | price gap zone se upar chala gaya | Aaj ye trade chhod do (enter nahi) |
| 🎯 **TARGET HIT** | open position ka target chhu gaya | Bech do → `close 7 <price>` |
| 🛑 **STOP HIT** | stop loss tak aa gaya | SL-M lag chuki hai → `close 7 <price>` |
| 💚 **QUICK-BOOK** | din-10+ aur abhi +2.5% | Book kar sakte ho → `close 8 <price>` |
| ⏳ **SETUP BAN RAHA** | bar ke andar setup trigger ho gaya | ⚠️ ADHOORA hai — **order mat lagao**, confirm hone do |

## Safety rules

- **RED ZONE** me koi alert nahi (naye signal band rehte hain).
- **Ek din me ek alert ek hi baar** — dedup state `data/algo/monitor_state.json`.
- **Bhejna fail hua to** agle ghante dobara koshish hoti hai (alert jal nahi jata).
- **Adhoora setup (⏳) = order NAHI** — final signal raat ~2:30 AM IST ke run me aata hai.
- Live price COMEX (GC=F) se INR/g me convert hota hai: `usdinr × (1+duty) × (1+tax) / 31.1035 × $`.
  Data 120 minute se purana ho to alert band (galat price par alert se better hai chup rehna).

## Timing

- **15 hourly crons:** 09:00, 10:00, 11:00 … 23:00 IST (Mon–Fri).
- **4 daily crons** waise hi chalte rehte hain: 03:00 / 05:30 / 08:30 / 00:30 IST — unme poora daily report aata hai.
- Manually test: Actions → **Run workflow** → `mode = monitor` → Run. (default `daily` hi rehta hai.)

## Files

- `monitor.py` — collect logic (price, orders, positions, provisional setups, dedup)
- `report_html.py` → `build_alert_html()` — alert ka HTML file
- `run_daily.py` → `MS_MODE=monitor` — sirf alert bhejta hai, daily state ko chhedta nahi
- Test hook: `MS_IGNORE_MKT_HOURS=1` (sirf local testing ke liye)
