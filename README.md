# WeShare!

Minimal text-first social news sharing app. React/Vite frontend, FastAPI API, SQLAlchemy, PostgreSQL, Argon2 password hashes, signed expiring access tokens, email verification, and server-side moderation.

[![CI](https://github.com/maseedwasimullah-crypto/weshare/actions/workflows/ci.yml/badge.svg)](https://github.com/maseedwasimullah-crypto/weshare/actions/workflows/ci.yml)

## Not a Streamlit application

This repository is **not** a Streamlit project and cannot be deployed to
Streamlit Community Cloud. There is no `streamlit_app.py` entry point, and
adding one would be wrong: the UI is a React single-page application and the
API is a FastAPI application.

Streamlit Community Cloud runs a Python script and serves it as a Streamlit
app. It cannot build a Vite bundle, cannot run a long-lived ASGI server, and
has no PostgreSQL service. A "This file does not exist" error from that
platform therefore means the entry point is missing, not that a setting is
wrong, and the only way to silence it would be to fake an entry point that
discards the real application.

The two parts are deployed separately instead — see
[Deployment](#13-deployment) for the exact steps.

---

## 1. Requirements

| Tool | Version |
| --- | --- |
| Python | 3.11+ (tested on 3.11, 3.12, 3.13 and 3.14) |
| Node.js | 20.19+ (tested on 24.x) |
| npm | 10+ |
| PostgreSQL | 14+ (tested on 18) |

Check what is installed:

```powershell
python --version
node --version
npm --version
```

## 2. Database setup

Create a role and a database with your own credentials:

```sql
CREATE ROLE weshare LOGIN PASSWORD 'choose-a-strong-password';
CREATE DATABASE weshare OWNER weshare;
```

The application also creates any missing tables on startup, but running the
Alembic migrations (step 4) is the supported path and is what a production
deployment should do.

## 3. Configuration

```powershell
Copy-Item .env.example .env
```

Then edit `.env`:

| Variable | Meaning |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy URL, e.g. `postgresql+psycopg://weshare:PASSWORD@127.0.0.1:5432/weshare` |
| `SECRET_KEY` | Signing key for session and verification tokens. Must be **at least 32 characters** or the API refuses to start. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ACCESS_TOKEN_MINUTES` | Session lifetime in minutes (default `30`) |
| `FRONTEND_ORIGIN` | Exact frontend origin used for CORS, e.g. `http://localhost:5173`. Several origins can be listed separated by commas |
| `FRONTEND_ORIGIN_REGEX` | Optional regular expression for preview deployments, e.g. `https://weshare-.*\.vercel\.app`. Leave empty for an exact-origin policy |
| `COOKIE_SECURE` | `true` when served over HTTPS |
| `EMAIL_*` | SMTP settings used to deliver the verification email |
| `MODERATION_BLOCKED_TERMS_FILE` | Block list location; relative paths resolve from the project root |
| `DEV_VERIFICATION_TOKENS` | When SMTP is not configured, registration returns a `verification_token` so the account can still be activated locally. Keep `false` in production |

`.env` is ignored by git. Never commit real credentials.

The frontend has its own build-time variables in `frontend/.env.example`:

| Variable | Meaning |
| --- | --- |
| `VITE_API_URL` | Absolute origin of the deployed API. Leave unset locally: the browser then calls `/api` and the Vite dev server proxies it to the backend. Set it in production, for example `https://weshare-api.onrender.com`. Vite inlines `VITE_` variables at build time, so changing it requires a rebuild. |

## 4. Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Frontend:

```powershell
cd frontend
npm install
```

## 5. Database migrations

From the `backend` directory:

```powershell
cd backend
alembic -c alembic.ini upgrade head
```

Schema changes use Alembic:

```powershell
cd backend
alembic -c alembic.ini revision --autogenerate -m "description"
# review the generated file
alembic -c alembic.ini upgrade head
```

## 6. Running the application

Backend (terminal 1), from the project root:

```powershell
.\.venv\Scripts\Activate.ps1
cd backend
uvicorn app.main:app --reload
```

Frontend (terminal 2), from the `frontend` directory:

```powershell
cd frontend
npm run dev
```

Open <http://localhost:5173>. The Vite dev server proxies `/api` to
`http://localhost:8000`. Set `VITE_API_TARGET` to point the proxy somewhere
else.

API documentation is available at <http://localhost:8000/docs>.

## 7. Email verification

Set `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USER`, `EMAIL_PASSWORD`, `EMAIL_FROM`
and `EMAIL_USE_TLS` in `.env`. SMTP delivery is attempted during registration.

* If SMTP is configured and the email is sent, the account is activated with
  the token delivered by mail.
* If SMTP is **not** configured, the registration response includes a
  `verification_token`. The sign-up screen shows a **Verify this account**
  button so local development does not need a mail server. This only happens
  when SMTP is unset, so a real deployment never leaks a token.

No account can post or comment until a valid verification token reaches
`POST /api/auth/verify`. Sessions expire after `ACCESS_TOKEN_MINUTES`. The API
returns a bearer token and also sets an HttpOnly cookie; the included browser
app keeps the bearer token in `localStorage` for its API requests, so
production deployments should replace this with a CSRF-protected cookie-only
flow.

## 8. Initial administrator

Register normally, complete email verification, then run from the project
root:

```powershell
.\.venv\Scripts\Activate.ps1
python scripts/promote_admin.py
```

The one-time interactive command checks the account email, verified status,
password, and an explicit `PROMOTE` confirmation. No public admin registration
exists. Admin content and account delete controls show a browser confirmation;
all permissions are also enforced by API dependencies. Account deletion
cascades to posts and comments. Audit entries retain the administrator action
and affected IDs, with the administrator reference set to null on later admin
deletion. Administrators cannot delete or deactivate their own account, and
cannot deactivate or delete another administrator.

## 9. Content rules

* Posts accept a maximum of **1000 characters**.
* Comments accept a maximum of **100 characters**.
* Empty submissions, whitespace-only submissions, blank lines, empty lines
  inside the text, and control characters are rejected by **both** the browser
  (`frontend/src/validate.js`) and the API (`backend/app/moderation.py`).
* A single line break inside a post is allowed.

## 10. Moderation and map attribution

`moderation/blocked_terms.txt` is the administrator-maintained, one-term-per-line
configurable block list. Empty and comment lines are ignored. This project does
not bundle a third-party profanity dataset because an appropriate commercial-use
license could not be established. URL heuristics reject selected suspicious URL
patterns; this is not a general malicious-link reputation service. Review and
curate terms with local language and news context in mind. Rejected and accepted
decisions are recorded and visible in the administrator dashboard.

The subtle static backdrop references Wikimedia Commons' **FATA Districts.svg**,
described there as districts of FATA and Frontier Regions as of October 2010 and
marked public domain: <https://commons.wikimedia.org/wiki/File:FATA_Districts.svg>.
It shows historical geography, not current administrative boundaries. The image
is loaded from Wikimedia's upload host, so an internet connection is needed for
the backdrop; app content remains usable if it is unavailable.

## 11. API

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/health` | public | Liveness probe |
| `POST` | `/api/auth/register` | public | Create an account (`201`) |
| `POST` | `/api/auth/verify` | public | Activate an account with a token |
| `POST` | `/api/auth/login` | public | Exchange credentials for a token |
| `POST` | `/api/auth/logout` | public | Clear the session cookie |
| `GET` | `/api/auth/me` | bearer | Current account |
| `GET` | `/api/feed?limit=20&offset=0` | public | Newest posts first, capped at 50 posts and 50 comments per post |
| `POST` | `/api/posts` | bearer, verified | Create a post |
| `POST` | `/api/posts/{post_id}/comments` | bearer, verified | Comment on a post |
| `GET` | `/api/admin/stats` | admin | Dashboard counters |
| `GET` | `/api/admin/users?search=&limit=&offset=` | admin | Account list |
| `PATCH` | `/api/admin/users/{id}` | admin | Activate or deactivate an account |
| `DELETE` | `/api/admin/users/{id}` | admin | Delete an account and its content |
| `GET` | `/api/admin/content` | admin | Recent posts and comments |
| `DELETE` | `/api/admin/posts/{id}` | admin | Delete a post |
| `DELETE` | `/api/admin/comments/{id}` | admin | Delete a comment |
| `GET` | `/api/admin/moderation` | admin | Moderation decision log |

Status codes: text validation errors `422`, duplicate email `409`,
unauthenticated or expired token `401`, non-admin `403`, missing content `404`,
rate-limited login `429`.

## 12. Tests

Backend (from the `backend` directory, or from the project root using the
command below):

```powershell
.\.venv\Scripts\python.exe -m pytest -c backend\pytest.ini --rootdir backend backend\tests
```

The suite always runs against an isolated database and never touches the
development database:

* set `TEST_DATABASE_URL` to run against a disposable PostgreSQL database;
* otherwise a temporary SQLite file is created and used.

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://weshare:PASSWORD@127.0.0.1:5432/weshare_test"
.\.venv\Scripts\python.exe -m pytest -c backend\pytest.ini --rootdir backend backend\tests
```

Frontend validation tests:

```powershell
cd frontend
npm test
```

### Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request:

| Job | What it does |
| --- | --- |
| `backend` | Backend suite on SQLite (Python 3.12) |
| `backend-postgres` | Backend suite against a PostgreSQL 18 service container |
| `frontend` | `npm test` and `npm run build` on Node 20.19 and 24 |
| `secrets` | Fails if a `.env` file is tracked or a credential pattern appears in the git history |

The `secrets` job is a guard against the most damaging mistake this project
could make: committing a real `.env`. It never has access to the secrets
themselves, only to the file names and patterns in the history.

## 13. Deployment

The project has two deployable parts and one database:

| Part | Type | Runs |
| --- | --- | --- |
| `backend/` | FastAPI (ASGI) | uvicorn `app.main:app` |
| `frontend/` | React/Vite static SPA | a static host serves `frontend/dist` |
| PostgreSQL | database | managed Postgres |

The frontend calls `/api/...` relative to its own origin by default, so the two
halves must be connected. The recommended setup below uses Render for the API
and the database, and Vercel for the static frontend.

### 13.1 Backend and database on Render (one click)

`render.yaml` in the repository root is a Render Blueprint. It provisions the
PostgreSQL instance and the API web service together.

1. Open <https://render.com/deploy?repo=https://github.com/maseedwasimullah-crypto/weshare>
2. Sign in to Render with the same GitHub account, and grant Render access to
   the **private** `weshare` repository.
3. Render shows the blueprint. Fill in the values marked `sync: false`:
   * `FRONTEND_ORIGIN` — the exact origin of the deployed frontend, for
     example `https://weshare.vercel.app` (no trailing slash). This is the
     CORS origin, so it must match the browser exactly. Several origins can be
     listed separated by commas. Leave `FRONTEND_ORIGIN_REGEX` empty unless
     you need to allow preview deployments.
   * `EMAIL_HOST`, `EMAIL_USER`, `EMAIL_PASSWORD`, `EMAIL_FROM` — SMTP
     credentials. **SMTP is mandatory in production**: without it no account
     can be activated.
4. Click **Apply**. Render builds the service and creates the database.

What the Blueprint does and why:

* `rootDir` is deliberately left at the repository root. `backend/app/config.py`
  locates `moderation/blocked_terms.txt` relative to the repository root. If
  the backend were the build root, that file would fall outside the build and
  the block list would silently load empty. The service therefore builds from
  the repository root and changes into `backend/` at run time.
* `preDeployCommand` runs `alembic upgrade head` before every deploy, so the
  schema is always migrated before the new version starts serving traffic.
  `alembic.ini` uses a relative `script_location`, so the command changes into
  `backend/` first.
* `SECRET_KEY` uses `generateValue: true`, so Render creates a random secret
  and stores it encrypted. The API refuses to start without a `SECRET_KEY` of
  at least 32 characters.
* `DATABASE_URL` is injected from the attached database. Managed providers
  hand out a plain `postgresql://` URL, which SQLAlchemy would map to
  psycopg2; the application rewrites the scheme to `postgresql+psycopg://`
  unless an explicit driver is present.

### 13.2 Frontend on Vercel

1. Open <https://vercel.com/new> and import the `weshare` repository (grant
   Vercel access to the private repo).
2. Project settings:
   * **Root Directory**: `frontend`
   * **Framework Preset**: Vite
   * **Build Command**: `npm run build`
   * **Output Directory**: `dist`
3. Settings → Environment Variables, add:

   | Name | Value |
   | --- | --- |
   | `VITE_API_URL` | `https://weshare-api.onrender.com` |

   `VITE_` variables are inlined at **build** time, so redeploy after changing
   the value.
4. Deploy. Note the resulting origin, for example
   `https://weshare-abc123.vercel.app`, and set it as `FRONTEND_ORIGIN` on the
   Render service, then trigger a redeploy there.

Netlify and Cloudflare Pages work the same way: set the base directory to
`frontend`, the build command to `npm run build`, the publish directory to
`frontend/dist`, and define `VITE_API_URL`.

### 13.3 Database migrations

`backend/alembic.ini` uses a relative `script_location`, so migrations must
run from inside `backend/`:

```bash
cd backend && alembic -c alembic.ini upgrade head
```

The Render Blueprint runs this automatically through `preDeployCommand` before
every deploy. On any other platform run it from the service **Shell** tab, or
from a machine that can reach the database. On first boot the API also calls
`Base.metadata.create_all()`, which creates missing tables but never alters
existing ones, so run the migration before the first schema change.

### 13.4 Troubleshooting a deployment

| Symptom | Cause | Fix |
| --- | --- | --- |
| `This file does not exist` on Streamlit Community Cloud | Streamlit expects a `streamlit_app.py` entry point, and this project has none because it is a React + FastAPI application | Use Render and Vercel as described above. Do not add a `streamlit_app.py` just to satisfy the form |
| Browser console: *blocked by CORS policy* | `FRONTEND_ORIGIN` does not match the frontend origin exactly | Set it to the exact origin, no trailing slash, then redeploy the API |
| UI: *Cannot reach the API at …* | `VITE_API_URL` was not set when the frontend was built, or the API is asleep | Set `VITE_API_URL` and rebuild/redeploy the frontend. A free Render service sleeps after inactivity; the first request then takes up to a minute |
| UI: *The API was not found at …* | The frontend called its own origin because `VITE_API_URL` was empty | Set `VITE_API_URL` to the API origin and rebuild |
| API log: *SECRET_KEY must be at least 32 characters* | `SECRET_KEY` is missing or too short | Set it, or use `generateValue: true` in the Blueprint |
| API log: *FRONTEND_ORIGIN must contain the exact origin* | `FRONTEND_ORIGIN` is empty | Set it to the deployed frontend origin |
| API log: *No module named psycopg2* | A plain `postgresql://` URL reached SQLAlchemy | Already handled: the scheme is rewritten to `postgresql+psycopg://` |
| API 500 on a missing table | Migrations never ran | Run `cd backend && alembic -c alembic.ini upgrade head` |

### 13.5 Other platforms
The backend needs a long-lived ASGI server, a migration step and a reachable
PostgreSQL, so it suits Render, Fly.io, Railway, Azure App Service, Google
Cloud Run, AWS App Runner or ECS Fargate, and DigitalOcean App Platform.
Serverless platforms that only run short-lived functions (Vercel Functions,
Netlify Functions, Cloudflare Workers) are a poor fit.

The frontend is a static build and suits Vercel, Netlify, Cloudflare Pages,
Render Static Sites, AWS S3 + CloudFront, or GitHub Pages at a root domain.

### 13.6 Production checklist

* HTTPS everywhere and `COOKIE_SECURE=true`.
* `DEV_VERIFICATION_TOKENS=false` and working SMTP. Both together are
  required: with SMTP missing and the flag off, no account can be activated;
  with SMTP missing and the flag on, the verification token is returned in the
  API response.
* `SECRET_KEY` supplied by the platform secret manager, never in the repo.
* The login throttle is per-process and in-memory; it is not a distributed
  rate limiter. There is also no password-reset flow and no server-side token
  revocation. Add those before a public launch.

Pushing the source to GitHub does **not** deploy the site. Deployment to any
hosting provider has to be performed separately and deliberately.


## 14. Project layout

```
backend/
  app/
    config.py        settings loaded from .env
    database.py      engine and session factory
    models.py        SQLAlchemy models
    moderation.py    text validation and block list
    main.py          FastAPI application and routes
  database/
    migrations/      Alembic environment and versions
  tests/             pytest suite
frontend/
  src/
    main.jsx         React application
    validate.js      client side validation rules
    style.css        styling
  .env.example      frontend build-time variables
  tests/             node:test validation suite
moderation/
  blocked_terms.txt  administrator maintained block list
scripts/
  promote_admin.py   interactive administrator promotion
render.yaml          Render blueprint: API service + PostgreSQL
```
