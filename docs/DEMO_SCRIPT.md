# Demo script (about 4 minutes)

Setup once: `docker compose up -d db`, `bash scripts/dev_server.sh`, `python scripts/seed_cases.py --url http://127.0.0.1:8000 --key demo-key`, `cd console && npm run dev`. Open http://localhost:3000, connect with address `http://127.0.0.1:8000`, key `demo-key` (local development key), your name.

| Time | Show | Say |
|---|---|---|
| 0:00 | Cases queue | "These are real alerts from the Elliptic Bitcoin graph. The chip says Real data. Alerts that touch form one case." |
| 0:25 | Open a multi-alert case, Run investigation | "The AI sees only counts, scores and links, and every sentence cites a fact. Hover a citation to see the fact." |
| 0:50 | **Replay run** | "This is the real recorded run, slowed down so you can follow it. Facts, no free text to redact, the abstain rule, the AI call with its real time, the fact check, the priority rule and the ledger. If the reply fails the check it routes to a safe fallback, and a lone weak alert stops at a fixed rule with no AI at all. Click a step to see what happened in it." |
| 1:30 | Decide | "Decisions need my name and are final. Now the dataset's own labels appear: they were hidden until I decided." |
| 1:50 | Audit trail, **tamper demo** | "Your browser just re-computed every fingerprint itself. Pick a record, change it on your own copy: the chain breaks there and everything after it is not trusted. Now let the attacker recompute every hash to cover their tracks: the records link up again, but the last fingerprint no longer matches the one the server saved separately." |
| 2:40 | **Decision Lab** | "Simulated, so it says so. Move the hold threshold: scam money stopped goes down, good customers bothered goes down too. This is the trade-off a policy owner has to choose." |
| 3:20 | Reports, Graph | "I expected the graph to help. It barely did. The big finding is drift: 0.91 to 0.05 after a market shutdown." |
| 3:45 | Close | "The AI assists, a deterministic policy decides, and I kept the negative results. Limits are on every report." |

Keep ready: `docs/THREAT_MODEL.md` for "what could go wrong", `docs/reports/load.md` for performance questions.
