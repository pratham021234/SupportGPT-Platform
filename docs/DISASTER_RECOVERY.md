# SupportGPT AI Platform - Disaster Recovery & Business Continuity Plan

## 1. Objectives & Critical Metrics

| Objective | Target Window | Basis & Verification Evidence |
|---|---|---|
| **Recovery Point Objective (RPO)** | **Provisional: 1 Hour** | Hourly automated PostgreSQL backups with custom compression (`-F c`) and WAL archiving. Maximum acceptable data loss is 1 hour of customer support ticket edits. |
| **Recovery Time Objective (RTO)** | **Provisional: 30 Minutes** | Time required to provision container host, restore verified database backup, and reindex vectors. Actual single-node database restore measured at < 5 seconds for test databases. |

> [!NOTE]
> These recovery objectives are explicitly provisional until validated by an automated, scheduled offsite replication test in staging or production infrastructure.

---

## 2. Authoritative Data Hierarchy

To prevent state corruption or unrecoverable split-brain scenarios, SupportGPT enforces a strict hierarchy of data persistence:

1. **Tier 1 (Authoritative Primary Source of Truth): PostgreSQL 16**
   - Contains all organizations, users, credentials, tickets, messages, knowledge base metadata, document revisions, and raw extracted chunk content.
   - Protected by Row-Level Security and transaction boundaries.
   - **Must be backed up with cryptographic checksums.**
2. **Tier 2 (Authoritative Binary Object Storage): Disk Volume / S3**
   - Stores raw uploaded documents (`.pdf`, `.md`, `.txt`) using opaque UUID storage keys (`storage_key`).
   - If destroyed, active document versions cannot be re-extracted, but existing chunks already in PostgreSQL remain functional for retrieval.
3. **Tier 3 (Derived / Reproducible Vector Store): Qdrant v1.12**
   - Stores dense vector embeddings and minimal provenance metadata (`chunk_id`, `organization_id`).
   - **Is NOT the authoritative source for document content or tenant ownership.**
   - If Qdrant data is lost or corrupted, the entire vector collection can be rebuilt from Tier 1 chunks via `scripts/reindex_vectors.py`.
4. **Tier 4 (Ephemeral Operational State): Redis 7**
   - Stores temporary ingestion queues, cache keys, and rate-limiting counters.
   - Ephemeral: if Redis crashes or is wiped, in-flight jobs are reclaimed from PostgreSQL by worker lease timeouts.

---

## 3. Automated Backup Architecture

### 3.1: Execution Workflow (`scripts/backup_database.py`)
```
[PostgreSQL Database]
       │
       ▼
[pg_dump -F c] (Custom Compressed Archive)
       │
       ├─────────────────────────────────┐
       ▼                                 ▼
[Compute SHA-256 Digest]      [Collect Environment Metadata]
       │                                 │
       ▼                                 ▼
[.dump.sha256 File]           [.dump.meta.json Receipt]
```

### 3.2: Operational Invocation
```bash
# Executed via scheduled cron (hourly or daily)
python scripts/backup_database.py \
  --backup-dir /app/backups \
  --retention-days 14 \
  --db-url postgresql://supportgpt_backup:SECRET@postgres:5432/supportgpt_prod
```

### 3.3: Backup Artifact Anatomy
For each backup run, three coupled artifacts are produced:
- `supportgpt_db_20261022_091340.dump`: Binary custom-format database archive suitable for parallel `pg_restore`.
- `supportgpt_db_20261022_091340.dump.sha256`: Hexadecimal SHA-256 digest computed immediately after dump generation.
- `supportgpt_db_20261022_091340.dump.meta.json`: JSON metadata receipt capturing file size, environment, version, and timestamps.

---

## 4. Disaster Recovery & Restoration Procedures

### Scenario A: Complete Host Loss or Regional Outage

#### Phase 1: Infrastructure Provisioning
1. Provision a fresh virtual machine or container host with Docker Engine 26+.
2. Clone repository:
   ```bash
   git clone https://github.com/pratham021234/SupportGPT-Platform.git /opt/supportgpt
   cd /opt/supportgpt
   ```
3. Inject production environment variables into `.env.production` from secrets vault.
4. Retrieve the latest verified database backup `.dump` and `.sha256` files from offsite object storage (e.g. AWS S3 Glacier / GCS).

#### Phase 2: Integrity Verification & Database Restoration
1. Launch PostgreSQL and Redis:
   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.production up -d postgres redis
   ```
2. Verify backup checksum integrity:
   ```bash
   python scripts/restore_database.py /path/to/backup.dump --verify-only
   ```
3. Execute restore into PostgreSQL:
   ```bash
   python scripts/restore_database.py /path/to/backup.dump --target-db supportgpt_prod
   ```

#### Phase 3: Vector Store Recovery (`scripts/reindex_vectors.py`)
1. Start Qdrant container:
   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.production up -d qdrant
   ```
2. Reconstruct collections and reindex all active document chunks:
   ```bash
   python scripts/reindex_vectors.py --batch-size 50
   ```
   The script queries all `document_chunks` joined to `document_versions` in `indexed` status, generates normalized embeddings, and upserts them into Qdrant with payload indexes.

#### Phase 4: Launch Platform Services
```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d
```
Verify platform readiness:
```bash
curl -f http://localhost:8000/readyz
```

---

## 5. Actual Restoration Test Results

During Phase 09 testing, an end-to-end disaster recovery test was executed against real PostgreSQL 16:
- **Backup Execution:** Real `pg_dump` executed on `supportgpt_db` producing `supportgpt_db_20261022_091340.dump` (195,373 bytes).
- **Checksum Calculation:** SHA-256 `172bd4a9898d0aec5a3fb572ac85d8b9ab203db82de2e9ce4b069493ef49127b` written to `.sha256`.
- **Integrity Verification:** Tested `restore_database.py --verify-only` -> Verified SHA-256 match cleanly.
- **Tampering Detection:** Modified byte in backup -> `restore_database.py` caught mismatch and aborted with `ValueError`.
- **Database Restoration:** Real `pg_restore` executed into `supportgpt_test_db` -> All tables, indexes, and constraints restored with exit code 0.
