"""
시세 수집기 — 외부 패키지 없이 표준 라이브러리만 사용.

GitHub Actions 러너에서 돌아간다는 전제가 설계를 지배한다.
러너 IP 대역은 전 세계가 공유해서 Yahoo 같은 곳이 통째로 429 를 던진다.
그래서 소스를 넉넉히 두고, 각각 재시도하고, 하나라도 살아 있으면 진행한다.

소스 (NDX)
  FRED NASDAQ100 CSV   — 세인트루이스 연준. 러너에서 가장 안정적. 다만 미 동부 밤에 갱신돼
                          당일치는 하루 늦게 들어온다.
  Nasdaq 공식 API      — 장 마감 직후 당일 종가가 바로 올라온다.
  Yahoo chart (q1/q2)  — 재시도를 붙이면 러너에서도 잘 붙는다. 429 는 대개 일시적이다.

  stooq 는 뺐다 — 러너에서 CSV 대신 HTML 을 돌려주는 것을 실측했다(2026-09).
  FRED 도 러너에서 읽기 타임아웃이 잦아 1회만 짧게 시도하는 보조로 내렸다.

소스 (VIX)
  CBOE 원본 미러(raw.githubusercontent) — 러너에서 사실상 항상 된다. 공식 종가라 권위가 있어
                                          과거 값이 어긋나면 이쪽으로 교정한다.
  Yahoo (q1/q2)                        — 보조. 미러가 하루 늦을 때 당일치를 메운다.

실패 원칙
  · NDX 소스가 하나도 안 열리면  → 죽는다(워크플로 실패 → 메일).
  · 소스는 열렸는데 새 거래일이 없으면 → 정상 종료. 휴장일이거나 아직 발표 전이다.
  · 소스끼리 0.5% 넘게 어긋나면 → 죽는다. 조용히 틀린 값을 남기느니 실패하는 게 낫다.

사용법:  python3 src/fetch.py            # data/market.csv 갱신
         python3 src/fetch.py --dry-run  # 저장하지 않고 무엇을 받았는지만 출력
"""
import csv
import datetime
import gzip
import io
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKET = os.path.join(ROOT, "data", "market.csv")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
TIMEOUT = 30
TRIES = 3
# 소스별 (재시도, 타임아웃). 잘 죽는 소스에 시간을 오래 쓰지 않는다 —
# 잡 전체 제한이 10분이라, 느린 소스 하나가 나머지를 잡아먹으면 안 된다.
BUDGET = {"fred": (1, 20), "nasdaq": (3, 30), "yahoo-q1": (2, 20), "yahoo-q2": (2, 20),
          "cboe-mirror": (3, 30)}

MAX_DAILY_MOVE = 0.15      # 지수 하루 변동 한계
MAX_SOURCE_DIFF = 0.005    # 소스 간 허용 오차 0.5%
VIX_RANGE = (1.0, 200.0)


class FetchError(RuntimeError):
    pass


def _get(url, headers=None, tries=TRIES, timeout=TIMEOUT):
    """재시도 + 백오프. gzip 응답도 알아서 푼다."""
    hdr = {"User-Agent": UA, "Accept": "*/*",
           "Accept-Language": "en-US,en;q=0.9", **(headers or {})}
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=hdr)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                return raw.decode("utf-8", "replace")
        except Exception as e:
            last = e
            if i < tries - 1:
                time.sleep(1.5 * (i + 1) + random.random())
    raise last


# ── 소스별 구현 ────────────────────────────────────────────────

def yahoo(symbol, rng="3mo", host="query1"):
    url = (f"https://{host}.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(symbol)}?range={rng}&interval=1d")
    t, to = BUDGET["yahoo-q1" if host == "query1" else "yahoo-q2"]
    return parse_yahoo(_get(url, tries=t, timeout=to), symbol)


def parse_yahoo(text, symbol="?"):
    j = json.loads(text)
    res = (j.get("chart") or {}).get("result")
    if not res:
        raise FetchError(f"yahoo {symbol}: 빈 응답 {str(j)[:200]}")
    ts = res[0]["timestamp"]
    cl = res[0]["indicators"]["quote"][0]["close"]
    out = {}
    for t, c in zip(ts, cl):
        if c is None:
            continue
        out[datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
            .strftime("%Y%m%d")] = float(c)
    if not out:
        raise FetchError(f"yahoo {symbol}: 종가 없음")
    return out


def fred(series="NASDAQ100", days=150):
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days)
    url = ("https://fred.stlouisfed.org/graph/fredgraph.csv"
           f"?id={series}&cosd={start}&coed={end}")
    t, to = BUDGET["fred"]
    return parse_fred(_get(url, tries=t, timeout=to), series)


