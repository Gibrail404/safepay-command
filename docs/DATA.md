# Data register and verification log

Machine-readable version: `data/registry.yaml`. Checks below were run on 2026-11-04.

| Dataset | Link works | Facts confirmed | Licence status | Used in |
|---|---|---|---|---|
| ULB credit card fraud (OpenML id 1597) | Yes, HTTP 200, 150,829,308 bytes | 284,807 rows, 492 fraud (0.172%), md5 from OpenML API | OpenML field says "Public". No formal licence text found. Cite the authors. | v1 |
| UCI SMS Spam Collection | Yes, HTTP 200 | 5,574 messages | CC BY 4.0 (stated on UCI). Attribution required. | v1 |
| OFAC SDN list | Yes, HTTP 200 (official Sanctions List Service) | CSV export available with SHA-256 hashes published by OFAC | Official US Treasury publication. Public-domain status not confirmed. | v1 or v2 |
| Elliptic Bitcoin graph (via PyG mirror) | Yes, HTTP 200 for features, edgelist, classes | 203,769 nodes, 234,355 edges, 166 features (PyG docs) | Original licence not found. A Hugging Face mirror claims MIT, which is not authoritative. | v3 |

## Not used, and why

- IEEE-CIS Fraud Detection: competition data, reuse rules unclear.
- IBM TabFormer: synthetic (rule-based generator) and licence unverified.

## Simulated layer

No public dataset of real bank scam conversations exists. Scam dialogues, interventions and counterfactuals come from a simulator driven by abstract scenario templates. It is labelled "simulated" everywhere it appears, and it is used to test defences, not to make claims about real victims.

## Known limits of the real data

- ULB has no customer ids, so there is no per-customer history. Features V1 to V28 are anonymised PCA components, so per-feature explanations are limited to Time, Amount and the component indices.
- SMS Spam is general spam, not payment scams.
- Elliptic is cryptocurrency, used only to test graph grouping.
