"""
Authentication module.

Real password hashing (werkzeug's generate_password_hash / check_password_hash
-- salted, uses PBKDF2/scrypt depending on werkzeug version) and Flask-Login
session management.

NOTE ON SCOPE: this is hackathon-appropriate auth -- correct password hashing,
proper session cookies via Flask-Login, but no email verification, no
password reset flow, no rate limiting on login attempts. Be upfront about
that if asked -- it's a normal, expected scope cut, not a hidden flaw.
"""

import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

DB_FILE = "verimed.db"


class User(UserMixin):
    """Flask-Login needs an object with .id, .is_authenticated, etc. -- UserMixin provides those."""
    def __init__(self, id, name, email):
        self.id = str(id)
        self.name = name
        self.email = email


def init_users_table():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def create_user(name: str, email: str, password: str) -> "User | None":
    """Returns the created User, or None if the email is already registered."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email = ?", (email.lower().strip(),))
    if cur.fetchone():
        conn.close()
        return None  # email already taken

    password_hash = generate_password_hash(password)
    now = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (name.strip(), email.lower().strip(), password_hash, now),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return User(user_id, name.strip(), email.lower().strip())


def verify_login(email: str, password: str) -> "User | None":
    """Returns the User if email+password match, else None."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None
    if not check_password_hash(row["password_hash"], password):
        return None

    return User(row["id"], row["name"], row["email"])


def get_user_by_id(user_id: str) -> "User | None":
    """Required by Flask-Login's user_loader callback."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None
    return User(row["id"], row["name"], row["email"])


if __name__ == "__main__":
    # Quick manual test -- run: python auth.py
    import os
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)  # clean slate for this test only

    init_users_table()

    user = create_user("Test User", "test@example.com", "correct-password-123")
    print(f"Created user: {user.name} ({user.email}), id={user.id}")

    dupe = create_user("Someone Else", "test@example.com", "whatever")
    print(f"Duplicate email rejected: {dupe is None}")

    good_login = verify_login("test@example.com", "correct-password-123")
    print(f"Correct password login: {'SUCCESS' if good_login else 'FAILED'}")

    bad_login = verify_login("test@example.com", "wrong-password")
    print(f"Wrong password login: {'correctly rejected' if bad_login is None else 'SECURITY BUG'}")

    fetched = get_user_by_id(user.id)
    print(f"Fetched by id: {fetched.name} ({fetched.email})")
