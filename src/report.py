"""
오늘의 트라이팟 상태를 대시보드용 JSON 으로 출력.
  python3 report.py            → 사람이 읽는 요약
  python3 report.py --json     → 아티팩트 DB 에 넣을 JSON
"""
import json
import sys
import datetime
from engine import build, STATE_LABEL, gear_of, target_text, distance_report

CHART_DAYS = 260
HIST_YEARS = 3


def build_payload(preset=None):
    cfg, rows = build(preset=preset)
    p = cfg["params"]
    live = [r for r in rows if r["state"]]
    cur, prev = live[-1], live[-2]

    # 신호 변경 이력 (상태가 바뀐 날). 체결일 = 신호일 + lag
    lag = cfg["execution"]["lag_days"]
    idx = {r["date"]: i for i, r in enumerate(rows)}
    changes = []
    for a, b in zip(live, live[1:]):
        if a["state"] != b["state"]:
            i = idx[b["date"]]
            fill = rows[min(i + lag - 1, len(rows) - 1)]["date"]
            changes.append({
                "signal_date": b["date"], "fill_date": fill,
                "from": a["state"], "to": b["state"],
                "from_alloc": target_text(a["target"]), "to_alloc": target_text(b["target"]),
                "from_gear": gear_of(a["target"]), "to_gear": gear_of(b["target"]),
            })

    def dparse(s):
        return datetime.date(int(s[:4]), int(s[4:6]), int(s[6:]))

    last_change = changes[-1] if changes else None
    days_since = (dparse(cur["date"]) - dparse(last_change["signal_date"])).days if last_change else None

    chart = [{"d": r["date"], "ndx": round(r["ndx"], 2), "sma": round(r["sma"], 2),
              "vix": round(r["vix_ma"], 2), "dd": round(r["dd"] * 100, 2),
              "st": r["state"]}
             for r in live[-CHART_DAYS:]]

    dist = distance_report(cur, p)
    # '타점 임박' 경보 — 어느 문턱이 가장 가까운가
    watch = []
    if cur["state"] == "UP_RISKON":
        watch.append({"cond": "52주 낙폭 9% 돌파", "unit": "지수",
                      "detail": f"NDX {abs(dist['px_to_dd_thr_pct']):.2f}% 더 하락 시",
                      "prox": max(0.0, 1 - abs(dist["px_to_dd_thr_pct"]) / 10)})
        watch.append({"cond": f"VIX10 {p['vix_up_threshold']:.0f} 돌파", "unit": "VIX",
                      "detail": f"VIX10 {dist['vix_to_up_thr']:.2f}p 상승 시",
                      "prox": max(0.0, 1 - dist["vix_to_up_thr"] / 12)})
    elif cur["state"] == "UP_RISKOFF":
        watch.append({"cond": "TQQQ 복귀(낙폭 9% 이내 + VIX10 28 미만)", "unit": "복합",
                      "detail": f"낙폭 {cur['dd']*100:.2f}% / VIX10 {cur['vix_ma']:.2f}",
                      "prox": 0.5})
        watch.append({"cond": "하락장 전환(250일선 -5%)", "unit": "지수",
                      "detail": f"NDX {dist['to_down_band_pct']:.2f}% 더 하락 시",
                      "prox": max(0.0, 1 - dist["to_down_band_pct"] / 15)})
    else:
        watch.append({"cond": "상승장 복귀(250일선 +1%)", "unit": "지수",
                      "detail": f"NDX {abs(dist['to_up_band_pct']):.2f}% 상승 시",
                      "prox": max(0.0, 1 - abs(dist["to_up_band_pct"]) / 15)})
        watch.append({"cond": f"VIX10 {p['vix_down_threshold']:.0f} 선", "unit": "VIX",
                      "detail": f"VIX10 {cur['vix_ma']:.2f} (문턱 {p['vix_down_threshold']:.0f})",
                      "prox": max(0.0, 1 - abs(dist["vix_to_down_thr"]) / 8)})
    watch.sort(key=lambda x: -x["prox"])

    return {
        "generated_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "preset": {"name": p["name"], "label": p["label"]},
        "params": {k: p[k] for k in ("sma_window", "band_up", "band_down", "vix_window",
                                     "vix_up_threshold", "vix_down_threshold",
                                     "dd_window", "dd_threshold")},
        "asof": cur["date"],
        "ndx": round(cur["ndx"], 2),
        "sma": round(cur["sma"], 2),
        "gap_pct": round(cur["gap"] * 100, 2),
        "vix_ma": round(cur["vix_ma"], 2),
        "vix_last": cur["vix"],
        "high52": round(cur["high52"], 2),
        "dd_pct": round(cur["dd"] * 100, 2),
        "regime": cur["regime"],
        "state": cur["state"],
        "state_label": STATE_LABEL[cur["state"]],
        "alloc": cur["target"],
        "alloc_text": target_text(cur["target"]),
        "gear": gear_of(cur["target"]),
        "changed_today": prev["state"] != cur["state"],
        "prev_state": prev["state"],
        "prev_alloc_text": target_text(prev["target"]),
        "days_since_change": days_since,
        "last_change": last_change,
        "changes": changes[-40:],
        "distance": {k: round(v, 3) for k, v in dist.items()},
        "watch": watch,
        "chart": chart,
    }


if __name__ == "__main__":
    pay = build_payload()
    if "--json" in sys.argv:
        print(json.dumps(pay, ensure_ascii=False))
    else:
        print(f"[{pay['asof']}] {pay['state_label']}  →  {pay['alloc_text']} ({pay['gear']:.1f}배)")
        print(f"  NDX {pay['ndx']:,.2f} / 250일선 {pay['sma']:,.2f} → 이격 {pay['gap_pct']:+.2f}%")
        print(f"  VIX10 {pay['vix_ma']:.2f} (문턱 {pay['params']['vix_up_threshold']:.0f}/{pay['params']['vix_down_threshold']:.0f})")
        print(f"  52주 고점 {pay['high52']:,.2f} → 낙폭 {pay['dd_pct']:+.2f}% (문턱 {pay['params']['dd_threshold']*100:.0f}%)")
        if pay["changed_today"]:
            msg = f"★ 오늘 변경! ({pay['prev_alloc_text']} → {pay['alloc_text']})"
        else:
            msg = f"없음 (마지막 {pay['last_change']['signal_date']}, {pay['days_since_change']}일 전)"
        print(f"  신호 변경: {msg}")
        for w in pay["watch"]:
            print(f"  · {w['cond']}: {w['detail']}")
