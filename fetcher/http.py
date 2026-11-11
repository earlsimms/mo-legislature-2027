"""Polite HTTP helper: curl_cffi browser impersonation, retries, small worker pool."""
import time
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests as creq

UA = "MissouriStrategies-BillTracker/1.0 (+public data; hourly)"
_sess = None


def session():
    global _sess
    if _sess is None:
        _sess = creq.Session(impersonate="chrome")
    return _sess


def get(url, tries=3, timeout=40, binary=False):
    last = None
    for i in range(tries):
        try:
            r = session().get(url, timeout=timeout)
            if r.status_code == 200:
                return r.content if binary else r.text
            last = f"HTTP {r.status_code}"
            if r.status_code in (403, 404):
                break
        except Exception as e:  # network hiccup
            last = str(e)
        time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def pmap(fn, items, workers=6):
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(fn, items))
