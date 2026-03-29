# EduKai CV Automation Engine

A production-grade backend system that automates the full lifecycle of candidate CV processing for an education recruitment agency — from bulk upload through AI-powered enhancement, PDF generation, geo-filtered organization matching, and targeted email outreach.

Built with **Django 6**, **Celery**, **MinIO**, **PostgreSQL**, **Redis**, and **SendGrid**, containerised with Docker.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Background Tasks](#background-tasks)
- [Key Design Decisions](#key-design-decisions)

---

## Overview

EduKai automates a recruitment agency's entire candidate workflow:

1. **Bulk CV Upload** — Upload 500–1000 CVs at once. Each CV is stored in MinIO and queued for AI processing.
2. **AI Processing** — A FastAPI/Celery AI service extracts candidate data, performs quality checks, and generates enhanced email content.
3. **PDF Generation** — WeasyPrint generates a branded enhanced CV PDF stored in MinIO.
4. **Availability Email** — Candidates are automatically emailed about new opportunities via SendGrid.
5. **Organization Management** — Import 24,000+ schools from Excel, auto-geocode addresses using Nominatim (free, no API key).
6. **Geo Filtering** — Find all organizations within N km of a candidate using their postcode.
7. **Targeted Outreach** — Send candidate profiles to up to 1000 selected school contacts in one request.
8. **Dashboard** — Real-time statistics, activity log, and notification system for the system operator.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        Docker Network                        │
│                                                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐               │
│  │ Backend  │    │ AI       │    │ MinIO    │               │
│  │ Django   │◄──►│ FastAPI  │    │ Storage  │               │
│  │ :8000    │    │ :8080    │    │ :9000    │               │
│  └────┬─────┘    └────┬─────┘    └──────────┘               │
│       │               │                                      │
│  ┌────▼──────────────▼──┐    ┌──────────┐                   │
│  │       Redis           │    │ Postgres │                   │
│  │  Broker + Cache       │    │ :5432    │                   │
│  └────┬──────────────────┘    └──────────┘                   │
│       │                                                      │
│  ┌────▼────────────────────────────────────┐                 │
│  │           Celery Workers                │                 │
│  │  default │ polling │ pdf │ beat         │                 │
│  └─────────────────────────────────────────┘                 │
└──────────────────────────────────────────────────────────────┘
```

### Data Flow — CV Processing

```
Upload CV
  → store in MinIO
  → process_cv_task (queue: default)
      → POST cv_url to AI service
      → receive task_id
      → poll_ai_result_task (queue: polling)
          → polls AI every 30s
          → on completion: save data + download profile photo
          → generate_enhanced_cv_pdf_task (queue: pdf)
              → render HTML template with WeasyPrint
              → save PDF to MinIO
              → send availability email via SendGrid
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web Framework | Django 6.0.2 + Django REST Framework |
| AI Service | FastAPI + Celery (separate service) |
| Task Queue | Celery 5.6 with Redis broker |
| Database | PostgreSQL 16 |
| Cache / Broker | Redis 7 |
| File Storage | MinIO (S3-compatible) |
| PDF Generation | WeasyPrint |
| Email | SendGrid |
| Geocoding | Nominatim / OpenStreetMap (free, no API key) |
| Auth | JWT via djangorestframework-simplejwt (HttpOnly cookies) |
| API Docs | drf-spectacular (Swagger + ReDoc) |
| Containerisation | Docker + Docker Compose |

---

## Project Structure

```
EduKai-CV-Automation-Engine/
├── docker-compose.yml              # Orchestrates all 9 services
│
├── Backend/                        # Django backend (primary focus)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── manage.py
│   ├── .env.example                # Copy to .env and configure
│   ├── Create_the_MinIO_Bucket.py  # One-time MinIO bucket setup
│   │
│   ├── edukai/                     # Django project config
│   │   ├── settings.py
│   │   ├── celery.py               # Celery app + task routing
│   │   └── urls.py
│   │
│   ├── account/                    # Auth, users, dashboard, activity log
│   │   ├── models.py               # User + ActivityLog models
│   │   ├── views.py                # Auth, dashboard, activity endpoints
│   │   ├── serializers.py
│   │   └── utils/
│   │       ├── activity.py         # log_activity() helper
│   │       ├── cookies.py          # HttpOnly JWT cookie helpers
│   │       └── password_reset.py   # OTP via Redis + SendGrid
│   │
│   ├── candidate/                  # Core candidate management
│   │   ├── models.py               # Candidate, CandidateUploadBatch
│   │   ├── views.py                # 15+ API endpoints
│   │   ├── serializers.py
│   │   ├── tasks/
│   │   │   ├── process_cv.py       # Task 1: submit CV to AI
│   │   │   ├── poll_ai_result.py   # Task 2: poll AI, save data, download photo
│   │   │   ├── generate_pdf.py     # Task 3: WeasyPrint PDF generation
│   │   │   ├── rewrite_cv.py       # AI rewrite polling task
│   │   │   ├── send_email.py       # Candidate availability email
│   │   │   ├── send_to_contacts.py # Bulk outreach to school contacts
│   │   │   ├── geocode.py          # On-demand candidate geocoding
│   │   │   ├── sync_batch.py       # Periodic batch progress sync
│   │   │   └── cleanup.py          # MinIO file cleanup on delete
│   │   ├── utils/
│   │   │   ├── minio_utils.py      # Pre-signed URL generation
│   │   │   └── pagination.py       # StandardPagination class
│   │   └── templates/
│   │       └── candidate/
│   │           └── enhanced_cv.html # WeasyPrint CV template
│   │
│   ├── organization/               # School/organization management
│   │   ├── models.py               # Organization + OrganizationContact
│   │   ├── views.py                # CRUD + import + geo filter endpoints
│   │   ├── serializers.py
│   │   └── tasks/
│   │       ├── geocode.py          # Postcode to lat/lng via Nominatim
│   │       └── import_excel.py     # Bulk Excel import (24,000+ orgs)
│   │
│   └── Demo Data/
│       ├── Organizations.xlsx      # Sample organization data
│       ├── Contacts.xlsx           # Sample contact data
│       └── Demo CV/                # Sample CV PDFs for testing
│
└── AI/                             # FastAPI AI service (separate service)
    ├── app/
    │   ├── main.py                 # FastAPI app entry point
    │   ├── tasks.py                # Celery tasks (CV processing)
    │   ├── api/v1/routes.py        # /regeneration, /rewrite, /tasks endpoints
    │   ├── services/
    │   │   ├── ai_service.py       # OpenAI GPT integration
    │   │   └── file_service.py     # CV download and parsing
    │   └── prompts/                # GPT prompt templates
    └── requirements.txt
```

---

## Getting Started

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- Git

### Quick Start

**1. Clone the repository**

```bash
git clone https://github.com/Mehedi-Hasan-Rabbi/EduKai-CV-Automation-Engine
cd EduKai-CV-Automation-Engine
```

**2. Configure environment variables**

```bash
cp Backend/.env.example Backend/.env
cp AI/.env.example AI/.env
```

Open `Backend/.env` and set the required values:

```env
SECRET_KEY=your-50-char-secret-key-here
SENDGRID_API_KEY=SG....
SENDGRID_FROM_EMAIL=you@yourdomain.com
```

Open `AI/.env` and add your OpenAI key:

```env
OPENAI_API_KEY=sk-...
```

**3. Build and start all services**

```bash
docker compose up --build
```

This starts 9 containers. Wait until you see all workers report `ready`.

**4. Create a superuser**

In a new terminal:

```bash
docker compose exec backend python manage.py createsuperuser
```

**5. Create the MinIO bucket**

Option A — via script (recommended):
```bash
docker compose exec backend python Create_the_MinIO_Bucket.py
```

Option B — via browser:
1. Open [http://localhost:9001](http://localhost:9001)
2. Login with `minioadmin` / `minioadmin123`
3. Create a bucket named `edukai`
4. Set the bucket access policy to **Public**

**6. Verify everything is running**

| Service | URL |
|---|---|
| Django API | http://localhost:8000 |
| Swagger Docs | http://localhost:8000/api/docs/ |
| ReDoc | http://localhost:8000/api/redoc/ |
| Django Admin | http://localhost:8000/admin/ |
| AI Service | http://localhost:8080 |
| MinIO Console | http://localhost:9001 |

**7. Import demo data (optional)**

Import sample organizations and contacts using the demo Excel files:

```
POST http://localhost:8000/api/organizations/import/
Body: form-data → file: Backend/Demo Data/Organizations.xlsx

POST http://localhost:8000/api/organizations/import/contacts/
Body: form-data → file: Backend/Demo Data/Contacts.xlsx
```

---

### Development Without Docker

If you prefer running locally:

**Backend:**
```bash
cd Backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # configure .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

**Celery workers — open 3 additional terminals:**
```bash
# Terminal 2 — default queue (CV upload, geocoding, emails)
celery -A edukai worker --queues=default --concurrency=4 --loglevel=info --hostname=default@%h

# Terminal 3 — polling and pdf queues
celery -A edukai worker --queues=polling,pdf --concurrency=4 --loglevel=info --hostname=pollpdf@%h

# Terminal 4 — beat scheduler (runs every 5 min batch sync)
celery -A edukai beat --loglevel=info
```

Redis, PostgreSQL, and MinIO must be running locally before starting.

---

## Environment Variables

### Backend (`Backend/.env`)

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | ✅ | Django secret key (min 50 chars) |
| `DEBUG` | ✅ | `True` for dev, `False` for production |
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `REDIS_URL` | ✅ | Redis URL for Django cache |
| `CELERY_BROKER_URL` | ✅ | Redis URL for Celery broker |
| `CELERY_RESULT_BACKEND` | ✅ | Redis URL for Celery results |
| `USE_S3` | ✅ | `True` to use MinIO/S3 storage |
| `MINIO_ACCESS_KEY` | ✅ | MinIO access key |
| `MINIO_SECRET_KEY` | ✅ | MinIO secret key |
| `MINIO_BUCKET_NAME` | ✅ | MinIO bucket name |
| `MINIO_ENDPOINT_URL` | ✅ | Internal MinIO URL (backend to MinIO) |
| `MINIO_PUBLIC_URL` | ✅ | Public MinIO URL (browser to MinIO) |
| `AI_BASE_URL` | ✅ | AI service base URL |
| `AI_POLL_INTERVAL_SECONDS` | — | Polling interval in seconds (default: 30) |
| `AI_POLL_MAX_RETRIES` | — | Max poll attempts (default: 60 = 30 min) |
| `SENDGRID_API_KEY` | — | SendGrid API key |
| `SENDGRID_FROM_EMAIL` | — | Verified sender email address |
| `SENDGRID_FROM_NAME` | — | Display name for outgoing emails |
| `SENDGRID_REPLY_TO_EMAIL` | — | Reply-to email address |
| `CV_LOGO_PATH` | — | Path to logo image used in CV PDF |

### AI Service (`AI/.env`)

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | ✅ | OpenAI API key |
| `REDIS_URL` | ✅ | Redis URL (uses separate DB from backend) |
| `APP_BASE_URL` | ✅ | AI service's own base URL |

---

## API Reference

Full interactive documentation available at [http://localhost:8000/api/docs/](http://localhost:8000/api/docs/).

### Authentication — `/api/auth/`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/register/` | Public | Create account |
| POST | `/login/` | Public | Login, sets HttpOnly JWT cookies |
| POST | `/logout/` | Required | Logout, clears cookies |
| POST | `/token/refresh/` | Public | Refresh access token from cookie |
| GET | `/me/` | Required | Current user profile |
| PATCH | `/profile/update/` | Required | Update profile photo, name, etc. |
| POST | `/password/update/` | Required | Change password |
| POST | `/forgot-password/` | Public | Request password reset OTP |
| POST | `/verify-otp/` | Public | Verify OTP code |
| POST | `/reset-password/` | Public | Set new password |
| GET | `/dashboard/` | Superuser | System-wide statistics |
| GET | `/activity/` | Superuser | Activity log and notifications |
| POST | `/activity/mark-read/` | Superuser | Mark notifications as read |

### Candidates — `/api/candidates/`

| Method | Endpoint | Description |
|---|---|---|
| POST | `/upload/` | Bulk CV upload (multipart, up to 1000 files) |
| GET | `/` | Paginated candidate list with filters |
| GET | `/<id>/` | Full candidate detail |
| PATCH | `/<id>/update/` | Edit candidate fields, triggers PDF regen if needed |
| DELETE | `/<id>/delete/` | Delete candidate and MinIO files (async) |
| POST | `/<id>/rewrite/` | Trigger AI CV rewrite |
| GET | `/<id>/rewrite/status/` | Poll rewrite completion |
| GET | `/<id>/nearby-organizations/` | Organizations within radius of candidate |
| GET | `/<id>/nearby-contacts/` | School contacts within radius (filterable by phase, job title) |
| POST | `/<id>/send-to-contacts/` | Email candidate profile to up to 1000 contacts |
| GET | `/send-status/<task_id>/` | Poll email send task result |
| GET | `/batches/` | Paginated list of upload batches |
| GET | `/batches/<id>/` | Batch progress and status |
| DELETE | `/batches/<id>/delete/` | Delete batch and all candidates |

### Organizations — `/api/organizations/`

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Paginated list with filters (phase, town, postcode, geo radius) |
| POST | `/` | Create organization (auto-geocodes postcode) |
| GET | `/<id>/` | Organization detail with nested contacts |
| PATCH | `/<id>/` | Update organization (re-geocodes if address changes) |
| DELETE | `/<id>/` | Delete organization and all contacts |
| POST | `/import/` | Bulk import from Excel file (background task) |
| POST | `/import/contacts/` | Bulk contact import from Excel |
| GET | `/import/status/<task_id>/` | Poll import task result |
| GET | `/contacts/` | All contacts across all organizations |
| GET | `/<id>/contacts/` | Contacts for a specific organization |
| POST | `/<id>/contacts/` | Add contact to organization |
| GET | `/contacts/<id>/` | Contact detail |
| PATCH | `/contacts/<id>/` | Update contact |
| DELETE | `/contacts/<id>/` | Delete contact |

---

## Background Tasks

Four dedicated Celery queues prevent task interference under heavy load:

| Queue | Container | Tasks | Concurrency |
|---|---|---|---|
| `default` | `celery_default` | CV processing, geocoding, emails, Excel import | 4 |
| `polling` | `celery_polling` | AI result polling, rewrite polling | 4 |
| `pdf` | `celery_pdf` | PDF generation (memory-intensive) | 2 |
| `beat` | `celery_beat` | Periodic tasks (batch sync every 5 min) | — |

### Task Chain — Full CV Lifecycle

```
[Upload] BulkCVUploadView
    └─ process_cv_task (default)
           POST cv_url to AI → get task_id
           └─ poll_ai_result_task (polling)
                  polls every 30s → extracts data → downloads profile photo
                  └─ generate_enhanced_cv_pdf_task (pdf)
                         WeasyPrint → PDF → MinIO
                         └─ send_availability_email_task (default)
                                SendGrid → candidate inbox
```

### Periodic Tasks

`sync_batch_counts` runs every 5 minutes via Celery Beat. It recalculates batch `processed_count` and `failed_count` from actual candidate statuses — fixing batches stuck at 0% when workers crash mid-task.

---

## Key Design Decisions

**Separate Celery queues** — PDF generation is slow and memory-heavy. Mixing it with polling tasks in one queue would cause AI polling to timeout. Each queue has appropriate concurrency for its workload.

**Two MinIO clients** — Pre-signed URLs must be signed with the public URL (what the browser sees). File operations use the internal container URL for speed. `minio_utils.py` maintains two separate boto3 clients to handle this correctly.

**On-demand geocoding for candidates** — Geocoding 1000+ candidates on upload would take 20+ minutes. Coordinates are populated only when a geo filter is first requested, then cached permanently on the candidate record.

**`is_regeneration` flag on PDF generation** — When a user edits `job_titles`, `name`, or `location`, the PDF is automatically regenerated. The flag skips incrementing `batch.processed_count` and sending the availability email again on regeneration.

**Short PostgreSQL `conn_max_age`** — Under heavy concurrent load, long-lived DB connections are killed by PostgreSQL, causing `SSL connection closed unexpectedly` in workers. Set to 60 seconds to force fresh reconnections.

**ActivityLog 1000-entry limit** — The system is operated by a single user. Rather than a complex notification infrastructure, a simple DB-backed activity log with automatic pruning at 1000 entries covers all needs efficiently.

**JWT in HttpOnly cookies** — Access and refresh tokens are stored in HttpOnly cookies, not localStorage. This prevents XSS attacks from stealing tokens. The custom `CookieJWTAuthentication` class falls back to the `Authorization` header for Swagger UI compatibility.

---

## Postman Collection

`Backend/Backend.postman_collection.json` contains all endpoints pre-configured for local testing. Import it into Postman and set `base_url` to `http://localhost:8000`.

---

## License

MIT License — see [LICENSE](LICENSE) for details.