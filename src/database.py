"""Local SQLite persistence layer for Wake Prospector.

Implements storage, transactions, queries, state transition enforcement,
and audit logs with zero external dependencies.
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, List, Optional

from src.config import (
    ALLOWED_PIPELINE_TRANSITIONS,
    DB_PATH,
    PipelineStatus,
    WebsiteStatus,
)
from src.deduplication import normalize_phone
from src.logger import get_logger, log_event
from src.models import (
    AuditLogEntry,
    Conversation,
    Lead,
    Source,
    utc_now_iso,
)

logger = get_logger()


class DatabaseManager:
    """Manages SQLite connection and deterministic operations for Wake Prospector."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.init_db()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provides a transactional connection with foreign keys enabled."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        """Initializes database tables and indexes if they do not exist."""
        with self.get_connection() as conn:
            # 1. Leads table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    id TEXT PRIMARY KEY,
                    business_name TEXT NOT NULL,
                    category TEXT,
                    city TEXT,
                    neighborhood TEXT,
                    normalized_phone TEXT,
                    website TEXT,
                    website_status TEXT NOT NULL,
                    pipeline_status TEXT NOT NULL,
                    discard_reason TEXT,
                    data_json TEXT NOT NULL,
                    discovered_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_leads_business_name ON leads(business_name);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_leads_city ON leads(city);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_leads_pipeline_status ON leads(pipeline_status);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_leads_website_status ON leads(website_status);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_leads_normalized_phone ON leads(normalized_phone);"
            )

            # 2. Sources table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY,
                    lead_id TEXT,
                    url TEXT,
                    title TEXT,
                    source_type TEXT NOT NULL,
                    accessed_at TEXT NOT NULL,
                    supports_json TEXT NOT NULL,
                    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sources_lead_id ON sources(lead_id);"
            )

            # 3. Conversations table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    lead_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    text TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    notes TEXT,
                    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversations_lead_id ON conversations(lead_id);"
            )

            # 4. Audit logs table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id TEXT PRIMARY KEY,
                    lead_id TEXT,
                    event_type TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT,
                    details_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_logs_lead_id ON audit_logs(lead_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type ON audit_logs(event_type);"
            )

    def save_lead(self, lead: Lead) -> Lead:
        """Inserts or updates a Lead record and its associated sources atomically."""
        lead.updated_at = utc_now_iso()

        # Primary normalized phone from contacts if available
        norm_phone = ""
        for c in lead.contacts:
            if c.phone:
                p = normalize_phone(c.phone)
                if p:
                    norm_phone = p
                    break

        data_json = json.dumps(lead.to_dict(), ensure_ascii=False)

        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO leads (
                    id, business_name, category, city, neighborhood,
                    normalized_phone, website, website_status,
                    pipeline_status, discard_reason, data_json,
                    discovered_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    business_name=excluded.business_name,
                    category=excluded.category,
                    city=excluded.city,
                    neighborhood=excluded.neighborhood,
                    normalized_phone=excluded.normalized_phone,
                    website=excluded.website,
                    website_status=excluded.website_status,
                    pipeline_status=excluded.pipeline_status,
                    discard_reason=excluded.discard_reason,
                    data_json=excluded.data_json,
                    updated_at=excluded.updated_at;
                """,
                (
                    lead.id,
                    lead.business.name,
                    lead.business.category,
                    lead.business.city,
                    lead.business.neighborhood,
                    norm_phone,
                    lead.business.website,
                    (
                        lead.business.website_status.value
                        if isinstance(lead.business.website_status, WebsiteStatus)
                        else str(lead.business.website_status)
                    ),
                    (
                        lead.pipeline_status.value
                        if isinstance(lead.pipeline_status, PipelineStatus)
                        else str(lead.pipeline_status)
                    ),
                    lead.discard_reason,
                    data_json,
                    lead.discovered_at,
                    lead.updated_at,
                ),
            )

            # Upsert sources
            for source in lead.sources:
                conn.execute(
                    """
                    INSERT INTO sources (id, lead_id, url, title, source_type, accessed_at, supports_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        url=excluded.url,
                        title=excluded.title,
                        source_type=excluded.source_type,
                        accessed_at=excluded.accessed_at,
                        supports_json=excluded.supports_json;
                    """,
                    (
                        source.id,
                        lead.id,
                        source.url,
                        source.title,
                        (
                            source.source_type.value
                            if hasattr(source.source_type, "value")
                            else str(source.source_type)
                        ),
                        source.accessed_at,
                        json.dumps(source.supports, ensure_ascii=False),
                    ),
                )

        audit_entry = log_event(
            event_type="LEAD_SAVED",
            lead_id=lead.id,
            details={
                "business_name": lead.business.name,
                "city": lead.business.city,
                "status": str(lead.pipeline_status),
            },
        )
        self.insert_audit_log(audit_entry)
        return lead

    def get_lead(self, lead_id: str) -> Optional[Lead]:
        """Retrieves a single Lead by its ID."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT data_json FROM leads WHERE id = ?", (lead_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            data = json.loads(row["data_json"])
            return Lead.from_dict(data)

    def list_leads(
        self,
        pipeline_status: Optional[PipelineStatus] = None,
        city: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[Lead]:
        """Lists leads with optional filters."""
        query = "SELECT data_json FROM leads WHERE 1=1"
        params: List[str] = []

        if pipeline_status:
            val = (
                pipeline_status.value
                if isinstance(pipeline_status, PipelineStatus)
                else str(pipeline_status)
            )
            query += " AND pipeline_status = ?"
            params.append(val)

        if city:
            query += " AND LOWER(city) = LOWER(?)"
            params.append(city)

        if category:
            query += " AND LOWER(category) LIKE LOWER(?)"
            params.append(f"%{category}%")

        query += " ORDER BY updated_at DESC"

        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            return [Lead.from_dict(json.loads(r["data_json"])) for r in rows]

    def update_lead_status(
        self,
        lead_id: str,
        new_status: PipelineStatus,
        reason: Optional[str] = None,
        user_confirmed: bool = False,
        lead: Optional[Lead] = None,
    ) -> Lead:
        """Updates a lead's pipeline status, strictly enforcing transition rules,

        mandatory discard reasons, and human confirmation for WhatsApp sends.
        """
        if lead is None:
            lead = self.get_lead(lead_id)
        if not lead:
            raise ValueError(f"Lead not found: {lead_id}")

        old_status = lead.pipeline_status
        target_status = (
            new_status
            if isinstance(new_status, PipelineStatus)
            else PipelineStatus(new_status)
        )

        # Rule check: cannot transition to same status
        if old_status == target_status:
            return lead

        # Rule check: allowed transitions
        allowed = ALLOWED_PIPELINE_TRANSITIONS.get(old_status, set())
        if target_status not in allowed:
            raise ValueError(
                f"Invalid pipeline status transition from {old_status.value} to {target_status.value}."
            )

        # Rule check: human sending control on WhatsApp (V1)
        if target_status == PipelineStatus.CONTACTED and not user_confirmed:
            raise ValueError(
                "Transition to CONTACTED requires explicit user confirmation that the message was sent manually."
            )

        # Rule check: discarding requires mandatory reason
        if target_status == PipelineStatus.DISCARDED and not reason:
            raise ValueError(
                "Transition to DISCARDED requires a mandatory discard reason."
            )

        lead.pipeline_status = target_status
        if target_status == PipelineStatus.DISCARDED:
            lead.discard_reason = reason
        elif reason:
            # If reason provided for another status change, retain it or note in opportunity
            lead.opportunity.uncertainties.append(f"Status update note: {reason}")

        lead = self.save_lead(lead)

        audit_entry = log_event(
            event_type="PIPELINE_STATUS_CHANGE",
            lead_id=lead.id,
            from_status=old_status.value,
            to_status=target_status.value,
            details={"reason": reason or "", "user_confirmed": user_confirmed},
        )
        self.insert_audit_log(audit_entry)
        return lead

    def save_source(self, source: Source, lead_id: Optional[str] = None) -> Source:
        """Saves a standalone source or links it to a lead."""
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sources (id, lead_id, url, title, source_type, accessed_at, supports_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    url=excluded.url,
                    title=excluded.title,
                    source_type=excluded.source_type,
                    accessed_at=excluded.accessed_at,
                    supports_json=excluded.supports_json;
                """,
                (
                    source.id,
                    lead_id,
                    source.url,
                    source.title,
                    (
                        source.source_type.value
                        if hasattr(source.source_type, "value")
                        else str(source.source_type)
                    ),
                    source.accessed_at,
                    json.dumps(source.supports, ensure_ascii=False),
                ),
            )
        return source

    def list_sources(self, lead_id: Optional[str] = None) -> List[Source]:
        """Lists sources, optionally filtered by lead_id."""
        query = "SELECT * FROM sources"
        params = []
        if lead_id:
            query += " WHERE lead_id = ?"
            params.append(lead_id)
        query += " ORDER BY accessed_at DESC"

        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            results = []
            for r in rows:
                results.append(
                    Source(
                        id=r["id"],
                        url=r["url"],
                        title=r["title"],
                        source_type=r["source_type"],
                        accessed_at=r["accessed_at"],
                        supports=json.loads(r["supports_json"]),
                    )
                )
            return results

    def save_conversation(self, conv: Conversation) -> Conversation:
        """Stores a conversation message."""
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO conversations (id, lead_id, timestamp, direction, text, intent, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    direction=excluded.direction,
                    text=excluded.text,
                    intent=excluded.intent,
                    notes=excluded.notes;
                """,
                (
                    conv.id,
                    conv.lead_id,
                    conv.timestamp,
                    conv.direction,
                    conv.text,
                    (
                        conv.intent.value
                        if hasattr(conv.intent, "value")
                        else str(conv.intent)
                    ),
                    conv.notes,
                ),
            )
        audit_entry = log_event(
            event_type="CONVERSATION_SAVED",
            lead_id=conv.lead_id,
            details={"intent": str(conv.intent), "direction": conv.direction},
        )
        self.insert_audit_log(audit_entry)
        return conv

    def list_conversations(self, lead_id: str) -> List[Conversation]:
        """Retrieves all conversation records for a given lead."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM conversations WHERE lead_id = ? ORDER BY timestamp ASC",
                (lead_id,),
            )
            rows = cursor.fetchall()
            return [
                Conversation(
                    id=r["id"],
                    lead_id=r["lead_id"],
                    timestamp=r["timestamp"],
                    direction=r["direction"],
                    text=r["text"],
                    intent=r["intent"],
                    notes=r["notes"],
                )
                for r in rows
            ]

    def insert_audit_log(self, entry: AuditLogEntry) -> None:
        """Records an entry in the audit_logs table."""
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (id, lead_id, event_type, from_status, to_status, details_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING;
                """,
                (
                    entry.id,
                    entry.lead_id,
                    entry.event_type,
                    entry.from_status,
                    entry.to_status,
                    json.dumps(entry.details, ensure_ascii=False),
                    entry.timestamp,
                ),
            )

    def list_audit_logs(
        self, lead_id: Optional[str] = None
    ) -> List[AuditLogEntry]:
        """Lists audit log entries, optionally filtered by lead_id."""
        query = "SELECT * FROM audit_logs"
        params = []
        if lead_id:
            query += " WHERE lead_id = ?"
            params.append(lead_id)
        query += " ORDER BY timestamp DESC"

        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            return [
                AuditLogEntry(
                    id=r["id"],
                    lead_id=r["lead_id"],
                    event_type=r["event_type"],
                    from_status=r["from_status"],
                    to_status=r["to_status"],
                    details=json.loads(r["details_json"]),
                    timestamp=r["timestamp"],
                )
                for r in rows
            ]

    def delete_lead(self, lead_id: str) -> bool:
        """Deletes a lead and its dependent records (via CASCADE)."""
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
            return cursor.rowcount > 0
