"""
docs/ 아래에 GitHub Pages 로 서빙할 정적 사이트를 만든다.

  python3 src/build_site.py

산출물
  docs/index.html   대시보드 (홈 화면 추가 시 앱처럼 뜨도록 manifest 연결)
  docs/state.json   기계가 읽을 현재 상태 — 워크플로가 신호 변경을 판정할 때 쓴다
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from report import build_payload  # noqa: E402

DOCS = os.path.join(ROOT, "docs")

VALIDATION = [
    ["연평균수익률 CAGR",        "32.9%",   "33.2%",   "±0.3%p"],
    ["최대낙폭 MDD",             "-62%",    "-61.9%",  "일치"],
    ["울서 지수",                "29.9",    "29.9",    "일치"],
    ["소르티노 지수",            "1.08",    "1.17",    "±0.09"],
    ["연평균 매매횟수",          "8.1회",   "7.9회",   "±0.2회"],
    ["매매 0회였던 해",          "5년",     "5년",     "일치"],
    ["최다 매매 연도",           "21회",    "21회",    "일치"],
    ["매매간격 중앙값",          "6일",     "6일",     "일치"],
    ["최장 무매매 기간",         "31개월",  "33개월",  "±2개월"],
    ["QQQ 단순보유 CAGR / MDD",  "15.4% / -82.8%", "15.3% / -82.8%", "일치"],
    ["QLD 단순보유 CAGR / MDD",  "19.7% / -99%",   "19.6% / -98.8%", "일치"],
    ["TQQQ 단순보유 CAGR / MDD", "16.4% / -100%",  "16.3% / -100%",  "일치"],
    ["7년 보유 원금손실확률",    "0%",      "0.2%",    "일치"],
    ["10년 보유 손실확률 (QQQ/QLD/TQQQ)", "8.8 / 21.2 / 40.1%", "9.1 / 21.7 / 40.4%", "일치"],
    ["QLD 대비 승률 (1/3/5/10년)", "59 / 62 / 76 / 78%", "59 / 62 / 76 / 80%", "일치"],
    ["10년 보유 결과 중앙값 (1억 투입)", "12.5억", "12.9억", "±3%"],
    ["10년 보유 최악 (1억 투입)", "1.56억",  "1.62억",  "±4%"],
    ["전고점 회복 QQQ / QLD",    "14.9 / 20.8년", "15.0 / 20.8년", "일치"],
]

CAUTION = (
    "<b>검증 메모.</b> 위 재현은 나스닥100 지수로 가상 QQQ·QLD·TQQQ를 합성해(운용보수·조달금리·"
    "거래비용 반영) 1991년부터 돌린 결과입니다. 영상 수치와 대부분 소수점 단위까지 맞지만, "
    "영상에서 &lsquo;레버리지 축소 55회&rsquo;라 한 항목만 본 재현에서는 142회로 잡힙니다 &mdash; "
    "총 매매횟수(연 7.9회 × 35년 ≒ 283회)는 영상과 같으므로, 55회는 연속된 감속 구간을 하나로 묶어 센 "
    "다른 정의로 보입니다. 또 2026-07-28 낙폭이 -9.45%로 문턱을 살짝 넘겨 한 차례 기어 다운이 잡히는데, "
    "영상(8월 말 촬영)에서는 &lsquo;4개월째 무매매&rsquo;라고 말합니다. 문턱 근처 판정은 이렇게 갈릴 수 있습니다."
    "<br><br>이 값들은 매 실행마다 <code>src/selftest.py</code> 가 다시 계산해 대조합니다. "
    "하나라도 어긋나면 워크플로가 실패하고 메일이 갑니다."
)

HEAD = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="송팀장 트라이팟 규칙 — 250일선·VIX10·52주 낙폭 기반 나스닥100 레버리지 배분 신호판">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#f2f5f4" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0d1416" media="(prefers-color-scheme: dark)">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icon-192.png" sizes="192x192">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="트라이팟">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<style>
html{-webkit-text-size-adjust:100%}
body{margin:0;font:14px system-ui,sans-serif}
img{max-width:100%}
[hidden]{display:none!important}
</style>
"""

MANIFEST = {
    "name": "트라이팟 신호판",
    "short_name": "트라이팟",
    "description": "송팀장 트라이팟 규칙 — 250일선·VIX10·52주 낙폭 신호판",
    "start_url": "./",
    "scope": "./",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": "#f2f5f4",
    "theme_color": "#0d6a60",
    "lang": "ko",
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "icon-512-maskable.png", "sizes": "512x512", "type": "image/png",
         "purpose": "maskable"},
    ],
}


def main():
    preset = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else None
    pay = build_payload(preset)
    pay["validation"] = VALIDATION
    pay["caution"] = CAUTION

    frag = open(os.path.join(ROOT, "src", "template.html")).read()
    body = frag.replace("/*__DATA__*/{}", json.dumps(pay, ensure_ascii=False))
    # 프래그먼트 맨 앞의 <title>/<link>/<style> 는 그대로 head 에 들어가야 한다
    head_end = body.index("<div class=\"wrap\">")
    html = HEAD + body[:head_end] + "</head>\n<body>\n" + body[head_end:] + "\n</body>\n</html>\n"

    os.makedirs(DOCS, exist_ok=True)
    open(os.path.join(DOCS, "index.html"), "w").write(html)
    open(os.path.join(DOCS, "manifest.webmanifest"), "w").write(
        json.dumps(MANIFEST, ensure_ascii=False, indent=1))
    open(os.path.join(DOCS, ".nojekyll"), "w").write("")

    state = {k: pay[k] for k in ("asof", "state", "state_label", "alloc", "alloc_text",
                                "gear", "ndx", "sma", "gap_pct", "vix_ma", "high52",
                                "dd_pct", "changed_today", "prev_state",
                                "prev_alloc_text", "days_since_change", "generated_at")}
    state["last_change"] = pay["last_change"]
    state["params"] = pay["params"]
    open(os.path.join(DOCS, "state.json"), "w").write(
        json.dumps(state, ensure_ascii=False, indent=1))

    print(json.dumps({"ok": True, "asof": pay["asof"], "state": pay["state"],
                      "alloc": pay["alloc_text"], "changed": pay["changed_today"],
                      "html_bytes": len(html)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
