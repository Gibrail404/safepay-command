# Demo script (about 4 minutes)

Setup once: `docker compose up -d db`, `bash scripts/dev_server.sh`, `python scripts/seed_cases.py --url http://127.0.0.1:8000 --key demo-key`, `cd console && npm run dev`. Open http://localhost:3000, connect with address `http://127.0.0.1:8000`, key `demo-key` (local development key), your name.

| Time | Show | Say |
|---|---|---|
| 0:00 | Overview | "Every number here is counted from what the server really recorded. The ring is the share of AI answers that passed the fact check first time; with n shown, so it is never a bare percentage." |
| 0:20 | **Interception**, honest scam victim, play it by typing | "A real held-out card transaction scored by the real model: band low. The payee is new and the amount sizeable, so the system asks. I am the customer: 'a man from my bank called'. The AI wrote these questions; rules checked them. The policy holds the payment and the customer gets a message. The AI never decided." |
| 1:10 | Reveal and the hidden truth | "It was a scam, hidden until the decision. Now the coached version: the customer follows the scammer's cover story and the policy lets it through. That is the honest limit of asking questions, and the page says so." |
| 1:40 | A case, alert network, **Replay run** | "Real links between real alerts. The run replay shows each step with its real time: facts, abstain rule, AI call with tokens, fact check, priority, ledger." |
| 2:20 | **Override** | "The AI recommended escalating. To dismiss I must write a reason, and the ledger keeps a fingerprint of it. The AI advises, I decide, and both are on record." |
| 2:50 | Audit trail, **tamper demo** | "My browser recomputed every fingerprint. Change a record on my copy: the chain breaks there. Let the attacker cover their tracks: it links up again, but the last fingerprint no longer matches the saved head." |
| 3:30 | **Decision Lab** | "Simulated, so it says so. Move the hold threshold and watch scam money stopped and good customers bothered move together." |
| 3:50 | Report: Interception comparison | "I measured whether the AI adds value over fixed questions plus keyword rules on two separate held-out sets. The first said no difference, the second said the AI was better, so I pooled them: all the detection comes from asking; fixed questions never miss an honest victim but are blind to a cover story, the AI catches some cover stories but misses a few honest victims. They are complementary. I report both sets." |
| 4:15 | Close | "The AI assists, a deterministic policy decides, and I kept the negative results. Limits are on every report." |

Keep ready: `docs/THREAT_MODEL.md` for "what could go wrong", `docs/reports/load.md` for performance questions.
