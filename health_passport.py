"""
Health Passport module -- v2, per-user.

Every table now has a user_id foreign key, so each logged-in user has their
own private passport, surgery history, vaccination record, and uploaded
reports.

QR CODE DESIGN CHANGE FROM v1:
v1 encoded the passport data as raw text directly in the QR code. That only
works if the scanning device has software that can parse that specific text
format. v2 instead gives each user a random, unguessable share_token and
encodes a URL (e.g. http://yourhost/emergency/<token>) in the QR code. Any
phone camera can scan it and it opens directly in a browser -- no app
needed on the doctor's side. That page is intentionally read-only and shows
only emergency-relevant fields, not the full account or uploaded documents.
"""

import sqlite3
import io
import os
import secrets
from datetime import datetime

import qrcode

DB_FILE = "verimed.db"
UPLOAD_DIR = "uploads/medical_reports"


def init_passport_table():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS health_passport (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            full_name TEXT,
            blood_group TEXT,
            date_of_birth TEXT,
            allergies TEXT,
            chronic_conditions TEXT,
            current_medicines TEXT,
            emergency_contact_name TEXT,
            emergency_contact_phone TEXT,
            share_token TEXT UNIQUE,
            updated_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS surgeries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            year TEXT,
            description TEXT,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS vaccinations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            vaccine_name TEXT,
            month TEXT,
            year TEXT,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS medical_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT,
            stored_path TEXT,
            category TEXT,
            month TEXT,
            year TEXT,
            uploaded_at TEXT
        )
    """)

    conn.commit()
    conn.close()
    os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Core passport (personal details)
# ---------------------------------------------------------------------------

def save_passport(user_id: int, data: dict):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id, share_token FROM health_passport WHERE user_id = ?", (user_id,))
    existing = cur.fetchone()
    now = datetime.now().isoformat(timespec="seconds")

    if existing:
        cur.execute("""
            UPDATE health_passport SET
                full_name=?, blood_group=?, date_of_birth=?, allergies=?,
                chronic_conditions=?, current_medicines=?,
                emergency_contact_name=?, emergency_contact_phone=?, updated_at=?
            WHERE user_id=?
        """, (
            data["full_name"], data["blood_group"], data["date_of_birth"],
            data["allergies"], data["chronic_conditions"], data["current_medicines"],
            data["emergency_contact_name"], data["emergency_contact_phone"], now,
            user_id,
        ))
    else:
        share_token = secrets.token_urlsafe(16)
        cur.execute("""
            INSERT INTO health_passport
            (user_id, full_name, blood_group, date_of_birth, allergies, chronic_conditions,
             current_medicines, emergency_contact_name, emergency_contact_phone, share_token, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, data["full_name"], data["blood_group"], data["date_of_birth"],
            data["allergies"], data["chronic_conditions"], data["current_medicines"],
            data["emergency_contact_name"], data["emergency_contact_phone"], share_token, now,
        ))
    conn.commit()
    conn.close()


def get_passport(user_id: int) -> dict | None:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM health_passport WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_passport_by_token(share_token: str) -> dict | None:
    """Used by the public /emergency/<token> view -- no auth required."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM health_passport WHERE share_token = ?", (share_token,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Surgeries
# ---------------------------------------------------------------------------

def add_surgery(user_id: int, year: str, description: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO surgeries (user_id, year, description, created_at) VALUES (?, ?, ?, ?)",
        (user_id, year, description, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()


def get_surgeries(user_id: int) -> list[dict]:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM surgeries WHERE user_id = ? ORDER BY year DESC", (user_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def delete_surgery(user_id: int, surgery_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM surgeries WHERE id = ? AND user_id = ?", (surgery_id, user_id))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Vaccinations
# ---------------------------------------------------------------------------

def add_vaccination(user_id: int, vaccine_name: str, month: str, year: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO vaccinations (user_id, vaccine_name, month, year, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, vaccine_name, month, year, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()


def get_vaccinations(user_id: int) -> list[dict]:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM vaccinations WHERE user_id = ? ORDER BY year DESC", (user_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def delete_vaccination(user_id: int, vaccination_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM vaccinations WHERE id = ? AND user_id = ?", (vaccination_id, user_id))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Medical report uploads
# ---------------------------------------------------------------------------

def save_report_file(user_id: int, file_storage, category: str, month: str, year: str) -> dict:
    """
    file_storage: a Flask FileStorage object (from request.files[...]).
    Saves the file to disk under a per-user subfolder and records metadata.
    """
    user_folder = os.path.join(UPLOAD_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)

    # Prefix with a timestamp so same-named uploads don't collide
    safe_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{file_storage.filename}"
    stored_path = os.path.join(user_folder, safe_name)
    file_storage.save(stored_path)

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO medical_reports (user_id, filename, stored_path, category, month, year, uploaded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, file_storage.filename, stored_path, category, month, year,
        datetime.now().isoformat(timespec="seconds"),
    ))
    conn.commit()
    report_id = cur.lastrowid
    conn.close()

    return {
        "id": report_id, "filename": file_storage.filename, "category": category,
        "month": month, "year": year,
    }


def get_reports(user_id: int) -> list[dict]:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM medical_reports WHERE user_id = ? ORDER BY year DESC, month DESC",
        (user_id,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_report_by_id(user_id: int, report_id: int) -> dict | None:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM medical_reports WHERE id = ? AND user_id = ?", (report_id, user_id))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_report(user_id: int, report_id: int):
    report = get_report_by_id(user_id, report_id)
    if report and os.path.exists(report["stored_path"]):
        os.remove(report["stored_path"])

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM medical_reports WHERE id = ? AND user_id = ?", (report_id, user_id))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# QR code -- now encodes a URL to the public emergency view, not raw text
# ---------------------------------------------------------------------------

def generate_qr_code(share_token: str, base_url: str) -> bytes:
    """
    base_url: e.g. "http://localhost:5000" -- passed in from app.py using
    request.host_url so it works correctly whether running locally or deployed.
    """
    emergency_url = f"{base_url.rstrip('/')}/emergency/{share_token}"

    qr = qrcode.QRCode(version=None, box_size=8, border=3)
    qr.add_data(emergency_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0F6FFF", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


if __name__ == "__main__":
    # Quick manual test -- run: python health_passport.py
    import os as _os
    if _os.path.exists(DB_FILE):
        _os.remove(DB_FILE)

    init_passport_table()

    save_passport(1, {
        "full_name": "Jane Doe", "blood_group": "O+", "date_of_birth": "01-01-1995",
        "allergies": "Penicillin", "chronic_conditions": "Asthma",
        "current_medicines": "Ventolin inhaler", "emergency_contact_name": "John Doe",
        "emergency_contact_phone": "+91-9999999999",
    })
    passport = get_passport(1)
    print(f"Saved passport for: {passport['full_name']}, share_token={passport['share_token']}")

    add_surgery(1, "2019", "Appendectomy")
    add_vaccination(1, "COVID-19 Booster", "March", "2024")
    print(f"Surgeries: {get_surgeries(1)}")
    print(f"Vaccinations: {get_vaccinations(1)}")

    by_token = get_passport_by_token(passport["share_token"])
    print(f"Fetched via public token: {by_token['full_name']}")

    qr_bytes = generate_qr_code(passport["share_token"], "http://localhost:5000")
    print(f"QR code generated: {len(qr_bytes)} bytes")