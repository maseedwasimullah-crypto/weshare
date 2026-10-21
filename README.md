# WeShare!

Minimal text-first social news sharing app. React/Vite frontend, FastAPI API, SQLAlchemy, PostgreSQL, Argon2 password hashes, signed expiring access tokens, email verification, and server-side moderation.

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
| `FRONTEND_ORIGIN` | Exact frontend origin used for CORS, e.g. `http://localhost:5173` |
| `COOKIE_SECURE` | `true` when served over HTTPS |
| `EMAIL_*` | SMTP settings used to deliver the verification email |
| `MODERATION_BLOCKED_TERMS_FILE` | Block list location; relative paths resolve from the project root |
| `DEV_VERIFICATION_TOKENS` | When SMTP is not configured, registration returns a `verification_token` so the account can still be activated locally. Keep `false` in production |

`.env` is ignored by git. Never commit real credentials.

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

## 13. Production deployment

1. Build the frontend: `cd frontend; npm run build` and serve `frontend/dist`
   from a static host.
2. Run the API from the `backend` directory:
   `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
3. Set `FRONTEND_ORIGIN` to the exact frontend origin, enable HTTPS, set
   `COOKIE_SECURE=true`, and keep secrets in the deployment secret manager.
4. Provision PostgreSQL, run `alembic -c alembic.ini upgrade head` before the
   app starts, configure SMTP, and put a reverse proxy with TLS in front.
5. The current API has no distributed login rate limiter, no password-reset
   flow and no robust token revocation; add those before a public launch. The
   included login throttle is per-process and in-memory, and is not claimed to
   be a distributed limiter.

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
  tests/             node:test validation suite
moderation/
  blocked_terms.txt  administrator maintained block list
scripts/
  promote_admin.py   interactive administrator promotion
```
