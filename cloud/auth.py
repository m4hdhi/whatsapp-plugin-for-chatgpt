"""Small persistent authorization store for an operator-managed hosted pilot.

Opaque credentials are hashed at rest. No message content belongs in this store.
Only one ASGI worker is supported (the application engines own SQLite state).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
import time


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt=None):
    if not isinstance(password, str) or not 14 <= len(password) <= 256:
        raise ValueError("Use a password of 14–256 characters.")
    salt = salt or secrets.token_hex(16)
    result = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600000).hex()
    return f"pbkdf2-sha256$600000${salt}${result}"


def password_ok(password, encoded):
    if not isinstance(password, str) or len(password) > 256:
        return False
    try:
        scheme, rounds, salt, expected = encoded.split("$")
        if scheme != "pbkdf2-sha256" or rounds != "600000":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600000).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, AttributeError):
        return False


def challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


class AuthStore:
    def __init__(self, path, clock=time.time):
        self.clock = clock
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS tickets (
                hash TEXT PRIMARY KEY, kind TEXT NOT NULL, user TEXT NOT NULL,
                family TEXT NOT NULL, payload TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS throttle (
                key TEXT PRIMARY KEY, started REAL NOT NULL, count INTEGER NOT NULL);
        """)

    def issue(self, kind, payload, ttl, user="", family=""):
        token = secrets.token_urlsafe(48)
        with self.lock, self.db:
            self.db.execute("INSERT INTO tickets VALUES (?,?,?,?,?,?)",
                            (digest(token), kind, user, family, json.dumps(payload), self.clock() + ttl))
        return token

    def get(self, token, kind, consume=False):
        if not token or len(token) > 512:
            return None
        with self.lock, self.db:
            row = self.db.execute("SELECT payload,expires FROM tickets WHERE hash=? AND kind=?",
                                  (digest(token), kind)).fetchone()
            if not row or row[1] <= self.clock():
                return None
            if consume:
                self.db.execute("DELETE FROM tickets WHERE hash=?", (digest(token),))
            return json.loads(row[0])

    def revoke(self, token):
        with self.lock, self.db:
            row = self.db.execute("SELECT family FROM tickets WHERE hash=?", (digest(token),)).fetchone()
            if row and row[0]:
                self.db.execute("DELETE FROM tickets WHERE family=?", (row[0],))
            else:
                self.db.execute("DELETE FROM tickets WHERE hash=?", (digest(token),))

    def revoke_user_grants(self, user):
        with self.lock, self.db:
            self.db.execute("DELETE FROM tickets WHERE user=? AND kind IN ('code','access','refresh','used-refresh','pending')", (user,))

    def tokens(self, grant, family=None):
        family = family or secrets.token_urlsafe(24)
        grant = {**grant, "family": family}
        return {"access_token": self.issue("access", grant, 900, grant["user"], family),
                "refresh_token": self.issue("refresh", grant, 30 * 86400, grant["user"], family),
                "token_type": "Bearer", "expires_in": 900, "scope": "whatsapp:read"}

    def rotate(self, token, client_id, resource):
        with self.lock:
            grant = self.get(token, "refresh")
            if not grant:
                if self.get(token, "used-refresh"):
                    self.revoke(token)  # Replay revokes the entire grant family.
                return None
            if grant["client_id"] != client_id or grant["resource"] != resource:
                return None
            with self.db:
                self.db.execute("UPDATE tickets SET kind='used-refresh' WHERE hash=?", (digest(token),))
            return self.tokens(grant, grant["family"])

    def allow(self, key, limit, seconds):
        key = digest(key)
        with self.lock, self.db:
            now = self.clock()
            self.db.execute("DELETE FROM tickets WHERE expires<=?", (now,))
            self.db.execute("DELETE FROM throttle WHERE started<?", (now - 3600,))
            row = self.db.execute("SELECT started,count FROM throttle WHERE key=?", (key,)).fetchone()
            if row and row[0] > now - seconds:
                if row[1] >= limit:
                    return False
                self.db.execute("UPDATE throttle SET count=count+1 WHERE key=?", (key,))
            else:
                self.db.execute("INSERT OR REPLACE INTO throttle VALUES (?,?,1)", (key, now))
        return True

    def close(self):
        self.db.close()
