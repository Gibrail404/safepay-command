# Demo script (about 4 minutes)

Setup once: `docker compose up -d db`, `bash scripts/dev_server.sh`, `python scripts/seed_cases.py --url http://127.0.0.1:8000 --key demo-key`, `cd console && npm run dev`. Open http://localhost:3000, connect with address `http://127.0.0.1:8000`, key `demo-key` (local development key), your name.

| Time | Show | Say |
|---|---|---|
| 0:00 | Cases queue | "These are real alerts from the Elliptic Bitcoin graph. The chip says Real data. Alerts that touch form one case." |
| 0:30 | Open a multi-alert case | "The model score and links come from the API only. Nothing on this page is typed in." |
| 1:00 | Run investigation | "The AI sees only counts, scores and links, and every sentence cites a fact. Hover a citation to see the fact. If the reply fails the fact check, a plain fallback is used. A lone weak alert abstains by a fixed rule, with no AI." |
| 1:45 | Decide (confirm or dismiss) | "Decisions need my name and are final. Now the dataset's own labels appear: they were hidden until I decided." |
| 2:15 | Audit trail | "Every import, investigation and decision is in a hash chain. Chain intact." |
| 2:45 | Reports, Decision Lab | "This one is simulated, so it says so. It shows how often each way of judging a new policy contains the truth." |
| 3:15 | Reports, Graph | "I expected the graph to help. It barely did. The big finding is drift: 0.91 to 0.05 after a market shutdown." |
| 3:40 | Close | "The AI assists, a deterministic policy decides, and I kept the negative results. Limits are on every report." |

Keep ready: `docs/THREAT_MODEL.md` for "what could go wrong", `docs/reports/load.md` for performance questions.
