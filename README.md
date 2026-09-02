# IT Helpdesk

[![CI](https://github.com/maulanaldimas/helpdesk-tiket/actions/workflows/ci.yml/badge.svg)](https://github.com/maulanaldimas/helpdesk-tiket/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-3776AB.svg)](https://www.python.org/)
[![Django 5.1](https://img.shields.io/badge/Django-5.1-092E20.svg)](https://www.djangoproject.com/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/Tests-113%20passing-brightgreen.svg)](#testing)
[![Live Demo](https://img.shields.io/badge/Live%20Demo-Try%20it!-00C853.svg)](https://itsokkalink.tailbc5ae7.ts.net/helpdesk)

> A full-featured, production-ready **IT support ticket system** built with Django. Multi-company, role-based access, SLA tracking, analytics dashboard, knowledge base, and audit trail — all containerized with Docker.

---

**Live Demo:** [itsokkalink.tailbc5ae7.ts.net/helpdesk](https://itsokkalink.tailbc5ae7.ts.net/helpdesk)

> Demo ini di-hosting dari komputer pribadi (Docker + Tailscale Funnel + Caddy) dan hanya aktif saat server daring.

---

## Highlights

- **15 Django models** with complex relationships and multi-tenancy
- **113 automated tests** covering models, views, middleware, and management commands
- **CI/CD pipeline** with GitHub Actions (test + Docker image build to GHCR)
- **5-service Docker architecture** (Django, PostgreSQL, Redis, Celery worker, SLA worker)
- **Security hardened**: RBAC, access-controlled media, CSRF, HSTS-ready, environment-based secrets

---

## Features

### Ticket Management
- Create, search, filter, and bulk-update tickets by status/priority
- Threaded comments with file attachments
- In-app notifications + async email via Celery
- **SLA auto-tracking** per priority (Urgent: 4h, High: 24h, Medium: 72h, Low: 168h)
- SLA pause/resume when waiting for requester reply
- **First response time** tracking
- **Auto-close** stale resolved tickets (`close_stale_resolved` management command)
- Ticket merging, CSV import, PDF export
- **Customer satisfaction (CSAT)** rating on resolved tickets

### Role-Based Access Control

| Role      | Scope                                                  |
|-----------|--------------------------------------------------------|
| **Admin** | All tickets, user/company/category management, reports |
| **Staff** | Company-scoped tickets, status changes, assignments    |
| **Requester** | Own tickets only (company auto-locked)            |

- Out-of-scope ticket access returns **404** (no information leakage)

### Dashboard & Analytics
- KPI cards: total/active/overdue tickets, SLA compliance %, avg resolution time, first response time, CSAT score
- 14-day trend chart (Chart.js)
- Status & priority distribution
- Per-staff workload breakdown (admin only)
- Personal "My Summary" dashboard for staff/requesters

### Reporting & Export
- Filter by status, priority, company, date range
- Export to **Excel (XLSX)** with styled headers
- Export to **PDF** with charts and tables (ReportLab)
- CSV export

### Knowledge Base
- Markdown articles with live preview
- Auto-sanitized HTML content
- Filterable by category
- Admin CRUD with publish/draft states

### User Management
- Admin CRUD with role assignment
- Self-service registration with admin approval workflow
- Admin-initiated password reset
- Profile with avatar, phone, job title

### Canned Responses
- Template answers for staff to respond faster
- Placeholder support (`{ticket_id}`, `{requester}`)

### Auto-Assignment
- Rule-based ticket assignment by company, category, and priority
- Automatic notification to assigned staff

### Audit Trail
- Every action logged: creation, status changes, assignments, comments, attachments
- Activity log viewable on ticket detail page

### Security & Production Hardening
- Environment-based configuration (`.env`)
- **Idle session timeout** (configurable, default 30 min)
- Security headers: HSTS, XSS filter, content-type nosniff, referrer policy
- Protected media serving (access-controlled file downloads)
- CSRF protection, secure cookies
- Logging with rotation (file + console)

---

## Architecture

```
                    ┌─────────────────────────────────┐
                    │         Docker Compose           │
                    │                                  │
  ┌──────────┐     │  ┌─────┐  ┌──────┐  ┌────────┐  │
  │  Client  │────▶│  │ NGX │  │ Web  │  │  DB    │  │
  │(Browser) │     │  │:8000│──│Django│──│Postgres│  │
  └──────────┘     │  └─────┘  └──┬───┘  └────────┘  │
                    │             │                    │
                    │        ┌────┴────┐               │
                    │        │  Redis  │               │
                    │        └────┬────┘               │
                    │         ┌───┴───┐                │
                    │    ┌────┴┐  ┌───┴───┐            │
                    │    │Celery│  │Worker │            │
                    │    │Email │  │SLA    │            │
                    │    └─────┘  └───────┘            │
                    └─────────────────────────────────┘
```

| Service    | Technology           | Purpose                          |
|------------|----------------------|----------------------------------|
| `web`      | Django 5.1 + Gunicorn | Application server               |
| `db`       | PostgreSQL 16        | Primary database                 |
| `redis`    | Redis 7              | Celery broker + cache            |
| `celery`   | Celery worker        | Async email notifications        |
| `worker`   | Custom loop          | Hourly SLA check + auto-close    |

---

## Tech Stack

| Layer          | Technology                                          |
|----------------|-----------------------------------------------------|
| **Backend**    | Django 5.1, Python 3.12+                            |
| **Database**   | PostgreSQL 16 (SQLite for local dev)                |
| **Task Queue** | Celery + Redis                                      |
| **Frontend**   | Django Templates, Chart.js, Tailwind CSS (CDN)      |
| **PDF/Excel**  | ReportLab, OpenPyXL                                 |
| **Markdown**   | python-markdown + bleach (sanitization)              |
| **Deployment** | Docker, Gunicorn, WhiteNoise                        |
| **CI/CD**      | GitHub Actions, GitHub Container Registry            |
| **Testing**    | Django TestCase, 113 automated tests                |

---

## Quick Start

### Docker (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/maulanaldimas/helpdesk-tiket.git
cd helpdesk-tiket

# 2. Configure environment
cp .env.example .env
# Edit .env — set SECRET_KEY, DB_PASSWORD, ALLOWED_HOSTS, etc.

# 3. Build and start all services
docker compose up -d --build

# 4. Create admin user
docker compose exec web python manage.py createsuperuser

# 5. Open in browser
open http://localhost:8000
```

### Local Development

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env

# 4. Run migrations
python manage.py migrate
python manage.py collectstatic --noinput

# 5. Create superuser
python manage.py createsuperuser

# 6. Start development server
python manage.py runserver
```

> **Note:** The first user created via `createsuperuser` should have their role set to **Admin** through the Django admin panel (`/admin/`). All new users default to `Requester`.

---

## Demo Accounts

| Username | Password     | Role    | Notes                    |
|----------|--------------|---------|--------------------------|
| admin    | (set via env)| Admin   | Full access               |

> Create additional users through the admin panel or enable self-registration (`REGISTRATION_OPEN=True`).

---

## Testing

```bash
# Run all 113 tests
python manage.py test tickets

# With verbosity
python manage.py test tickets --verbosity=2

# Inside Docker
docker compose exec web python manage.py test tickets
```

---

## Project Structure

```
helpdesk-tiket/
├── helpdesk/                        # Project configuration
│   ├── settings.py                  # Settings (env-based)
│   ├── urls.py                      # Root URL config
│   ├── middleware.py                 # Idle session timeout
│   └── tasks.py                     # Celery tasks
├── tickets/                         # Main application
│   ├── models.py                    # 15 models (Ticket, Comment, etc.)
│   ├── views.py                     # 40+ views (1525 lines)
│   ├── forms.py                     # Django forms
│   ├── admin.py                     # Admin panel customization
│   ├── tests.py                     # 113 automated tests
│   ├── context_processors.py        # Template context (notifications, settings)
│   ├── management/commands/
│   │   ├── close_stale_resolved.py  # Auto-close resolved tickets
│   │   └── sla_check.py             # SLA monitoring
│   ├── migrations/                  # Database migrations
│   └── templates/tickets/           # 40+ HTML templates
├── .github/workflows/ci.yml        # CI/CD pipeline
├── Dockerfile                       # Application image
├── docker-compose.yml               # 5-service orchestration
├── entrypoint.sh                    # Auto migrate + collectstatic
├── requirements.txt                 # Python dependencies
├── .env.example                     # Environment template
├── LICENSE                          # MIT License
└── README.md                        # This file
```

---

## API Endpoints (Key Routes)

| Method | URL                         | Description                  |
|--------|-----------------------------|------------------------------|
| GET    | `/`                         | Dashboard with KPIs          |
| GET    | `/my-summary/`              | Personal summary             |
| GET/POST | `/tickets/`               | Ticket list + bulk actions   |
| GET/POST | `/ticket/new/`            | Create ticket                |
| GET/POST | `/ticket/<id>/`           | Ticket detail + comments     |
| GET    | `/reports/`                 | Reports with export          |
| GET    | `/kb/`                      | Knowledge base               |
| GET    | `/activity/`                | Activity log (audit trail)   |
| GET/POST | `/users/`                 | User management (admin)      |
| GET/POST | `/auto-assign/`           | Auto-assignment rules        |
| POST   | `/ticket/<id>/merge/`      | Merge tickets                |
| POST   | `/ticket/<id>/pdf/`        | Export ticket as PDF         |

---

## Environment Variables

| Variable              | Required | Default       | Description                         |
|-----------------------|----------|---------------|-------------------------------------|
| `SECRET_KEY`          | Yes      | —             | Django secret key                    |
| `DEBUG`               | No       | `True`        | Debug mode                          |
| `ALLOWED_HOSTS`       | No       | `127.0.0.1`  | Comma-separated allowed hosts       |
| `DB_PASSWORD`         | Yes*     | —             | PostgreSQL password (*required for Docker) |
| `SITE_URL`            | No       | `http://localhost:8000` | Public URL for email links |
| `EMAIL_BACKEND`       | No       | Console       | Email backend                       |
| `REGISTRATION_OPEN`   | No       | `True`        | Allow self-registration              |
| `IDLE_TIMEOUT`        | No       | `1800`        | Session idle timeout (seconds)      |

See [`.env.example`](.env.example) for the full list.

---

## Roadmap

- [x] Multi-company tenancy with data isolation
- [x] Role-based access control (Admin / Staff / Requester)
- [x] SLA tracking with auto-escalation
- [x] SLA pause/resume on requester reply
- [x] First response time tracking
- [x] Customer satisfaction (CSAT) rating
- [x] Auto-close stale resolved tickets
- [x] Internal notes (staff-only, hidden from requesters)
- [x] Time tracking on tickets
- [x] Auto-assignment rules
- [x] Canned responses for faster replies
- [x] Ticket merge
- [x] CSV import + Excel/PDF export
- [x] Knowledge base with Markdown
- [x] Activity audit trail
- [x] Idle session timeout
- [x] Security headers (HSTS, XSS, CSP-ready)
- [x] CI/CD with GitHub Actions + GHCR
- [x] Docker Compose (5 services)
- [x] Password reset flow
- [ ] Webhook integrations (Slack / Teams)
- [ ] LDAP / SSO authentication
- [ ] Two-factor authentication (2FA)
- [ ] REST API (DRF)
- [ ] Real-time notifications (WebSocket)

---

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## Author

**Maulana Dimas** — [GitHub](https://github.com/maulanaldimas)

Built as a portfolio project demonstrating full-stack Django development with production-grade architecture, testing, and deployment.
