"""
트라이팟 규칙 35년 백테스트 — 영상 공개 수치와 대조 검증용.
NDX 지수로 가상 QQQ / QLD / TQQQ 를 합성(비용·조달금리 반영)한 뒤 규칙을 적용한다.
"""
import math
import json
import sys
from engine import build, gear_of, STATE_LABEL, target_text

TD = 252


def synth_returns(rows, sc):
    """지수 일간수익률 → 가상 ETF 일간수익률(비용 반영)."""
    for i, r in enumerate(rows):
        if i == 0:
            r["ret"] = 0.0
        else:
            r["ret"] = rows[i]["ndx"] / rows[i - 1]["ndx"] - 1.0
        div = sc.get("index_dividend_yield", 0.0) / 100.0 / TD
        fin = ((r["irx"] or 0.0) + sc["financing_spread"]) / 100.0 / TD
        cash = max(((r["irx"] or 0.0) - sc["cash_yield_haircut"]) / 100.0, 0.0) / TD
        r["r"] = {
            "QQQ":  r["ret"] * 1 + 1 * div - sc["expense_qqq"] / 100.0 / TD,
            "QLD":  r["ret"] * 2 + 2 * div - sc["expense_qld"] / 100.0 / TD - 1 * fin,
            "TQQQ": r["ret"] * 3 + 3 * div - sc["expense_tqqq"] / 100.0 / TD - 2 * fin,
            "CASH": cash,
        }
    return rows


def run(rows, cfg, start, end):
    ex, sc = cfg["execution"], cfg["synthetic_costs"]
    lag, tc = ex["lag_days"], ex["trade_cost_bps"] / 10000.0
    synth_returns(rows, sc)

    idx = [i for i, r in enumerate(rows) if start <= r["date"] <= end]
    i0, i1 = idx[0], idx[-1]

    equity, held = 1.0, None
    curve, trades = [], []
    bench = {k: 1.0 for k in ("QQQ", "QLD", "TQQQ")}
    bench_curve = {k: [] for k in bench}

    for i in range(i0, i1 + 1):
        r = rows[i]
        src = rows[i - lag]
        tgt = src["target"]
        if tgt is None:
            continue
        if held != tgt:
            turnover = sum(abs(tgt.get(k, 0) - (held or {}).get(k, 0))
                           for k in set(list(tgt) + list(held or {})))
            equity *= (1 - tc * turnover / 2)
            if held is not None:
                trades.append({"date": r["date"], "from": held, "to": tgt,
                               "from_state": prev_state, "to_state": src["state"]})
            held = tgt
        prev_state = src["state"]
        equity *= (1 + sum(w * r["r"][k] for k, w in held.items()))
        curve.append((r["date"], equity))
        for k in bench:
            bench[k] *= (1 + r["r"][k])
            bench_curve[k].append((r["date"], bench[k]))
    return curve, trades, bench_curve


def stats(curve):
    vals = [v for _, v in curve]
    n = len(vals)
    yrs = n / TD
    cagr = vals[-1] ** (1 / yrs) - 1
    peak, mdd, dds = vals[0], 0.0, []
    for v in vals:
        peak = max(peak, v)
        dd = v / peak - 1
        dds.append(dd)
        mdd = min(mdd, dd)
    rets = [vals[i] / vals[i - 1] - 1 for i in range(1, n)]
    mean = sum(rets) / len(rets)
    downs = [min(x, 0.0) for x in rets]
    dsd = math.sqrt(sum(x * x for x in downs) / len(downs)) * math.sqrt(TD)
    sortino = (mean * TD) / dsd if dsd else float("nan")
    ulcer = math.sqrt(sum((d * 100) ** 2 for d in dds) / len(dds))
    sd = math.sqrt(sum((x - mean) ** 2 for x in rets) / len(rets)) * math.sqrt(TD)
    return {"final": vals[-1], "years": yrs, "cagr": cagr, "mdd": mdd,
            "sortino": sortino, "ulcer": ulcer, "vol": sd,
            "calmar": cagr / abs(mdd) if mdd else float("nan")}


def rolling(curve, years):
    """모든 시작 시점 기준 보유기간별 연평균수익률 분포 + 원금손실확률."""
    n = int(years * TD)
    vals = [v for _, v in curve]
    if len(vals) <= n:
        return None
    rs = [(vals[i + n] / vals[i]) ** (1 / years) - 1 for i in range(len(vals) - n)]
    rs_sorted = sorted(rs)
    loss = sum(1 for x in rs if x < 0) / len(rs)
    return {"n": len(rs), "min": rs_sorted[0], "p10": rs_sorted[len(rs) // 10],
            "median": rs_sorted[len(rs) // 2], "max": rs_sorted[-1], "loss_prob": loss}


def main():
    preset = sys.argv[1] if len(sys.argv) > 1 else None
    cfg, rows = build(preset=preset)
    bt = cfg["backtest"]
    curve, trades, bench = run(rows, cfg, bt["start"], bt["end"])
    s = stats(curve)
    print(f"=== 트라이팟 규칙 백테스트 [{cfg['params']['name']}] "
          f"{curve[0][0]} ~ {curve[-1][0]} ({s['years']:.1f}년) ===\n")
    hdr = f"{'':14}{'CAGR':>9}{'MDD':>9}{'Sortino':>9}{'Ulcer':>8}{'배수':>8}"
    print(hdr)
    print(f"{'트라이팟 규칙':<12}{s['cagr']*100:>8.1f}%{s['mdd']*100:>8.1f}%"
          f"{s['sortino']:>9.2f}{s['ulcer']:>8.1f}{'':>8}")
    for k in ("QQQ", "QLD", "TQQQ"):
        b = stats(bench[k])
        print(f"{k:<14}{b['cagr']*100:>8.1f}%{b['mdd']*100:>8.1f}%"
              f"{b['sortino']:>9.2f}{b['ulcer']:>8.1f}{'':>8}")

    yrs = s["years"]
    print(f"\n매매 횟수 {len(trades)}회 · 연평균 {len(trades)/yrs:.1f}회")
    down = [t for t in trades if gear_of(t["to"]) < gear_of(t["from"])]
    print(f"  기어 다운(레버리지 축소·현금화) {len(down)}회")

    print("\n[보유기간별 연평균수익률 중앙값 / 원금손실확률]")
    print(f"{'기간':<6}{'트라이팟':>20}{'QQQ':>20}{'QLD':>20}{'TQQQ':>20}")
    for y in (1, 3, 5, 7, 10):
        line = f"{str(y)+'년':<6}"
        for c in (curve, bench["QQQ"], bench["QLD"], bench["TQQQ"]):
            rr = rolling(c, y)
            line += f"{rr['median']*100:>12.1f}% /{rr['loss_prob']*100:>5.1f}%" if rr else f"{'-':>20}"
        print(line)

    print("\n[최근 신호 변경 이력]")
    for t in trades[-8:]:
        print(f"  {t['date']}  {STATE_LABEL[t['from_state']]} → {STATE_LABEL[t['to_state']]}"
              f"   {target_text(t['from'])} → {target_text(t['to'])}")

    json.dump({"stats": s, "trades": len(trades), "gear_down": len(down)},
              open("backtest_summary.json", "w"), indent=1)


if __name__ == "__main__":
    main()
