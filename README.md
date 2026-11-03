# SafePay Command

An AI decision platform for payment risk, sanctions screening and fraud investigation, built in public as a portfolio project. It is independent and is not affiliated with, endorsed by, or built from any company's data or code.

**Status: v0.1, data foundation only.** The product (interception flow, analyst workbench, evaluations) is not built yet. This repo currently holds the master spec and a reproducible data pipeline that runs on real public datasets.

- Master spec: [docs/SPEC.md](docs/SPEC.md)
- Data register, licences and verification log: [docs/DATA.md](docs/DATA.md)

## Principles

1. Real data wherever a public dataset exists. Where none exists (scam conversations), a simulator is used and everything it produces is labelled "simulated".
2. No hand-written product data. Raw files are downloaded by script and verified against a checksum; processed data and its manifest are generated.
3. Every metric is reported with its data source and, once evaluation exists, with confidence intervals.

## Quickstart

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install pandas numpy scipy pyarrow pyyaml pytest
cd pipelines && python -m safepay_data all    # downloads and validates the real datasets (about 150 MB)
cd .. && python -m pytest -q                         # unit tests plus tests on the real data
```

## Data in v0.1 (all downloaded and validated, see docs/DATA.md for licence caveats)

| Dataset | Rows | Role |
|---|---|---|
| ULB credit card fraud (real, anonymised) | 284,807 (492 fraud) | transaction-risk model |
| UCI SMS Spam Collection (CC BY 4.0) | 5,574 | scam-like text classifier |
| OFAC SDN list (official) | 19,485 | payee and name screening |

Citations: Dal Pozzolo, Caelen, Johnson, Bontempi (IEEE CIDM 2015) for the ULB data; Almeida and Hidalgo (2011), UCI, doi:10.24432/C5CC84 for SMS Spam.

## Roadmap

v1 risk model, text classifier, screening, interception flow, analyst workbench, faithfulness evals. v2 simulator and counterfactual estimators. v3 graph-based ring detection and conformal abstention. See the spec for exit criteria.
