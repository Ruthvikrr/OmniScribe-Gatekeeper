import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "database" / "vault.db"


def init_db():
    """Create database and tables if they do not exist."""
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS token_vault (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            token_key TEXT NOT NULL,
            real_value TEXT NOT NULL,
            token_type TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS session_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            input_type TEXT,
            redaction_count INTEGER,
            tickets_generated INTEGER,
            stubs_generated INTEGER,
            input_hash TEXT,
            created_at TEXT NOT NULL
        )
    """
    )
    try:
        c.execute("ALTER TABLE session_logs ADD COLUMN input_hash TEXT")
    except sqlite3.OperationalError:
        pass
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service TEXT NOT NULL UNIQUE,
            access_token TEXT NOT NULL,
            refresh_token TEXT,
            token_type TEXT,
            scope TEXT,
            expires_at TEXT,
            extra_data TEXT,
            connected_at TEXT NOT NULL
        )
    """
    )
    c.execute("""
        CREATE TABLE IF NOT EXISTS sync_settings (
            service TEXT PRIMARY KEY,
            auto_push INTEGER DEFAULT 1,
            push_brief INTEGER DEFAULT 1,
            push_tickets INTEGER DEFAULT 1,
            push_stubs INTEGER DEFAULT 1,
            updated_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS push_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            service TEXT,
            status TEXT,
            detail TEXT,
            url TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def store_token_mapping(session_id: str, token_key: str, real_value: str, token_type: str):
    """Store a token to real value mapping locally."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO token_vault (session_id, token_key, real_value, token_type, created_at)
        VALUES (?, ?, ?, ?, ?)
    """,
        (session_id, token_key, real_value, token_type, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_vault_contents(session_id: str) -> list:
    """Retrieve all token mappings for a session without exposing real values."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT token_key, token_type, created_at FROM token_vault
        WHERE session_id = ? ORDER BY id
    """,
        (session_id,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def get_all_sessions() -> list:
    """Return all sessions ordered by most recent first."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT session_id, input_type, redaction_count,
               tickets_generated, stubs_generated, created_at
        FROM session_logs
        ORDER BY created_at DESC
        LIMIT 50
    """
    )
    rows = c.fetchall()
    conn.close()
    return rows


def get_session_vault(session_id: str) -> list:
    """Return vault entries for a specific session."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT token_key, token_type, created_at
        FROM token_vault WHERE session_id = ?
        ORDER BY id
    """,
        (session_id,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def save_oauth_token(service: str, access_token: str, refresh_token: str = None,
                     token_type: str = "Bearer", scope: str = None,
                     expires_at: str = None, extra_data: dict = None):
    if isinstance(scope, (list, tuple)):
        scope = ",".join(str(s) for s in scope)
    elif scope is not None:
        scope = str(scope)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO oauth_tokens
        (service, access_token, refresh_token, token_type, scope,
         expires_at, extra_data, connected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(service) DO UPDATE SET
            access_token=excluded.access_token,
            refresh_token=excluded.refresh_token,
            token_type=excluded.token_type,
            scope=excluded.scope,
            expires_at=excluded.expires_at,
            extra_data=excluded.extra_data,
            connected_at=excluded.connected_at
    """, (service, access_token, refresh_token, token_type, scope,
          expires_at, json.dumps(extra_data or {}), datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_oauth_token(service: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM oauth_tokens WHERE service = ?", (service,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    cols = ["id", "service", "access_token", "refresh_token", "token_type",
            "scope", "expires_at", "extra_data", "connected_at"]
    return dict(zip(cols, row))


def delete_oauth_token(service: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM oauth_tokens WHERE service = ?", (service,))
    conn.commit()
    conn.close()


def get_all_oauth_status() -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT service, connected_at FROM oauth_tokens")
    rows = c.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}


def get_session_by_hash(input_hash: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT session_id FROM session_logs WHERE input_hash = ?", (input_hash,))
        row = c.fetchone()
    except sqlite3.OperationalError:
        row = None
    conn.close()
    return row[0] if row else None


def log_session(
    session_id: str,
    input_type: str,
    redaction_count: int,
    tickets_count: int,
    stubs_count: int,
    input_hash: str = None
):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO session_logs
        (session_id, input_type, redaction_count, tickets_generated, stubs_generated, input_hash, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (
            session_id,
            input_type,
            redaction_count,
            tickets_count,
            stubs_count,
            input_hash,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def delete_session(session_id: str):
    """Delete all database logs and vault mappings for a session."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM session_logs WHERE session_id = ?", (session_id,))
    c.execute("DELETE FROM token_vault WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()


def get_sync_settings(service: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM sync_settings WHERE service = ?", (service,))
    row = c.fetchone()
    conn.close()
    if not row:
        return {"service": service, "auto_push": 1, "push_brief": 1,
                "push_tickets": 1, "push_stubs": 1}
    cols = ["service","auto_push","push_brief","push_tickets","push_stubs","updated_at"]
    return dict(zip(cols, row))

def save_sync_setting(service: str, key: str, value: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"""
        INSERT INTO sync_settings (service, {key}, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(service) DO UPDATE SET {key}=excluded.{key},
        updated_at=excluded.updated_at
    """, (service, value, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def log_push(session_id: str, service: str, status: str,
             detail: str = "", url: str = ""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO push_log (session_id, service, status, detail, url, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (session_id, service, status, detail, url, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_push_logs(session_id: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT service, status, detail, url, created_at
        FROM push_log WHERE session_id = ?
        ORDER BY id
    """, (session_id,))
    rows = c.fetchall()
    conn.close()
    return rows


def refresh_jira_token() -> str | None:
    """Refreshes the Jira OAuth 2.0 access token using the stored refresh token."""
    import os
    import requests
    from dotenv import load_dotenv
    load_dotenv()

    tok = get_oauth_token("jira")
    if not tok or not tok.get("refresh_token"):
        return None

    client_id = os.getenv("JIRA_CLIENT_ID")
    client_secret = os.getenv("JIRA_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None

    payload = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": tok["refresh_token"]
    }

    try:
        response = requests.post(
            "https://auth.atlassian.com/oauth/token",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            new_access_token = data.get("access_token")
            new_refresh_token = data.get("refresh_token") or tok["refresh_token"]
            
            # Preserve existing extra data (e.g. cloud_id)
            extra_data = {}
            if tok.get("extra_data"):
                try:
                    extra_data = json.loads(tok["extra_data"])
                except Exception:
                    pass

            save_oauth_token(
                service="jira",
                access_token=new_access_token,
                refresh_token=new_refresh_token,
                scope=data.get("scope") or tok.get("scope"),
                extra_data=extra_data
            )
            return new_access_token
        else:
            print(f"Jira token refresh failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Error refreshing Jira token: {e}")
        return None


init_db()