def parse_fred(text, series="?"):
    lines = text.strip().splitlines()
    if not lines or "," not in lines[0]:
        raise FetchError(f"fred {series}: 예상과 다른 응답 {text[:120]}")
    out = {}
    for r in csv.DictReader(io.StringIO(text)):
        vals = list(r.values())
        if len(vals) < 2:
            continue
        d, v = vals[0], vals[1]
        if v in (".", "", None):
            continue
        out[d.replace("-", "")] = float(v)
    if not out:
        raise FetchError(f"fred {series}: 종가 없음")
    return out


def nasdaq(symbol="NDX", days=120):
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days)
    url = (f"https://api.nasdaq.com/api/quote/{symbol}/historical"
           f"?assetclass=index&fromdate={start}&todate={end}&limit=250")
    t, to = BUDGET["nasdaq"]
    return parse_nasdaq(_get(url, {"Accept": "application/json",
                                   "Referer": "https://www.nasdaq.com/"},
                             tries=t, timeout=to), symbol)


def parse_nasdaq(text, symbol="?"):
    j = json.loads(text)
    tbl = ((j.get("data") or {}).get("tradesTable") or {})
    rows = tbl.get("rows")
    if not rows:
        raise FetchError(f"nasdaq {symbol}: 행 없음 {str(j)[:200]}")
    out = {}
    for r in rows:
        c = (r.get("close") or "").replace(",", "").replace("$", "").strip()
        if not c:
            continue
        m, d, y = r["date"].split("/")
        out[f"{y}{m}{d}"] = float(c)
    if not out:
        raise FetchError(f"nasdaq {symbol}: 종가 없음")
    return out


def stooq(symbol):
    """지금은 소스 목록에서 빠져 있다(러너에서 HTML 을 돌려줌).
    위장 응답을 거르는 이 검사 자체는 자가진단에서 계속 검증한다 —
    나중에 stooq 를 되살릴 때 같은 함정에 다시 빠지지 않도록."""
    url = f"https://stooq.com/q/d/l/?s={urllib.parse.quote(symbol)}&i=d"
    txt = _get(url)
    head = txt.splitlines()[0] if txt.strip() else ""
    if not head.lower().startswith("date,open"):
        # HTTP 200 과 함께 "Access denied" 를 주는 경우가 있다. 조용히 틀릴 소스는 안 쓴다.
        raise FetchError(f"stooq {symbol}: 예상과 다른 응답 {txt[:80]!r}")
    out = {}
    for r in csv.DictReader(io.StringIO(txt)):
        c = r.get("Close")
        if c and c not in ("null", "N/D"):
            out[r["Date"].replace("-", "")] = float(c)
    if not out:
        raise FetchError(f"stooq {symbol}: 종가 없음")
    return out


def cboe_vix_mirror():
    url = "https://raw.githubusercontent.com/datasets/finance-vix/main/data/vix-daily.csv"
    out = {}
    for r in csv.DictReader(io.StringIO(_get(url))):
        if r.get("CLOSE"):
            out[r["DATE"].replace("-", "")] = float(r["CLOSE"])
    if not out:
        raise FetchError("cboe mirror: 종가 없음")
    return out


def gather(sources):
    ok, bad = [], []
    for name, fn in sources:
        try:
            ok.append((name, fn()))
        except Exception as e:
            bad.append({"source": name, "error": f"{type(e).__name__}: {e}"[:180]})
    return ok, bad


def agree(series, date, label):
    """여러 소스의 같은 날짜 값을 대조하고 대표값을 돌려준다."""
    vals = [(n, s[date]) for n, s in series if date in s]
    if not vals:
        return None, []
    base = vals[0][1]
    for n, v in vals[1:]:
        if base and abs(v / base - 1) > MAX_SOURCE_DIFF:
            raise FetchError(
                f"{label} 소스 불일치: " + ", ".join(f"{n2}={v2}" for n2, v2 in vals))
    return base, vals


# ── 메인 ───────────────────────────────────────────────────────

