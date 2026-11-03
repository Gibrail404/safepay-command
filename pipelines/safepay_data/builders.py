from __future__ import annotations
import io, zipfile
import pandas as pd
from scipy.io import arff
from .registry import Dataset, load_registry
from .fetch import fetch
from .manifest import write_processed, check_expected


def parse_ulb(path) -> pd.DataFrame:
    data, _ = arff.loadarff(str(path))
    df = pd.DataFrame(data)
    df["Class"] = df["Class"].map(lambda v: int(v.decode() if isinstance(v, bytes) else v)).astype("int8")
    return df


def build_ulb(ds: Dataset) -> dict:
    df = parse_ulb(fetch(ds))
    check_expected(ds, {"rows": len(df), "positives": int(df["Class"].sum())})
    stats = {"positives": int(df["Class"].sum()), "fraud_rate": float(df["Class"].mean()), "time_seconds_min": float(df["Time"].min()), "time_seconds_max": float(df["Time"].max()),
             "amount_min": float(df["Amount"].min()), "amount_median": float(df["Amount"].median()), "amount_max": float(df["Amount"].max())}
    return write_processed(ds, df, stats)


def parse_sms(zip_path) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as z:
        raw = z.read("SMSSpamCollection").decode("utf-8", errors="replace")
    rows = [line.split("\t", 1) for line in raw.splitlines() if "\t" in line]
    df = pd.DataFrame(rows, columns=["label", "text"])
    df["is_spam"] = (df["label"] == "spam").astype("int8")
    return df


def build_sms(ds: Dataset) -> dict:
    df = parse_sms(fetch(ds, "sms_spam_collection.zip"))
    check_expected(ds, {"rows": len(df)})
    return write_processed(ds, df, {"spam": int(df["is_spam"].sum()), "ham": int((1 - df["is_spam"]).sum()), "median_chars": float(df["text"].str.len().median())})


SDN_COLUMNS = ["ent_num", "name", "sdn_type", "program", "title", "call_sign", "vess_type", "tonnage", "grt", "vess_flag", "vess_owner", "remarks"]


def parse_sdn(path) -> pd.DataFrame:
    df = pd.read_csv(path, header=None, names=SDN_COLUMNS, dtype=str, keep_default_na=False, encoding="latin-1")
    for c in df.columns:
        df[c] = df[c].str.strip().replace("-0-", "")
    return df


def build_ofac(ds: Dataset) -> dict:
    df = parse_sdn(fetch(ds, "SDN.CSV", force=True))   # the list changes, always take a fresh copy and record its hash
    if len(df) < 1000 or df["name"].eq("").mean() > 0.01:
        raise ValueError("ofac_sdn: file does not look like the SDN list")
    return write_processed(ds, df, {"types": df["sdn_type"].replace("", "entity").value_counts().to_dict(), "distinct_programs": int(df["program"].nunique())})


BUILDERS = {"ulb_creditcard": build_ulb, "sms_spam": build_sms, "ofac_sdn": build_ofac}


def build(name: str) -> dict:
    reg = load_registry()
    if name not in BUILDERS:
        raise SystemExit(f"no builder yet for {name}; available: {', '.join(BUILDERS)}")
    return BUILDERS[name](reg[name])
