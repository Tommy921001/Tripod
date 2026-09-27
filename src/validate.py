"""영상에서 공개된 개별 수치들과 1:1 대조 검증."""
from engine import build, gear_of
from backtest import run, stats, rolling, TD

cfg, rows = build()
bt = cfg["backtest"]
curve, trades, bench = run(rows, cfg, bt["start"], bt["end"])
D = {d: i for i, (d, v) in enumerate(curve)}
V = [v for _, v in curve]
B = {k: [v for _, v in bench[k]] for k in bench}

def near(d):
    ks = [x for x in D if x >= d]
    return D[min(ks)]

def seg(d0, d1, series=None):
    a, b = near(d0), near(d1)
    s = series or V
    return s[b] / s[a]

print("● 닷컴 고점 진입: 2000-03 에 1억, 3년 뒤")
for name, s in [("규칙", V), ("QQQ", B["QQQ"]), ("QLD", B["QLD"]), ("TQQQ", B["TQQQ"])]:
    print(f"   {name:<5} {seg('20000301','20030301',s)*10000:>10,.0f}만원")
print("   (영상: 규칙 6,437 / QQQ 2,400 / QLD 229 / TQQQ 10)")

print("\n● 규칙이 이겼던 3구간 (1억 투입 → 종료시점 평가액)")
for lbl, a, b in [("2000-04~2003-05", "20000401", "20030531"),
                  ("2008 금융위기",   "20080101", "20090630"),
                  ("2022",            "20220101", "20221231")]:
    print(f"   {lbl:<16} 규칙 {seg(a,b)*10000:>9,.0f}만원 | TQQQ {seg(a,b,B['TQQQ'])*10000:>9,.0f}만원")
print("   (영상: 9,749 vs 22 / 10,956 vs 395 / 10,137 vs 반토막)")

print("\n● 10년 보유 결과 분포 (1억 투입, 월 단위 진입시점 전부)")
months, seen = [], set()
for i, (d, v) in enumerate(curve):
    if d[:6] not in seen:
        seen.add(d[:6]); months.append(i)
res = sorted(V[i+10*TD]/V[i] for i in months if i+10*TD < len(V))
n = len(res)
print(f"   시뮬레이션 {n}개 시점 (영상: 307개)")
print(f"   최악 {res[0]*10000:,.0f}만 | 하위10% {res[n//10]*10000:,.0f}만 | "
      f"중앙 {res[n//2]*10000:,.0f}만 | 최고 {res[-1]*10000:,.0f}만")
print("   (영상: 최악 1억5,600 / 하위 4억7,300 / 중앙 12억5,000 / 최고 141억)")
for k in ("QQQ","QLD","TQQQ"):
    r = sorted(B[k][i+10*TD]/B[k][i] for i in months if i+10*TD < len(V))
    print(f"   같은 기간 {k} 최악 {r[0]*10000:,.0f}만원")
print("   (영상: QQQ 4,600만 / QLD 400만 / TQQQ 0)")

print("\n● QLD 단순보유 대비 승률 (같은 날 시작·같은 날 종료)")
for y in (1,3,5,10):
    n_ = y*TD
    w = [1 for i in range(len(V)-n_) if V[i+n_]/V[i] > B["QLD"][i+n_]/B["QLD"][i]]
    print(f"   {y:>2}년: {len(w)/(len(V)-n_)*100:>5.1f}%")
print("   (영상: 1년 59% / 3년 62% / 5년 76% / 10년 78%)")

print("\n● 전고점 회복 소요기간 (단순보유)")
for k in ("QQQ","QLD","TQQQ"):
    s = B[k]; peak = s[0]; pi = 0; worst = 0; ongoing = False
    for i, v in enumerate(s):
        if v >= peak: peak = v; pi = i
        else: worst = max(worst, i-pi)
    print(f"   {k}: 최장 {worst/TD:.1f}년" + ("  (현재 미회복)" if s[-1] < peak else ""))
print("   (영상: QQQ 14.9년 / QLD 20.8년 / TQQQ 미회복)")

print("\n● 매매 빈도 상세")
yrs_all = {}
for t in trades: yrs_all[t["date"][:4]] = yrs_all.get(t["date"][:4],0)+1
allyrs = sorted({r["date"][:4] for r in rows if bt["start"] <= r["date"] <= bt["end"]})
zero = [y for y in allyrs if yrs_all.get(y,0)==0]
gaps = []
ds = [t["date"] for t in trades]
import datetime
dt = lambda s: datetime.date(int(s[:4]),int(s[4:6]),int(s[6:]))
for a,b in zip(ds, ds[1:]): gaps.append((dt(b)-dt(a)).days)
gaps_sorted = sorted(gaps)
print(f"   매매 0회인 해: {len(zero)}년 {zero}   (영상: 5년)")
print(f"   최장 무매매 간격: {max(gaps)/30.4:.1f}개월   (영상: 2년 7개월 = 31개월)")
print(f"   최다 매매 연도: {max(yrs_all.values())}회   (영상: 21회)")
print(f"   매매간격 중앙값 {gaps_sorted[len(gaps)//2]}일 · 평균 {sum(gaps)/len(gaps):.0f}일  (영상: 중앙 6일 · 평균 45일)")
