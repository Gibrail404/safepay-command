import time
import numpy as np


def latency_ms(fn, x, n=500):
    """Time single-row scoring: warm up, then n calls, report the median and the 95th percentile in milliseconds."""
    for _ in range(20):
        fn(x)
    t = []
    for _ in range(n):
        s = time.perf_counter()
        fn(x)
        t.append((time.perf_counter() - s) * 1000)
    return {"p50_ms": float(np.percentile(t, 50)), "p95_ms": float(np.percentile(t, 95))}
