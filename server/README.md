# OpenAgent Backend

FastAPI backend for the OpenAgent multi-tenant management platform.

## Tech Stack

- **Framework**: FastAPI + Python 3.11+
- **ORM**: SQLAlchemy 2.0 (async) + Alembic
- **Database**: PostgreSQL 15+ (asyncpg)
- **Validation**: Pydantic v2

## Quick Start

```bash
# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Make sure PostgreSQL is running and create the database
createdb openagent

# 4. Run dev server (migrations run automatically on startup)
uvicorn app.main:app --reload --port 5001
```

## Environment

- `APP_ENV=dev` (default) → loads `.env.dev`
- `APP_ENV=production` → loads `.env.production`

```bash
APP_ENV=production uvicorn app.main:app
```

## Project Structure

```
server/
├── app/
│   ├── main.py           # App entry & lifespan
│   ├── configs/           # Settings (Pydantic)
│   ├── routers/v1/        # Route layer
│   ├── schemas/           # Request/response schemas
│   ├── services/          # Business logic
│   ├── repositories/      # Data access
│   ├── models/            # SQLAlchemy models
│   ├── db/                # DB session & migration
│   └── core/              # Exceptions & security
├── migrations/            # Alembic migrations
├── tests/
└── requirements.txt
```

## Generate Migration

```bash
alembic revision --autogenerate -m "description"
```
