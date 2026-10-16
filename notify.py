#!/usr/bin/env python3
"""Message bhejne ka module — Telegram / ntfy / WhatsApp (CallMeBot). Sirf standard library.

Visual (16-Oct upgrade):
  • Telegram -> HTML (bold headings, <code> numbers) + auto-fallback plain text agar HTML reject ho
  • ntfy     -> Markdown (bold) + Title + Tags + Priority  (signal day = high priority 🎯)
  • Dono channel ke message byte-safe chunks me tootenge (ntfy limit 4096 bytes)

Env vars (GitHub repo ke Secrets me):
  TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
  NTFY_TOPIC        (ek ya comma se kai: "topic1,topic2")
  WHATSAPP_PHONE (+91...) + WHATSAPP_APIKEY   <- CallMeBot (unofficial)
  NOTIFY_CHANNEL    telegram | ntfy | whatsapp | none   (khaali = jo configured hain sab)
  DRY_RUN=1         -> sirf print, bhejo mat
"""
import os, json, urllib.request, urllib.parse, urllib.error

TG_MAX = 3900          # Telegram limit 4096 chars (safety margin)
NTFY_MAX = 3800        # ntfy limit 4096 BYTES


def _chunks_by_len(text, limit):
    if len(text) <= limit:
        return [text]
    out, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:                    # ek hi line bahut lambi ho to todo
            if cur:
                out.append(cur); cur = ""
            out.append(line[:limit]); line = line[limit:]
        if len(cur) + len(line) + 1 > limit:
            out.append(cur); cur = ""
        cur += line + "\n"
    if cur.strip():
        out.append(cur)
    return out


def _chunks_by_bytes(text, limit):
    if len(text.encode("utf-8")) <= limit:
        return [text]
    out, cur = [], ""
    for line in text.split("\n"):
        if len((cur + line + "\n").encode("utf-8")) > limit:
            if cur:
                out.append(cur); cur = ""
            while len(line.encode("utf-8")) > limit:    # single long line
                cut = limit // 2
                out.append(line[:cut]); line = line[cut:]
        cur += line + "\n"
    if cur.strip():
        out.append(cur)
    return out


def _post(url, data=None, headers=None, method="POST"):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.read().decode("utf-8", "ignore")[:400]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")[:400]
    except Exception as e:
        return 0, str(e)[:200]


def _telegram(text, html=None):
    tok = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not tok or not chat:
        return "telegram: skip (secret nahi hai)"
    url = f"https://api.telegram.org/bot{tok}/sendMessage"
    ok = tot = 0
    notes = ""
    for mode in ("html", "plain"):
        if mode == "html" and not html:
            continue
        body_text = html if mode == "html" else text
        parts = _chunks_by_len(body_text, TG_MAX)
        ok, tot, notes = 0, len(parts), ""
        for i, p in enumerate(parts, 1):
            payload = {"chat_id": chat, "text": p, "disable_web_page_preview": True}
            if mode == "html":
                payload["parse_mode"] = "HTML"
            st, resp = _post(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
            if st == 200:
                ok += 1
            else:
                notes = f"HTTP {st} {resp[:120]}"
                break
        if ok == tot:
            return f"telegram: {ok}/{tot} bheje" + (" (plain fallback)" if (mode == "plain" and html) else "")
        if mode == "plain" or not html:
            break
    return f"telegram: {ok}/{tot} FAIL{(' — ' + notes) if notes else ''}"


def _ntfy(text, md=None):
    """ntfy JSON publish (emoji/Unicode safe + markdown + priority + tags)."""
    raw = os.getenv("NTFY_TOPIC", "").strip()
    if not raw:
        return "ntfy: skip (secret nahi hai)"
    body_src = md or text
    title = os.getenv("_NTFY_TITLE", "MS Gold Algo")[:250]
    tags = [t.strip() for t in os.getenv("_NTFY_TAGS", "chart_with_upwards_trend").split(",") if t.strip()]
    try:
        prio = int(os.getenv("_NTFY_PRIO", "3") or 3)
    except Exception:
        prio = 3
    res = []
    for topic in [t.strip() for t in raw.split(",") if t.strip()]:
        parts = _chunks_by_bytes(body_src, NTFY_MAX)
        ok = 0
        for i, p in enumerate(parts, 1):
            payload = {"topic": topic, "message": p, "title": title + (f" ({i}/{len(parts)})" if len(parts) > 1 else ""),
                       "tags": tags, "priority": prio, "markdown": True}
            st, resp = _post("https://ntfy.sh/", json.dumps(payload).encode("utf-8"),
                             {"Content-Type": "application/json"})
            ok += 1 if st == 200 else 0
            if st != 200:
                res.append(f"{topic}:HTTP {st} {resp[:70]}")
                break
        if ok == len(parts):
            res.append(f"{topic}:✅ {ok}/{len(parts)}")
    return "ntfy: " + " ".join(res)


def _whatsapp(text):
    ph = os.getenv("WHATSAPP_PHONE", "").strip()
    key = os.getenv("WHATSAPP_APIKEY", "").strip()
    if not ph or not key:
        return "whatsapp: skip (secret nahi hai)"
    q = urllib.parse.urlencode({"phone": ph, "text": text, "apikey": key})
    st, resp = _post("https://api.callmebot.com/whatsapp.php?" + q, None, {}, "GET")
    return f"whatsapp(callmebot): HTTP {st}"


def send(text, html=None, md=None, title=None, tags=None, priority=None):
    """Sab configured channels par bhejo; DRY_RUN=1 par sirf print.

    text = plain (WhatsApp / fallback) · html = Telegram version · md = ntfy version (markdown)
    title/tags/priority = ntfy notification ke liye (priority: 3 normal, 4 high, 5 max)
    """
    print("\n===== MESSAGE (plain) =====\n" + text + "\n===========================")
    if os.getenv("DRY_RUN") == "1":
        print("[DRY_RUN] message bheja nahi gaya")
        return ["dry-run"]
    env_bak = {k: os.environ.get(k) for k in ("_NTFY_TITLE", "_NTFY_TAGS", "_NTFY_PRIO")}
    if title:
        os.environ["_NTFY_TITLE"] = str(title)
    if tags:
        os.environ["_NTFY_TAGS"] = str(tags)
    if priority:
        os.environ["_NTFY_PRIO"] = str(priority)
    ch = os.getenv("NOTIFY_CHANNEL", "").strip().lower()
    fns = {"telegram": lambda: _telegram(text, html), "ntfy": lambda: _ntfy(text, md), "whatsapp": lambda: _whatsapp(text)}
    todo = [fns[ch]] if ch in fns else list(fns.values())
    res = []
    for fn in todo:
        try:
            res.append(fn())
        except Exception as e:
            res.append(f"ERROR {str(e)[:120]}")
    for k, v in env_bak.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    print("[notify]", " | ".join(res))
    return res


if __name__ == "__main__":
    send("Test message — MS Gold Algo ✅ (agar ye aapke phone par aaya, to sab set hai)")
