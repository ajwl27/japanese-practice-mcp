import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator

import httpx

BASE_URL = "https://api.wanikani.com/v2"


class StalenessError(RuntimeError):
    """Raised when fresh data cannot be obtained and stale is unacceptable."""


@dataclass
class WaniKaniClient:
    token: str
    timeout: float = 30.0

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Wanikani-Revision": "20170710",
        }

    def get_pages(self, url: str) -> Iterator[dict]:
        with httpx.Client(timeout=self.timeout, headers=self._headers()) as client:
            next_url: str | None = url
            while next_url:
                resp = client.get(next_url)
                resp.raise_for_status()
                payload = resp.json()
                yield payload
                next_url = (payload.get("pages") or {}).get("next_url")


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _mark_synced(conn: sqlite3.Connection, key: str) -> None:
    conn.execute(
        "INSERT INTO wk_cache_meta (key, value, updated_at) VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
        (f"{key}_synced_at", _now_iso()),
    )


def last_synced_at(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM wk_cache_meta WHERE key = ?", (f"{key}_synced_at",)
    ).fetchone()
    return row["value"] if row else None


def sync_subjects(conn: sqlite3.Connection, client: WaniKaniClient) -> int:
    """Fetch all subjects, upsert into wk_subjects. Returns # rows upserted."""
    n = 0
    for page in client.get_pages(f"{BASE_URL}/subjects"):
        for item in page.get("data", []):
            sid = item["id"]
            obj = item["object"]
            data = item.get("data", {})
            characters = data.get("characters")
            slug = data.get("slug")
            level = data.get("level")
            meanings = [m["meaning"] for m in data.get("meanings", [])]
            readings = [r["reading"] for r in data.get("readings", [])]
            conn.execute(
                """
                INSERT INTO wk_subjects
                    (id, object, characters, slug, level, meanings, readings, data_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    object=excluded.object,
                    characters=excluded.characters,
                    slug=excluded.slug,
                    level=excluded.level,
                    meanings=excluded.meanings,
                    readings=excluded.readings,
                    data_json=excluded.data_json,
                    updated_at=excluded.updated_at
                """,
                (
                    sid, obj, characters, slug, level,
                    json.dumps(meanings, ensure_ascii=False),
                    json.dumps(readings, ensure_ascii=False),
                    json.dumps(item, ensure_ascii=False),
                    item.get("data_updated_at", _now_iso()),
                ),
            )
            n += 1
    _mark_synced(conn, "subjects")
    return n


def sync_assignments(conn: sqlite3.Connection, client: WaniKaniClient) -> int:
    """Fetch all unlocked assignments, replace wk_assignments. Returns # rows."""
    conn.execute("DELETE FROM wk_assignments")
    n = 0
    for page in client.get_pages(f"{BASE_URL}/assignments?unlocked=true"):
        for item in page.get("data", []):
            aid = item["id"]
            data = item.get("data", {})
            conn.execute(
                """
                INSERT INTO wk_assignments
                    (id, subject_id, srs_stage, data_json, cached_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    aid, data["subject_id"], data["srs_stage"],
                    json.dumps(item, ensure_ascii=False), _now_iso(),
                ),
            )
            n += 1
    _mark_synced(conn, "assignments")
    return n


def assignments_age_seconds(conn: sqlite3.Connection) -> float | None:
    ts = last_synced_at(conn, "assignments")
    if not ts:
        return None
    delta = datetime.now(tz=timezone.utc) - datetime.fromisoformat(ts)
    return delta.total_seconds()


def subjects_age_days(conn: sqlite3.Connection) -> float | None:
    ts = last_synced_at(conn, "subjects")
    if not ts:
        return None
    delta = datetime.now(tz=timezone.utc) - datetime.fromisoformat(ts)
    return delta.total_seconds() / 86400.0


def ensure_subjects_fresh(
    conn: sqlite3.Connection, client: WaniKaniClient, max_age_days: float
) -> tuple[bool, str | None]:
    """Refresh subjects if stale or absent. Returns (is_fresh, staleness_note_or_none)."""
    age = subjects_age_days(conn)
    if age is None or age > max_age_days:
        try:
            sync_subjects(conn, client)
            return True, None
        except (httpx.HTTPError, httpx.HTTPStatusError) as e:
            if age is None:
                raise StalenessError(
                    f"WaniKani subjects have never been synced and the API is unreachable: {e}"
                ) from e
            return False, f"WaniKani API unreachable; serving subjects cache from {age:.1f}d ago"
    return True, None


def ensure_assignments_fresh(
    conn: sqlite3.Connection, client: WaniKaniClient, ttl_seconds: float
) -> tuple[bool, str | None]:
    age = assignments_age_seconds(conn)
    if age is None or age > ttl_seconds:
        try:
            sync_assignments(conn, client)
            return True, None
        except (httpx.HTTPError, httpx.HTTPStatusError) as e:
            if age is None:
                raise StalenessError(
                    f"WaniKani assignments have never been synced and the API is unreachable: {e}"
                ) from e
            return False, f"WaniKani API unreachable; serving assignments cache from {age/60:.1f}m ago"
    return True, None
