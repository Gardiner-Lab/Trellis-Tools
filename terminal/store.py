"""
What the HPC Terminal keeps: the HPC machines an administrator has allowed, with the host key each
was found with, and each member's saved connections (who they log in as, on which machine).

Never a password, a one-time code or a private key: those are typed into the terminal when asked,
passed on to the machine and forgotten.
"""
import sqlite3
import time
import uuid
from pathlib import Path
from typing import List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS hosts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    hostname TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 22,
    host_key TEXT NOT NULL,          -- the machine's public key, OpenSSH format, as found when added
    fingerprint TEXT NOT NULL,       -- its SHA256 fingerprint, to compare with the machine's own
    note TEXT NOT NULL DEFAULT '',
    added_by TEXT NOT NULL,
    added_at TEXT NOT NULL,
    UNIQUE (hostname, port)
);
CREATE TABLE IF NOT EXISTS connections (
    id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    host_id TEXT NOT NULL REFERENCES hosts (id) ON DELETE CASCADE,
    username TEXT NOT NULL,
    label TEXT NOT NULL,
    tmux INTEGER NOT NULL DEFAULT 1, -- keep the work in tmux on the machine, to come back to
    record INTEGER NOT NULL DEFAULT 1, -- write the transcript to the member's notebook when a session ends
    created_at TEXT NOT NULL,
    last_used TEXT
);
CREATE INDEX IF NOT EXISTS connections_by_owner ON connections (owner);
"""


def _now() -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S')


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as conn:
            conn.executescript(SCHEMA)
            columns = {r[1] for r in conn.execute('PRAGMA table_info(connections)')}
            if 'record' not in columns:          # a database from before recording
                conn.execute('ALTER TABLE connections ADD COLUMN record INTEGER NOT NULL DEFAULT 1')

    def _db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        return conn

    # --- hosts (administrators) ---

    def hosts(self) -> List[dict]:
        with self._db() as conn:
            return [dict(r) for r in conn.execute('SELECT * FROM hosts ORDER BY name COLLATE NOCASE')]

    def host(self, host_id: str) -> Optional[dict]:
        with self._db() as conn:
            row = conn.execute('SELECT * FROM hosts WHERE id = ?', (host_id,)).fetchone()
        return dict(row) if row else None

    def add_host(self, name: str, hostname: str, port: int, host_key: str, fingerprint: str, note: str,
                 by: str) -> dict:
        host_id = uuid.uuid4().hex
        with self._db() as conn:
            conn.execute('INSERT INTO hosts (id, name, hostname, port, host_key, fingerprint, note, added_by, added_at) '
                         'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                         (host_id, name, hostname, port, host_key, fingerprint, note, by, _now()))
        return self.host(host_id)

    def set_host_key(self, host_id: str, host_key: str, fingerprint: str) -> None:
        with self._db() as conn:
            conn.execute('UPDATE hosts SET host_key = ?, fingerprint = ? WHERE id = ?', (host_key, fingerprint, host_id))

    def remove_host(self, host_id: str) -> bool:
        with self._db() as conn:
            return conn.execute('DELETE FROM hosts WHERE id = ?', (host_id,)).rowcount > 0

    # --- connections (each member's own) ---

    def connections(self, owner: str) -> List[dict]:
        with self._db() as conn:
            return [dict(r) for r in conn.execute(
                'SELECT c.*, h.name AS host_name, h.hostname, h.port FROM connections c JOIN hosts h ON h.id = c.host_id '
                'WHERE c.owner = ? ORDER BY c.label COLLATE NOCASE', (owner,))]

    def connection(self, conn_id: str, owner: str) -> Optional[dict]:
        """A connection, only when it is the member's own."""
        with self._db() as conn:
            row = conn.execute(
                'SELECT c.*, h.name AS host_name, h.hostname, h.port, h.host_key FROM connections c '
                'JOIN hosts h ON h.id = c.host_id WHERE c.id = ? AND c.owner = ?', (conn_id, owner)).fetchone()
        return dict(row) if row else None

    def add_connection(self, owner: str, host_id: str, username: str, label: str, tmux: bool,
                       record: bool = True) -> dict:
        conn_id = uuid.uuid4().hex
        with self._db() as conn:
            conn.execute('INSERT INTO connections (id, owner, host_id, username, label, tmux, record, created_at) '
                         'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                         (conn_id, owner, host_id, username, label, int(tmux), int(record), _now()))
        return self.connection(conn_id, owner)

    def update_connection(self, conn_id: str, owner: str, **fields) -> Optional[dict]:
        allowed = {k: v for k, v in fields.items() if k in ('username', 'label', 'tmux', 'record') and v is not None}
        if allowed:
            sets = ', '.join(f'{k} = ?' for k in allowed)
            with self._db() as conn:
                conn.execute(f'UPDATE connections SET {sets} WHERE id = ? AND owner = ?',
                             (*[int(v) if k in ('tmux', 'record') else v for k, v in allowed.items()], conn_id, owner))
        return self.connection(conn_id, owner)

    def used(self, conn_id: str) -> None:
        with self._db() as conn:
            conn.execute('UPDATE connections SET last_used = ? WHERE id = ?', (_now(), conn_id))

    def remove_connection(self, conn_id: str, owner: str) -> bool:
        with self._db() as conn:
            return conn.execute('DELETE FROM connections WHERE id = ? AND owner = ?', (conn_id, owner)).rowcount > 0