def main():
    dry = "--dry-run" in sys.argv
    rows = list(csv.DictReader(open(MARKET)))
    last = rows[-1]

    ndx_ok, ndx_bad = gather([
        ("fred",     lambda: fred("NASDAQ100")),
        ("nasdaq",   lambda: nasdaq("NDX")),
        ("yahoo-q1", lambda: yahoo("^NDX", host="query1")),
        ("yahoo-q2", lambda: yahoo("^NDX", host="query2")),
    ])
    vix_ok, vix_bad = gather([
        ("cboe-mirror", cboe_vix_mirror),
        ("yahoo-q1",    lambda: yahoo("^VIX", host="query1")),
        ("yahoo-q2",    lambda: yahoo("^VIX", host="query2")),
    ])

    report = {"stored_last": last["date"],
              "ndx_sources_ok": [n for n, _ in ndx_ok],
              "vix_sources_ok": [n for n, _ in vix_ok],
              "sources_failed": ndx_bad + vix_bad,
              "appended": [], "notes": []}

    if not ndx_ok:
        raise FetchError("나스닥100 소스를 하나도 열지 못했습니다 — " + "; ".join(
            f"{b['source']}: {b['error']}" for b in ndx_bad))
    if not vix_ok:
        raise FetchError("VIX 소스를 하나도 열지 못했습니다 — " + "; ".join(
            f"{b['source']}: {b['error']}" for b in vix_bad))

    latest_seen = max(max(s) for _, s in ndx_ok)
    report["latest_available"] = latest_seen

    new_dates = sorted(d for d in set().union(*[set(s) for _, s in ndx_ok])
                       if d > last["date"])

    prev_close = float(last["ndx"])
    for d in new_dates:
        ndx, ndx_vals = agree(ndx_ok, d, f"NDX {d}")
        if ndx is None:
            continue
        try:
            vix, _ = agree(vix_ok, d, f"VIX {d}")
        except FetchError as e:
            report["notes"].append(str(e))
            vix = None

        move = ndx / prev_close - 1
        if abs(move) > MAX_DAILY_MOVE:
            raise FetchError(f"{d} 지수 변동 {move*100:.1f}% — 데이터 오류로 판단하고 중단합니다 "
                             f"(직전 {prev_close}, 수신 {ndx})")
        if vix is not None and not (VIX_RANGE[0] < vix < VIX_RANGE[1]):
            raise FetchError(f"{d} VIX {vix} 범위 이탈")

        rows.append({"date": d, "ndx": f"{ndx:g}",
                     "vix": f"{vix:g}" if vix is not None else "", "irx": ""})
        report["appended"].append({"date": d, "ndx": ndx, "vix": vix,
                                   "sources": [n for n, _ in ndx_vals]})
        prev_close = ndx

    if not new_dates:
        report["notes"].append(
            f"새 거래일 없음 — 소스가 가진 최신일이 {latest_seen}, 저장된 최신일이 {last['date']}. "
            "미국 휴장일이거나 아직 발표 전입니다. 정상 종료합니다.")

    # 비어 있던 VIX 채우기 / 임시값 교정 (CBOE 원본 우선)
    auth = {}
    for name, s in vix_ok:
        if name == "cboe-mirror":
            auth.update(s)
    for _, s in vix_ok:
        for d, v in s.items():
            auth.setdefault(d, v)
    filled = corrected = 0
    for r in rows:
        a = auth.get(r["date"])
        if a is None:
            continue
        a = f"{a:g}"
        if not r.get("vix"):
            r["vix"] = a
            filled += 1
        elif r["vix"] != a and abs(float(r["vix"]) / float(a) - 1) > 1e-9:
            r["vix"] = a
            corrected += 1
    report["vix_filled"] = filled
    report["vix_corrected"] = corrected

    # ── 최근 값 재검증 ────────────────────────────────────────
    # FRED 는 미 동부 밤늦게 갱신돼 이른 실행에서는 하루 뒤처져 있다.
    # 그래서 다음 실행 때 최근 며칠치를 독립 소스와 다시 대조한다.
    # 규칙상 체결이 T+1 이므로, 이 재검증은 그 값으로 실제 매매하기 전에 끝난다.
    recheck = []
    for r in rows[-6:]:
        for name, s in ndx_ok:
            v = s.get(r["date"])
            if v is None:
                continue
            diff = v / float(r["ndx"]) - 1
            if abs(diff) > MAX_SOURCE_DIFF:
                raise FetchError(
                    f"{r['date']} 저장된 지수 {r['ndx']} 와 {name} 의 {v} 가 "
                    f"{diff*100:+.2f}% 어긋납니다 — 사람이 확인해야 합니다")
            if abs(diff) > 1e-9:
                recheck.append({"date": r["date"], "source": name,
                                "stored": float(r["ndx"]), "source_value": v,
                                "diff_pct": round(diff * 100, 4)})
    report["recheck_notes"] = recheck

    if not dry:
        tmp = MARKET + ".tmp"
        with open(tmp, "w") as f:
            f.write("date,ndx,vix,irx\n")
            for r in rows:
                f.write(f"{r['date']},{r['ndx']},{r.get('vix','')},{r.get('irx','')}\n")
        os.replace(tmp, MARKET)
    report["new_last"] = rows[-1]["date"]
    report["rows"] = len(rows)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"::error::시세 수집 실패 — {e}", file=sys.stderr)
        sys.exit(1)
