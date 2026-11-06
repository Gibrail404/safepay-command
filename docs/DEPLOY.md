# Deploying SafePay Command

**Currently deployed (free tiers):** console on Vercel (`https://safepay-command.vercel.app`), API on Railway (`https://safepay-command-production.up.railway.app`, built from this repository's `Dockerfile`, **without** the demo assets), database on Neon (PostgreSQL, US East). `scripts/check_deploy.py` passes every required check against it.
**What has been verified:** the API image runs against PostgreSQL (health, roles, accounts, reports, screening, simulation, name redaction without PyTorch, non-root user, about 160 MB of memory at start and about 260 MB after one simulation and one interception); the console builds and its 21 browser tests pass against a local API; CORS is allowed for the console's address.
**What has not been verified:** how Railway's trial credit ($5, 30 days, then $1 a month) holds up under real use; there are no backups, alerts or log shipping.

## The setup
| Part | Where | Notes |
|---|---|---|
| Console (Next.js) | Vercel | the server address is fixed at build time (`NEXT_PUBLIC_API_URL`, defaulting to the hosted API); people sign in with email and password |
| API (the Docker image) | Railway, from the GitHub repository | Hugging Face Docker Spaces are now a paid feature; Render sleeps after 15 idle minutes and takes about a minute to wake; Fly.io and Koyeb have no ongoing free tier. Check each provider's current terms. |
| Database | Neon (PostgreSQL) | free tier, scales to zero |
| AI model | Ollama Cloud key (optional) | without it summaries use the safe plain-text fallback |

## Accounts
- **Sign-up is closed unless the server names a tenant:** set `SAFEPAY_SIGNUP_TENANT=demo` and anyone can create an account that joins that tenant as an **analyst** (never admin). Everyone in a tenant sees the same cases and ledger, so this is a shared demo space, not private workspaces. `SAFEPAY_MAX_USERS` (default 500) caps how many accounts open sign-up can create, and sign-in and sign-up attempts are rate-limited per client address.
- Passwords are stored as salted scrypt hashes; a sign-in token is random, expires after 7 days and only its SHA-256 is stored. A signed-in person's decisions carry their account name, not a header they could change.
- **Admins** are never created by sign-up. Use an admin API key to add people: `POST /v1/auth/users` with `{email, name, password, role}` (role viewer, analyst or admin; the person joins your tenant).
- **API keys** (`SAFEPAY_TENANTS`) still exist for scripts and for `check_deploy.py`; the console does not use them.

## Before anything is public
1. **Rotate** the Ollama and Gemini keys that were pasted into a chat during development.
2. **Data licences** are written up in [DATA_LICENCES.md](DATA_LICENCES.md). The image downloads the OFAC list at build time. The optional demo assets (below) contain a 3,000-row sample of real ULB transactions and a model trained on that data: ULB's stated licence allows reuse with attribution and asks that a substantial extract keep the same licence, so publish that image only with the notice and citation. **Elliptic is CC BY-NC-ND: never seed Elliptic-derived cases on a public instance.** Without the assets the image has no ULB data and the Interception page answers 503.
3. Make a long random admin key: `SAFEPAY_TENANTS="demo:<long-random>:admin"`, and a long random `SAFEPAY_CAPABILITY_SECRET`, otherwise capability tokens do not survive a restart.
4. Use the database provider's connection string with TLS: `DATABASE_URL=postgresql://USER:PASSWORD@HOST/DB?sslmode=require` (leave out `channel_binding=require`).

## Steps
**0. Optional: include the Interception page.** On your machine, with the data and trained model present: `bash scripts/prepare_demo_assets.sh`, then `docker build -t safepay-api .`. Keep that image private (see above).

**1. Database.** Create a Neon project and copy the pooled connection string. Tables are created on first start.

**2. API (Railway).** New project, Deploy from GitHub repo. Variables: `DATABASE_URL`, `SAFEPAY_TENANTS`, `SAFEPAY_CAPABILITY_SECRET`, `SAFEPAY_SIGNUP_TENANT`, `SAFEPAY_CORS_ORIGINS` (the console's address), optionally `OLLAMA_API_KEY`. Settings, Networking, Generate Domain.

**3. Cases.** Only for a private instance: `python scripts/seed_cases.py --url https://<api> --key <admin key>` turns Elliptic alerts into cases, which the Elliptic licence (no derivatives, non-commercial) does not allow on a public site. The public demo therefore has no seeded cases.

**4. Console (Vercel).** Import the GitHub repository, root directory `console`. Set `NEXT_PUBLIC_API_URL` only if the API address differs from the default in `console/lib/api.ts`.

**5. Check it.**
```bash
python scripts/check_deploy.py --url https://<api> --key <admin key> --origin https://<console> --try-interception
```
It prints PASS, FAIL or WARN for: server up, key accepted, wrong key refused, audit chain verifies, reports served, name-screening tool loaded, risk model loaded (WARN if absent), simulation endpoint, the console's address allowed by CORS, and one simulated payment end to end. Exit code 0 only if every required check passes.

## Known operational gaps
- The rate limiters are per process; the daily AI cap is shared through the database. Behind a proxy, the per-address sign-in limit trusts the last `X-Forwarded-For` entry, which is the one the platform's own proxy recorded.
- The OFAC list in the image is as of the build date; the screening tool reports `thresholds_tuned_on_this_list: false` when it differs from the list the thresholds were tuned on. Rebuild and re-run `scripts/eval_screening.py` to refresh.
- No automatic backups, alerting or log shipping are configured. `healthz` is the only probe.
- No password reset, email verification or multi-factor sign-in: accounts are for a demo, not for real customer data.
- Scenarios in the deployed demo come from a 3,000-row sample of the ULB held-out data, so a given seed gives a different payment than on a machine with the full data.
