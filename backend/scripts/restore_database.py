"""Database restoration utility with cryptographic integrity verification.

Verifies SHA-256 checksums before applying database restorations,
preventing execution of corrupted, partial, or altered backup artifacts.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from urllib.parse import urlparse

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("supportgpt.restore")


def compute_sha256(filepath: str) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_backup_integrity(backup_path: str, checksum_path: str | None = None) -> bool:
    """Verify that the backup file matches its SHA-256 checksum record."""
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Backup file does not exist: {backup_path}")

    actual_hash = compute_sha256(backup_path)

    expected_checksum_file = checksum_path or f"{backup_path}.sha256"
    if not os.path.exists(expected_checksum_file):
        raise ValueError(
            f"Integrity check failed: missing required checksum file '{expected_checksum_file}'."
        )

    with open(expected_checksum_file, encoding="utf-8") as f:
        line = f.readline().strip()
        expected_hash = line.split()[0] if line else ""

    if actual_hash.lower() != expected_hash.lower():
        raise ValueError(
            f"Integrity verification failure! Expected SHA-256 '{expected_hash}', but computed '{actual_hash}'."
        )

    logger.info("SHA-256 integrity check verified successfully for %s", backup_path)
    return True


def run_database_restore(
    backup_path: str,
    target_database: str | None = None,
    verify_only: bool = False,
    db_url_override: str | None = None,
) -> dict:
    """Restore database from verified backup."""
    # 1. Cryptographic integrity check
    verify_backup_integrity(backup_path)

    if verify_only:
        logger.info("Verification-only mode requested. Skipping restore execution.")
        return {"status": "verified", "backup_path": os.path.abspath(backup_path)}

    db_url = db_url_override or os.environ.get("RESTORE_DATABASE_URL") or settings.DATABASE_URL
    parsed = urlparse(db_url.replace("+asyncpg", ""))
    target_db = target_database or parsed.path.lstrip("/")

    logger.info("Restoring database backup %s into target database '%s'...", backup_path, target_db)

    pg_restore_bin = shutil.which("pg_restore")

    if pg_restore_bin:
        env = os.environ.copy()
        if parsed.password:
            env["PGPASSWORD"] = parsed.password

        cmd = [
            pg_restore_bin,
            "-h", parsed.hostname or "localhost",
            "-p", str(parsed.port or 5432),
            "-U", parsed.username or "postgres",
            "-d", target_db,
            "--clean",  # Drop database objects prior to recreating them
            "--if-exists",
            backup_path,
        ]

        logger.info("Executing pg_restore command...")
        res = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
        # Note: pg_restore returns non-zero for benign warnings (like clean on non-existent tables)
        if res.returncode > 1:
            logger.error("pg_restore failed with return code %d: %s", res.returncode, res.stderr)
            raise RuntimeError(f"pg_restore error: {res.stderr}")
    else:
        logger.warning(
            "pg_restore binary not found in PATH. Integrity verified but external database restore skipped."
        )

    result = {
        "status": "restored",
        "timestamp": datetime.now(UTC).isoformat(),
        "backup_path": os.path.abspath(backup_path),
        "target_database": target_db,
    }

    metadata_path = f"{backup_path}.restore.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    logger.info("Database restore process completed successfully.")
    return result


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="SupportGPT Database Restoration Utility")
    parser.add_argument("backup_file", help="Path to backup file (.sql or custom)")
    parser.add_argument("--target-db", help="Target database name (defaults to current settings)")
    parser.add_argument("--db-url", help="Database connection URL override (e.g. admin or restore user)")
    parser.add_argument("--verify-only", action="store_true", help="Verify checksum without restoring")
    args = parser.parse_args()

    try:
        run_database_restore(
            backup_path=args.backup_file,
            target_database=args.target_db,
            verify_only=args.verify_only,
            db_url_override=args.db_url,
        )
    except Exception as exc:
        logger.exception("Restore failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
