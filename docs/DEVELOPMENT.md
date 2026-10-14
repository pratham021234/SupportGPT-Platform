# SupportGPT AI — Local Development Guide

## 1. Prerequisites & Environment Verification

### System Requirements
- **Windows 10/11 64-bit** (PowerShell 5.1+ or PowerShell 7+)
- **Node.js**: v20.x or v22+ (`node -v`)
- **Python**: 3.11.x (Verify via `py -3.11 --version` or `py -0`)
- **Git**: 2.40+ (`git --version`)
- **Docker Desktop** (Optional for containerized mode, required for live PostgreSQL/Redis/Qdrant containers)

### PowerShell Execution Policy Configuration
If running PowerShell scripts (like virtualenv activation) encounters execution policy restrictions, configure the current process scope:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

---

## 2. Initial Setup

### Step 1: Clone or Navigate to Workspace
```powershell
cd D:\SupportGPT-Platform
```

### Step 2: Environment Configuration
Copy the provided environment templates:
```powershell
# Root Docker Compose environment
Copy-Item .env.example .env

# Backend environment
Copy-Item backend\.env.example backend\.env

# Frontend environment
Copy-Item frontend\.env.example frontend\.env.local
```

### Step 3: Backend Python Environment
Create an isolated Python 3.11 virtual environment and install dependencies in editable mode:
```powershell
# Create virtual environment using the Python launcher
py -3.11 -m venv backend\.venv

# Upgrade pip and install development dependencies
.\backend\.venv\Scripts\python.exe -m pip install --upgrade pip
.\backend\.venv\Scripts\pip.exe install -e "./backend[dev]"
```

### Step 4: Frontend Node Environment
```powershell
cd frontend
npm install
cd ..
```

---

## 3. Running Infrastructure (Docker Compose)

Start the supporting datastores (PostgreSQL, Redis, Qdrant):
```powershell
docker compose up -d postgres redis qdrant
```

Check health of the infrastructure services:
```powershell
docker compose ps
```

---

## 4. Running the Applications

### Starting the Backend (FastAPI)
Run the uvicorn development server with live reload:
```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
The API is available at: `http://localhost:8000`  
Interactive OpenAPI documentation: `http://localhost:8000/docs`

### Starting the Frontend (Next.js)
In a separate PowerShell terminal:
```powershell
cd frontend
npm run dev
```
The application shell is available at: `http://localhost:3000`

---

## 5. Database Migrations (Alembic)

### Run Migrations to Latest Schema:
```powershell
cd backend
.\.venv\Scripts\alembic.exe upgrade head
```

### Generate Migration SQL Offline (Without Live Database):
```powershell
cd backend
.\.venv\Scripts\alembic.exe upgrade 0001_initial_foundation --sql
```

### Create a New Migration Revision:
```powershell
cd backend
.\.venv\Scripts\alembic.exe revision --autogenerate -m "describe_migration_purpose"
```

---

## 6. Code Quality & Formatting

### Backend Linting and Formatting:
```powershell
cd backend
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format .
```

### Frontend Type-Checking and Linting:
```powershell
cd frontend
npm run type-check
npm run lint
```
