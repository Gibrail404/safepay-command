# Notice for the demo assets

These files let the hosted Interception demo run. They contain material from third-party datasets, which is why they carry this notice.

## `scenario_pool.parquet`: an extract of the ULB credit card fraud data
- **What it is:** 3,000 transactions (all labelled genuine) taken from the held-out part of the ULB / Worldline "Credit Card Fraud Detection" dataset: 1,500 with amounts from 20 to 400 and 1,500 from 400 to 3,000, drawn with a fixed random seed (`scripts/build_scenario_pool.py`). Values are unchanged; the original row number is kept in the `index` column. The 28 `V` columns are the dataset's own anonymised PCA components.
- **Source:** Machine Learning Group, ULB, with Worldline. Kaggle: https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud
- **Licence stated by the publisher on that page (read 2026-11-07):** Database: Open Database Licence (ODbL 1.0), Contents: Database Contents Licence (DbCL 1.0). This extract is a substantial part of the database and is therefore made available under the **ODbL 1.0** (https://opendatacommons.org/licenses/odbl/1-0/), with the contents under DbCL 1.0 (https://opendatacommons.org/licenses/dbcl/1-0/). If you redistribute it or a database built from it, keep this notice and the same licence.
- **Please cite:** Andrea Dal Pozzolo, Olivier Caelen, Reid A. Johnson and Gianluca Bontempi. Calibrating Probability with Undersampling for Unbalanced Classification. Symposium on Computational Intelligence and Data Mining (CIDM), IEEE, 2015. The dataset page lists further papers to cite.

## `models/risk/`: a model trained on that dataset
A LightGBM transaction-risk model trained on the full ULB data (60/20/20 time-ordered split) and its metadata. It is a Produced Work under the ODbL and is shared with this notice; it is not a copy of the data.

## `models/text_scam/`: a text model trained on the SMS Spam Collection
Trained on the UCI SMS Spam Collection (CC BY 4.0). Almeida, T. and Hidalgo, J. (2011). SMS Spam Collection. UCI Machine Learning Repository. https://doi.org/10.24432/C5CC84

## `ml/`
The project's own training and serving code, copied so the image can load the models.

This note is a working record, not legal advice. See `docs/DATA_LICENCES.md`.
