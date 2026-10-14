"""SQLite acceptance journal: a durable claim precedes every paid POST."""
from contextlib import contextmanager
import json
import os
import sqlite3
import time
from pathlib import Path


class JournalError(RuntimeError):
    pass


class Journal:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        self.path = self.directory / 'requests.sqlite3'
        with self.connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS requests (
                request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, state TEXT NOT NULL,
                provider TEXT, model TEXT, task_id TEXT, snapshot TEXT, result_json TEXT,
                result_files TEXT, report_json TEXT NOT NULL DEFAULT '{}',
                reserved_cost REAL NOT NULL DEFAULT 0, currency TEXT, updated REAL NOT NULL)''')
            db.execute('CREATE TABLE IF NOT EXISTS health (provider TEXT PRIMARY KEY, until REAL NOT NULL)')
            db.execute('BEGIN IMMEDIATE')
            if 'identity' not in {column[1] for column in db.execute('PRAGMA table_info(health)')}:
                db.execute('ALTER TABLE health ADD COLUMN identity TEXT')
        os.chmod(self.path, 0o600)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, request_id):
        with self.connection() as db:
            row = db.execute('SELECT * FROM requests WHERE request_id=?', (request_id,)).fetchone()
        return dict(row) if row else None

    def has_legacy_submissions(self):
        # An old Bridge prompt contained a configuration digest. A new natural
        # prompt cannot prove it differs from an already paid legacy operation.
        with self.connection() as db:
            for row in db.execute("SELECT snapshot FROM requests WHERE state!='ready' AND snapshot IS NOT NULL"):
                if json.loads(row['snapshot']).get('identity_version') != 2:
                    return True
        return False

    def begin(self, request_id, fingerprint):
        with self.connection() as db:
            db.execute('INSERT OR IGNORE INTO requests(request_id,fingerprint,state,updated) VALUES(?,?,?,?)',
                       (request_id, fingerprint, 'ready', time.time()))
        row = self.get(request_id)
        if row['fingerprint'] != fingerprint:
            raise JournalError('Request id conflicts with different inputs; use a new nonce')
        return row

    def reserve(self, request_id, provider, model, snapshot, cost, currency, total_cap):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT state FROM requests WHERE request_id=?', (request_id,)).fetchone()
            if not row or row['state'] != 'ready':
                raise JournalError('Request already claimed; no duplicate submission')
            if db.execute('SELECT 1 FROM requests WHERE reserved_cost>0 AND currency!=? LIMIT 1', (currency,)).fetchone():
                raise JournalError('Budget currency differs from previous reservations; use the same accounting currency')
            if total_cap is not None:
                for previous in db.execute("SELECT snapshot FROM requests WHERE state!='ready' AND reserved_cost=0 AND snapshot IS NOT NULL"):
                    previous_model = json.loads(previous['snapshot']).get('model', {})
                    if previous_model and previous_model.get('price_upper_bound') is None:
                        raise JournalError('Previous accepted/uncertain cost is unknown; a finite cumulative budget cannot be guaranteed')
            total = db.execute('SELECT COALESCE(SUM(reserved_cost),0) FROM requests').fetchone()[0]
            if total_cap is not None and total + cost > total_cap + 1e-9:
                raise JournalError('Configured cumulative estimated-cost limit exceeded')
            db.execute('''UPDATE requests SET state='submitting',provider=?,model=?,snapshot=?,reserved_cost=?,
                          currency=?,updated=? WHERE request_id=?''',
                       (provider, model, json.dumps(snapshot), cost, currency, time.time(), request_id))

    def mark(self, request_id, state, *, task_id=None, result=None, files=None, report=None):
        sources = {
            'submitting': ('submitting',), 'accepted': ('submitting', 'accepted'),
            'uncertain': ('submitting', 'uncertain'),
            'result_ready': ('submitting', 'accepted', 'result_ready'),
            'failed': ('accepted', 'failed'), 'completed': ('result_ready', 'completed'),
        }[state]
        placeholders = ','.join('?' for _ in sources)
        with self.connection() as db:
            db.execute(f'''UPDATE requests SET state=?,task_id=COALESCE(?,task_id),
                result_json=COALESCE(?,result_json),result_files=COALESCE(?,result_files),
                report_json=COALESCE(?,report_json),updated=? WHERE request_id=? AND state IN ({placeholders})''',
                (state, task_id, json.dumps(result) if result is not None else None,
                 json.dumps(files) if files is not None else None,
                 json.dumps(report) if report is not None else None, time.time(), request_id, *sources))

    def reject(self, request_id, report):
        with self.connection() as db:
            db.execute("UPDATE requests SET state='ready',reserved_cost=0,report_json=?,updated=? WHERE request_id=?",
                       (json.dumps(report), time.time(), request_id))

    def cooldown(self, provider, seconds, identity=None):
        with self.connection() as db:
            db.execute('INSERT OR REPLACE INTO health(provider,until,identity) VALUES(?,?,?)',
                       (provider, time.time() + seconds, identity))

    def available(self, provider, identity=None):
        with self.connection() as db:
            row = db.execute('SELECT until,identity FROM health WHERE provider=?', (provider,)).fetchone()
        return row is None or row['until'] <= time.time() or (identity is not None and row['identity'] is not None and row['identity'] != identity)
