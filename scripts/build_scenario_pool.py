"""A small sample of the REAL held-out ULB non-fraud transactions (3,000 rows: 1,500 with amounts 20 to 400, 1,500 with amounts 400 to 3,000) used by the interception demo when the full
dataset is not available, for example inside the deployed container. Writes data/processed/scenario_pool.parquet. The licence terms of the ULB data are not confirmed: do not publish this file
or an image that contains it until they are. Usage: python scripts/build_scenario_pool.py"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
from safepay_ml.data import load_ulb, temporal_split

frame = temporal_split(load_ulb())["test"].frame
frame = frame[frame["Class"] == 0].reset_index(drop=False)               # keeps the original row number in the "index" column
parts = [frame[(frame["Amount"] >= lo) & (frame["Amount"] < hi)].sample(1500, random_state=0) for lo, hi in ((20, 400), (400, 3000))]
import pandas as pd
pool = pd.concat(parts).sort_values("index")[["index", "Amount", "Class"] + [f"V{i}" for i in range(1, 29)]]
out = ROOT / "data" / "processed" / "scenario_pool.parquet"
pool.to_parquet(out, index=False)
print(f"{len(pool)} rows -> {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")
