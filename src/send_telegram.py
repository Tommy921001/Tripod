import json, os, urllib.request, urllib.parse

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

with open("docs/state.json", encoding="utf-8") as f:
    s = json.load(f)

lines = [
    f"📊 트라이팟 · {s['asof']}",
    f"상태: {s['state_label']}",
    f"포지션: {s['alloc_text']} ({s['gear']:.1f}배)",
    "",
    f"250일선 이격: {s['gap_pct']:+.2f}%",
    f"VIX 10일 평균: {s['vix_ma']:.2f}",
    f"52주 낙폭: {s['dd_pct']:+.2f}%",
]
if s.get("changed_today"):
    lines.insert(1, f"⚠️ 오늘 신호 변경됨: {s['prev_alloc_text']} → {s['alloc_text']}")

text = "\n".join(lines)
url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
urllib.request.urlopen(url, data=data)
