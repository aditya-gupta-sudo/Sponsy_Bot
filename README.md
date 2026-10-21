# SponsyBot

SponsyBot is an event sponsorship workspace built with FastAPI, vanilla HTML/CSS/JavaScript, MySQL, and provider SDKs for Gemini, Tavily, Groq, and Hunter.io.

## What is included

- A consistent workspace sidebar and protected pages for Home, Events, Sponsor Discovery, Sponsor Pipeline, Email Studio, Outreach Tracking, and AI Usage & Limits.
- Session-based authentication with email/password registration and Google OpenID Connect sign-in. Passwords are Argon2-hashed; only hashes of opaque session tokens are stored in MySQL.
- One event form for create and edit, event search/filter/sorting, sponsor candidate counts, and per-event workflow milestones.
- Event-specific sponsor pipeline with research evidence, selection, contact discovery, candidate deletion confirmation, and prevention of deleting a candidate with outreach history.
- Editable saved email drafts and explicit recipient/send confirmation before SMTP delivery.
- A provider-call usage ledger. Hunter can show live account quota when its API key is configured. Gemini and Tavily display SponsyBot-tracked usage against configured limits, not a universal provider-account quota readback.

## Quick start

1. Use Python 3.10 or newer and MySQL. Make a backup before applying this version to an existing database.
2. Create/activate a virtual environment and install dependencies:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env`, then fill in the MySQL connection, a unique `SECRET_KEY`, provider API keys, and SMTP configuration. Never share `.env`.
4. Configure Google OAuth if Google sign-in is required. The callback URL must exactly match the Google Cloud Console OAuth client configuration.
5. Run locally:

   ```powershell
   uvicorn app:app --host 127.0.0.1 --port 8000 --reload
   ```

6. Open `http://127.0.0.1:8000/login` and register or sign in.

See [DEPLOYMENT.md](DEPLOYMENT.md) for migration choices, provider configuration, Google OAuth setup, SMTP testing, production HTTPS settings, known limitations, and the validation checklist. A `Dockerfile` is included for repeatable container builds; MySQL remains an external service.

## API safety and deployment notes

- Business API routes derive the current user from the server-side session. The frontend does not choose the `user_id` for event/sponsor operations.
- A new account sees only events owned by that account. Back up the database and explicitly migrate ownership if existing records need to be assigned to a different user.
- Use HTTPS, a strong stable secret, a least-privilege MySQL account, backups, and authentication rate limiting before public deployment. Review `DEPLOYMENT.md` before deploying.
- Automatic reply detection and scheduled follow-ups are not implemented in this package.
