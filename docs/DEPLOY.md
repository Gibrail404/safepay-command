# Deploying SafePay Command

**What has been verified:** the API image builds and runs locally (`docker build`, then `docker run` against PostgreSQL): health, roles, reports, the screening tool, the simulation endpoint, the name-redaction layer (without PyTorch), and a non-root user. The console builds and its browser tests pass against a local API.
**What has not been done:** no cloud deployment. That needs your accounts, so these are steps for you, not a record of something done. Free-tier terms change often; check each provider's current pricing and limits before you rely on them.

## Suggested free setup
| Part | Where | Why |
|---|---|---|
| Console (Next.js) | Vercel | free static-friendly hosting, deploys from GitHub |
| API (the Docker image) | Hugging Face Spaces (Docker) | free CPU with generous memory, built for ML demos; sleeps after inactivity |
| Database | Neon (PostgreSQL) | free tier, scales to zero |
| AI model | Ollama Cloud key (optional) | without it summaries use the safe plain-text fallback |

## Before anything is public
1. **Rotate** the Ollama and Gemini keys that were pasted into a chat during development.
2. **Decide the data question.** OFAC, ULB and Elliptic licence terms are unconfirmed. The image downloads the OFAC list at build time; it contains no ULB or Elliptic data, but the cases and reports derive from them. A private Space with a login avoids the question.
3. **Never ship the demo key.** Create real keys: `SAFEPAY_TENANTS="demo:<long-random>:viewer,team:<long-random>:analyst"`. A shared read-only (viewer) key is reasonable for a public look-around; analyst and admin keys are not.
4. Set `SAFEPAY_CAPABILITY_SECRET` to a long random value (otherwise capability tokens do not survive a restart).
5. Use the provider's connection string with TLS for `DATABASE_URL` (`postgresql+psycopg://...?sslmode=require`).

## Steps
**Database.** Create a Neon project and copy the connection string. Tables are created on first start.

**API (Hugging Face Space).** Create a Space with the Docker SDK. Put the repository files in it, but use `deploy/huggingface/README.md` as the Space's `README.md` (it carries the required front matter, port 7860). Add the secrets `DATABASE_URL`, `SAFEPAY_TENANTS`, `SAFEPAY_CAPABILITY_SECRET`, `SAFEPAY_CORS_ORIGINS` (your console's address) and optionally `OLLAMA_API_KEY`. The first build downloads the OFAC list and a language model and takes several minutes; the image is about 1.4 GB. Check `GET /healthz`.

**Cases.** Import the real cases with an admin key: `python scripts/seed_cases.py --url https://<space>.hf.space --key <admin key>` (needs the Elliptic data and a trained model locally).

**Console (Vercel).** Import the GitHub repository, set the root directory to `console`, build command `npm run build`. No environment variables are required: users type the server address, key and their name into the connect form.

## Check it works
`curl https://<space>.hf.space/healthz`; `GET /v1/whoami` with your key shows the role; the console shows the queue; `GET /v1/audit/verify` returns `ok: true`.

## Known operational gaps
- The rate limiter is per process; the daily AI cap is shared through the database.
- The OFAC list in the image is as of the build date; the screening tool reports `thresholds_tuned_on_this_list: false` when it differs from the list the thresholds were tuned on. Rebuild and re-run `scripts/eval_screening.py` to refresh.
- No automatic backups, alerting or log shipping are configured. `healthz` is the only probe.
- Free instances sleep, so the first request after a quiet period is slow.
