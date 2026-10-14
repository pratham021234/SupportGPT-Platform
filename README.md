# SupportGPT AI — Platform Foundation & Architecture

> **Enterprise AI Support Quality, Verification, Human Approvals & Reliability Platform**

SupportGPT AI is a commercial-grade, multi-tenant B2B SaaS platform engineered for customer support automation with factual grounding, claim-level response verification, policy-enforced human approvals, and forensic AI failure investigation.

---

## 1. Phase 00 Status: Foundation & Standards

Phase 00 establishes the greenfield architecture, clean layer boundaries, and engineering standards:
- **Architecture**: Modular Monolith with clean domain boundaries (`api/`, `core/`, `db/`, `models/`, `schemas/`, `ai/`).
- **Backend Transport**: Python 3.11, FastAPI, Pydantic v2 Settings with strict production validation.
- **Data & Migrations**: PostgreSQL 16 authoritative datastore, SQLAlchemy 2.0 (asyncio + asyncpg), Alembic async migration pipeline.
- **Frontend Presentation**: Next.js (App Router), React 19, TypeScript (Strict Mode), Tailwind CSS, live system diagnostics console.
- **Quality Gates**: Pytest automated test suite (Unit, API, Integration), Ruff linter, and GitHub Actions CI workflow.
- **Honest Metrics**: Zero fabricated business counts, fake tickets, fake revenue, or simulated accuracy.

---

## 2. Prerequisites & Environment

- **Operating System**: Windows 10/11 64-bit (PowerShell 5.1+ or PowerShell 7+)
- **Python**: 3.11.x (Verify via `py -3.11 --version` or `py -0`)
- **Node.js**: v20.x or v22+ (`node -v`)
- **Git**: 2.40+ (`git --version`)
- **Docker Desktop**: Optional for host development, required for running containerized PostgreSQL 16, Redis 7, and Qdrant.

---

## 3. Quick Start (Windows PowerShell)

Open a Windows PowerShell terminal in `D:\SupportGPT-Platform`.

### Step 1: Copy Environment Templates
```powershell
Copy-Item .env.example .env
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env.local
```

### Step 2: Set Up Backend Virtual Environment
```powershell
# Create Python 3.11 virtual environment
py -3.11 -m venv backend\.venv

# Upgrade pip and install development dependencies
.\backend\.venv\Scripts\python.exe -m pip install --upgrade pip
.\backend\.venv\Scripts\pip.exe install -e "./backend[dev]"
```

### Step 3: Set Up Frontend Dependencies
```powershell
cd frontend
cmd /c npm install
cd ..
```

### Step 4: (Optional) Start Infrastructure Containers
If Docker Desktop is running on your machine:
```powershell
docker compose up -d postgres redis qdrant
```

---

## 4. Running the Development Servers

### Terminal 1: Backend API (FastAPI)
```powershell
cd D:\SupportGPT-Platform\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
- API Base: `http://localhost:8000`
- Interactive OpenAPI Docs: `http://localhost:8000/docs`
- Process Liveness Probe: `http://localhost:8000/healthz`
- Infrastructure Readiness Probe: `http://localhost:8000/readyz`

### Terminal 2: Frontend UI (Next.js)
```powershell
cd D:\SupportGPT-Platform\frontend
cmd /c npm run dev
```
- Web Application Shell: `http://localhost:3000`
- Live System Diagnostics Console: `http://localhost:3000/system`

---

## 5. Verification & Testing

### Run Backend Automated Tests (Pytest)
```powershell
cd D:\SupportGPT-Platform
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -v
```

### Run Backend Lint & Formatting (Ruff)
```powershell
.\backend\.venv\Scripts\python.exe -m ruff check backend/
```

### Run Frontend Strict Type-Checking
```powershell
cd D:\SupportGPT-Platform\frontend
cmd /c npm run type-check
```

### Run Frontend Production Build
```powershell
cmd /c npm run build
```

---

## 6. Architecture & Governance Documentation

- [Architecture & Standards](docs/ARCHITECTURE.md): Layer boundaries, request flows, and architectural invariants.
- [Development Guide](docs/DEVELOPMENT.md): Detailed workflow, PowerShell execution policies, and migration guides.
- [Security Architecture](docs/SECURITY.md): Active protections, production validation, and future security milestones.
- [Testing & Quality Gates](docs/TESTING.md): Test categories, execution rules, and current test results.
- [Phased Product Roadmap](docs/ROADMAP.md): Detailed milestones for Phases 00 through 09.
- [ADR 0001: Modular Monolith](docs/adr/0001-modular-monolith-architecture.md)
- [ADR 0002: Async SQLAlchemy & Alembic](docs/adr/0002-async-sqlalchemy-and-alembic.md)
- [ADR 0003: Multi-Tenancy & PostgreSQL RLS Strategy](docs/adr/0003-tenant-isolation-and-rls-strategy.md)
