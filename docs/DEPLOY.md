# Deploying SafePay Command

**What has been verified:** an earlier build of the API image ran locally against PostgreSQL (health, roles, reports, the screening tool, the simulation endpoint, name redaction without PyTorch, a non-root user). `scripts/demo.sh` was run end to end from an empty database. The console builds and its 19 browser tests pass against a local API.
**What has not been verified:** (1) the latest image, which adds the optional demo assets and the name list, could not be finished building in the last session because the network stalled while pip was downloading packages (a read timeout, not a code error); rebuild it and run `scripts/check_deploy.py` against it before you rely on it. (2) Nothing has been deployed to a cloud: that needs your accounts and secrets, which an assistant must not create or enter. Free-tier terms change often; check each provider's current pricing and limits.

## Suggested free setup
| Part | Where | Why |
|---|---|---|
| Console (Next.js) | Vercel | free hosting that deploys from GitHub |
| API (the Docker image) | Hugging Face Spaces (Docker, **private**) | free CPU with generous memory; sleeps when idle |
| Database | Neon (PostgreSQL) | free tier, scales to zero |
| AI model | Ollama Cloud key (optional) | without it summaries use the safe plain-text fallback |

## Before anything is public
1. **Rotate** the Ollama and Gemini keys that were pasted into a chat during development.
2. **Decide the data question.** OFAC, ULB and Elliptic licence terms are unconfirmed. The image downloads the OFAC list at build time. The optional demo assets (below) contain a 3,000-row sample of real ULB transactions and a model trained on that data: **put an image with those assets only into a PRIVATE Space** until the terms are settled. Without the assets the image has no ULB data and the Interception page answers 503.
3. **Never ship the demo key.** Make real keys: `SAFEPAY_TENANTS="demo:<long-random>:viewer,team:<long-random>:analyst"`. A shared read-only (viewer) key is reasonable for a look-around; analyst and admin keys are not.
4. Set `SAFEPAY_CAPABILITY_SECRET` to a long random value, otherwise capability tokens do not survive a restart.
5. Use the database provider's connection string with TLS, written in SQLAlchemy form: `postgresql+psycopg://USER:PASSWORD@HOST/DB?sslmode=require`.

## Steps
**0. Optional: include the Interception page.** On your machine, with the data and trained model present: `bash scripts/prepare_demo_assets.sh`. It copies the risk model, the scenario sample and the `ml` package into `deploy/demo_assets/` (git-ignored). Then `docker build -t safepay-api .` picks them up, installs LightGBM and its runtime library, and the page works. Build once locally and run `python scripts/check_deploy.py` against `docker run -p 7861:7860 ...` before uploading anything.

**1. Database.** Create a Neon project and copy the connection string (convert it to the form above). Tables are created on first start.

**2. API (Hugging Face Space).** Create a **private** Space with the Docker SDK. Put the repository files in it, but use `deploy/huggingface/README.md` as the Space's `README.md` (it carries the front matter and port 7860). If you want the demo assets, add them with `git add -f deploy/demo_assets` because they are git-ignored. Add these as Space secrets: `DATABASE_URL`, `SAFEPAY_TENANTS`, `SAFEPAY_CAPABILITY_SECRET`, `SAFEPAY_CORS_ORIGINS` (your console's address) and optionally `OLLAMA_API_KEY`. The first build takes several minutes; the image is about 1.4 GB.

**3. Cases.** Import the real cases with an admin key: `python scripts/seed_cases.py --url https://<space>.hf.space --key <admin key>` (needs the Elliptic data and a trained model locally).

**4. Console (Vercel).** Import the GitHub repository, root directory `console`, build command `npm run build`. No environment variables are required: users type the server address, key and their name into the connect form.

**5. Check it.** One command tells you what works:
```bash
python scripts/check_deploy.py --url https://<space>.hf.space --key <your key> --origin https://<console>.vercel.app --try-interception
```
It prints PASS, FAIL or WARN for: server up, key accepted, wrong key refused, audit chain verifies, reports served, name-screening tool loaded, risk model loaded (WARN if absent), simulation endpoint, the console's address allowed by CORS, and one simulated payment end to end. Exit code 0 only if every required check passes.

## Known operational gaps
- The rate limiter is per process; the daily AI cap is shared through the database.
- The OFAC list in the image is as of the build date; the screening tool reports `thresholds_tuned_on_this_list: false` when it differs from the list the thresholds were tuned on. Rebuild and re-run `scripts/eval_screening.py` to refresh.
- No automatic backups, alerting or log shipping are configured. `healthz` is the only probe.
- Free instances sleep, so the first request after a quiet period is slow.
- Scenarios in the deployed demo come from a 3,000-row sample of the ULB held-out data, so a given seed gives a different payment than on a machine with the full data. The evaluation reports use the full data.
