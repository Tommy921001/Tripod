"""
트라이팟(Tripod) 규칙 엔진
- 송팀장 채널 '35년 백테스트' 영상(2026-08-31 촬영)에서 공개된 규칙을 그대로 구현.
- 매 거래일 종가로 3개 지표를 계산 → 시장상태 판정 → 목표배분 결정.
- 실제 체결은 다음 거래일(종가 기준)로 가정.

지표 3개(= 트라이팟)
  1) NDX 250일 단순이동평균  → 큰 방향(추세)
  2) VIX 10일 평균           → 공포
  3) 52주 고점 대비 낙폭      → 피로도
"""
import json
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

STATE_LABEL = {
    "UP_RISKON":  "상승 · 위험선호",
    "UP_RISKOFF": "상승 · 위험회피",
    "DOWN_CALM":  "하락 · 안정",
    "DOWN_FEAR":  "하락 · 공포",
}
GEAR = {"TQQQ": 3.0, "QLD": 2.0, "QQQ": 1.0, "CASH": 0.0}


def load_config(path=None, preset=None):
    cfg = json.load(open(path or os.path.join(ROOT, "config.json")))
    name = preset or cfg["active_preset"]
    p = dict(cfg["presets"][name])
    p["name"] = name
    cfg["params"] = p
    return cfg


def load_market(path=None):
    """date(YYYYMMDD 오름차순), ndx, vix, irx"""
    path = path or os.path.join(ROOT, "data", "market.csv")
    out = []
    for r in csv.DictReader(open(path)):
        out.append({
            "date": r["date"],
            "ndx": float(r["ndx"]),
            "vix": float(r["vix"]) if r["vix"] else None,
            "irx": float(r["irx"]) if r["irx"] else None,
        })
    return out


def compute_indicators(rows, p):
    """각 행에 sma / vix_ma / high52 / dd 를 채워 넣는다."""
    n_sma, n_vix, n_dd = p["sma_window"], p["vix_window"], p["dd_window"]
    ndx = [r["ndx"] for r in rows]
    vix = [r["vix"] for r in rows]
    for i, r in enumerate(rows):
        r["sma"] = sum(ndx[i - n_sma + 1:i + 1]) / n_sma if i >= n_sma - 1 else None
        w = [v for v in vix[max(0, i - n_vix + 1):i + 1] if v is not None]
        r["vix_ma"] = sum(w) / len(w) if len(w) == n_vix else None
        if i >= n_dd - 1:
            hi = max(ndx[i - n_dd + 1:i + 1])
            r["high52"] = hi
            r["dd"] = r["ndx"] / hi - 1.0
        else:
            r["high52"] = None
            r["dd"] = None
        r["gap"] = (r["ndx"] / r["sma"] - 1.0) if r["sma"] else None
    return rows


def classify(rows, p):
    """1단계 시장상태(히스테리시스) + 2단계 목표배분."""
    regime = None
    for r in rows:
        if r["gap"] is None:
            r["regime"] = r["state"] = r["target"] = None
            continue
        if r["gap"] > p["band_up"]:
            regime = "UP"
        elif r["gap"] < p["band_down"]:
            regime = "DOWN"
        # 그 사이 구간이면 직전 상태 유지
        if regime is None or r["vix_ma"] is None or r["dd"] is None:
            r["regime"] = regime
            r["state"] = r["target"] = None
            continue
        if regime == "UP":
            risk_on = (r["vix_ma"] < p["vix_up_threshold"]) and (r["dd"] >= p["dd_threshold"])
            state = "UP_RISKON" if risk_on else "UP_RISKOFF"
        else:
            state = "DOWN_CALM" if r["vix_ma"] < p["vix_down_threshold"] else "DOWN_FEAR"
        r["regime"] = regime
        r["state"] = state
        r["target"] = dict(p["alloc"][state])
    return rows


def gear_of(target):
    return sum(GEAR[k] * w for k, w in target.items()) if target else None


def target_text(target):
    if not target:
        return "-"
    order = ["TQQQ", "QLD", "QQQ", "CASH"]
    parts = [f"{k} {int(round(w*100))}%" for k in order if k in target for w in [target[k]]]
    return " + ".join(parts)


def build(config_path=None, market_path=None, preset=None):
    cfg = load_config(config_path, preset)
    rows = load_market(market_path)
    compute_indicators(rows, cfg["params"])
    classify(rows, cfg["params"])
    return cfg, rows


def distance_report(r, p):
    """각 조건까지 얼마나 남았는지 — '타점 임박' 판단용."""
    if r["gap"] is None or r["vix_ma"] is None or r["dd"] is None:
        return {}
    return {
        # 상승 전환까지 지수가 몇 % 더 올라야 하나 (음수면 이미 충족)
        "to_up_band_pct": (p["band_up"] - r["gap"]) * 100,
        # 하락 전환까지 지수가 몇 % 더 빠져야 하나
        "to_down_band_pct": (r["gap"] - p["band_down"]) * 100,
        # VIX10이 상승장 문턱까지 남은 폭
        "vix_to_up_thr": p["vix_up_threshold"] - r["vix_ma"],
        "vix_to_down_thr": p["vix_down_threshold"] - r["vix_ma"],
        # 낙폭 문턱까지 남은 폭(%p)
        "dd_headroom_pp": (r["dd"] - p["dd_threshold"]) * 100,
        # 낙폭 9% 도달까지 지수가 더 빠져야 하는 %
        "px_to_dd_thr_pct": (r["high52"] * (1 + p["dd_threshold"]) / r["ndx"] - 1) * 100,
    }


if __name__ == "__main__":
    cfg, rows = build()
    p = cfg["params"]
    last = rows[-1]
    prev = next(r for r in reversed(rows[:-1]) if r["state"])
    print(f"기준일: {last['date']}  프리셋: {p['name']}")
    print(f"NDX {last['ndx']:,.2f} | 250일선 {last['sma']:,.2f} | 이격 {last['gap']*100:+.2f}%")
    print(f"VIX10 {last['vix_ma']:.2f} | 52주고점 {last['high52']:,.2f} | 낙폭 {last['dd']*100:+.2f}%")
    print(f"시장상태: {STATE_LABEL[last['state']]}  →  {target_text(last['target'])}  ({gear_of(last['target']):.1f}배)")
    print(f"전일 상태: {STATE_LABEL[prev['state']]}  →  변경 {'있음' if prev['state']!=last['state'] else '없음'}")
    for k, v in distance_report(last, p).items():
        print(f"  {k}: {v:+.2f}")
