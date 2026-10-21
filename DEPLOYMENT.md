# SponsyBot — local setup, security, and deployment

This package contains the existing SponsyBot event/sponsor workflow plus authenticated workspace pages. It is an application source bundle, not a hosted deployment: provider keys, Google OAuth credentials, MySQL, and an SMTP account must be configured in the deployment environment.

## Implemented

- Email/password registration and login. Passwords are hashed with Argon2 via `pwdlib`; the browser receives a random HttpOnly session cookie while the database stores only a SHA-256 hash of that session token.
- Google OpenID Connect sign-in through Authlib. Google login works only after adding a Web OAuth client ID/secret and an exact callback URL. Verified email is required.
- All existing business APIs derive the owner `user_id` from the authenticated session, not from a user ID sent by the browser.
- Events page: the original full event form shared by create/edit, search, past/upcoming/type filters, sorting by date, participants, name, newest, and number of saved sponsor candidates. It also displays per-event workflow milestones, refreshed on page load and every 30 seconds while visible.
- Each event's `View Sponsors` opens `/pipeline?event_id=<id>`. Sponsor selection, contact research, saved research evidence, email drafts, and outreach history operate in that event context.
- Email draft modal shows configured sender and the saved recipient, allows subject/body editing, requires a recipient confirmation checkbox plus a browser confirmation, and calls the authenticated send endpoint with both `confirm_recipient=true` and `confirm_send=true`; the backend rejects a send request if either confirmation is missing. Recipient identity comes from the saved contact on the server; browser input cannot replace the actual recipient address.
- Sponsor deletion is event-scoped, requires an explicit browser confirmation, keeps the global company record, and refuses deletion if outreach records exist so the audit trail is preserved.
- Dedicated Email Studio and Outreach Tracking pages use the same protected `/api/outreach` endpoint for drafts, delivery statuses, filters, and history. This project does not implement inbox reply detection or automated follow-up sending.
- AI Usage dashboard tracks provider calls made by this app for Gemini, Tavily, Groq, and Hunter. It does not reconstruct prior use or calls made by other apps/projects/keys. Hunter usage is fetched from its account usage API where configured. Gemini limits vary by model/project and must be configured from the AI Studio account view. Tavily uses actual `usage.credits` when returned, and a conservative per-query estimate otherwise; set the monthly account limit to match your actual plan.
- Authentication creates the `auth_sessions` table and adds `users.google_sub` to the existing `users` table. Event/company/research/contact/outreach tables are not rebuilt. See `migrations/001_auth_sessions.sql` for manual migration.

## Quick start (Windows PowerShell)

1. Open the project root (the folder containing `app.py`).
2. Create a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in database/provider/SMTP values. Do not share or commit `.env`.
4. Ensure the existing SponsyBot MySQL schema is installed and the configured MySQL user can access it. Local development defaults to `AUTH_AUTO_MIGRATE=true`, which adds the authentication schema at startup. For production, take a database backup, apply `migrations/001_auth_sessions.sql` once with a migration account, and set `AUTH_AUTO_MIGRATE=false` in the application environment so the runtime account does not need DDL privileges.
5. Run:

   ```powershell
   uvicorn app:app --host 127.0.0.1 --port 8000 --reload
   ```
6. Open `http://127.0.0.1:8000/login`, create an account or sign in.

## Google OAuth setup

In Google Cloud Console, create **Credentials → OAuth client ID → Web application**. Add the correct authorized redirect URI:

- Local: `http://127.0.0.1:8000/auth/google/callback`
- Production: `https://YOUR_DOMAIN/auth/google/callback`

Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI` in `.env`. Google OAuth cannot be tested with a placeholder client secret. Ensure your consent screen's publishing/test-user configuration permits the accounts you want to use.


## Container deployment

Build the application image from the project root:

```powershell
docker build -t sponsybot:latest .
```

Run it with your configured environment and an existing MySQL schema. Supply environment variables through your deployment platform or a protected local `.env` file; the image intentionally excludes `.env` and the local usage ledger. Example for a Windows-hosted MySQL instance:

```powershell
docker run --rm -p 8000:8000 --env-file .env `
  -e DB_HOST=host.docker.internal `
  -e SPONSYBOT_AI_USAGE_FILE=/app/data/ai_usage.json `
  -v sponsybot-ai-usage:/app/data `
  sponsybot:latest
```

Change `DB_HOST` to the reachable hostname of your MySQL server. In production, use a managed secret store rather than a checked-in `.env`, terminate HTTPS at a trusted reverse proxy, configure `ENVIRONMENT=production`, `COOKIE_SECURE=true`, a stable `SECRET_KEY`, and `AUTH_AUTO_MIGRATE=false` after applying the SQL migration. Persist `/app/data` if you want the single-instance JSON usage ledger to survive container recreation. For multiple replicas, replace that ledger with a shared transactional data store before scaling.

## Production requirements

- Deploy behind HTTPS; set `ENVIRONMENT=production`, `COOKIE_SECURE=true`, `SECRET_KEY` to a unique random string (for example, `python -c "import secrets; print(secrets.token_urlsafe(48))"`), and use the production callback URL.
- Never put API keys, the `.env` file, the database, session tokens, or OAuth client secrets into a public web root or source control.
- Use a least-privilege MySQL account, managed backups, and a migration process. Password hashing and session cookies do not replace HTTPS, backup/restore tests, monitoring, and abuse controls.
- Add rate limiting for authentication endpoints at the reverse proxy or application layer before opening registration to the public internet.
- Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and `SMTP_FROM_EMAIL`, then test only with an address you control before enabling real outreach.
- `GEMINI_DAILY_LIMIT` is an app-ledger budget configured from your active Gemini model/project limit; it is not a quota API readback. Gemini RPM/TPM/RPD limits differ by model/project and should be checked in AI Studio. `GEMINI_RESET_TIMEZONE` defaults to `America/Los_Angeles` because Gemini documented RPD resets at midnight Pacific Time.
- `TAVILY_MONTHLY_LIMIT` must match your actual plan; the example default is 1000 credits as a convenience baseline, not a guaranteed account quota. `TAVILY_RESET_DAY` defaults to 1; change it if your account cycle differs.
- `GROQ_DAILY_LIMIT` is optional and represents a local request count, not a complete Groq RPM/TPM quota calculation.
- The JSON tracker is local-file backed. For multiple app workers/instances, move it to a transactional database or Redis before production scaling.
- A new account will see only events attached to its own `user_id`. If you need to assign older events from an existing workspace to a newly created account, back up MySQL and migrate ownership deliberately; do not remove user ownership filters.

## Validation

```powershell
python -m compileall -q .
node --check frontend/sidebar.js
node --check frontend/login.js
node --check frontend/home.js
node --check frontend/events.js
node --check frontend/sponsors.js
node --check frontend/pipeline.js
node --check frontend/ai-usage.js
node --check frontend/outreach-workspace.js
```

Syntax checks do not prove external connectivity. After configuring credentials, perform manual integration tests for registration/login/logout, Google OAuth callback, event create/edit, sponsor discovery, event-specific delete, draft persistence, SMTP send confirmation, usage reset timers, and account-specific event ownership.
