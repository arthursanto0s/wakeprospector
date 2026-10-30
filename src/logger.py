"""Structured logging and audit trail recorder for Wake Prospector."""

import json
import logging
from typing import Any, Dict, Optional

from src.config import LOG_FILE_PATH
from src.models import AuditLogEntry, generate_log_id, utc_now_iso

# Configure root logger for the package
_logger = logging.getLogger("wake_prospector")
_logger.setLevel(logging.INFO)

# File handler
if not _logger.handlers:
    _file_handler = logging.FileHandler(LOG_FILE_PATH, encoding="utf-8")
    _formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _file_handler.setFormatter(_formatter)
    _logger.addHandler(_file_handler)


def get_logger() -> logging.Logger:
    """Returns the package logger."""
    return _logger


def log_event(
    event_type: str,
    lead_id: Optional[str] = None,
    from_status: Optional[str] = None,
    to_status: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> AuditLogEntry:
    """Creates a structured AuditLogEntry, logs it via the standard logger, and returns it.

    Can be persisted to SQLite via DatabaseManager.insert_audit_log().
    """
    entry = AuditLogEntry(
        id=generate_log_id(),
        lead_id=lead_id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        details=details or {},
        timestamp=utc_now_iso(),
    )

    msg_parts = [f"EVENT={event_type}"]
    if lead_id:
        msg_parts.append(f"LEAD={lead_id}")
    if from_status or to_status:
        msg_parts.append(f"TRANSITION=({from_status} -> {to_status})")
    if details:
        msg_parts.append(f"DETAILS={json.dumps(details, ensure_ascii=False)}")

    _logger.info(" | ".join(msg_parts))
    return entry
