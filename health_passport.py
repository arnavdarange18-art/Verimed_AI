"""
Health Passport module.

Stores a user's personal health profile locally (SQLite) and generates a
QR code encoding a compact emergency-readable summary of it.

NOTE: This is a hackathon-scope, single-user local demo -- no multi-user auth,
no encryption at rest. If you present this, be upfront that a production
version would need proper auth + encryption (HIPAA-style) -- judges respect
that honesty far more than pretending it's production-secure.
"""

import sqlite3
import json
import qrcode
import io

DB_FILE = "verimed.db"


def init_passport_table():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS health_passport (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT,
            blood_group TEXT,
            date_of_birth TEXT,
            allergies TEXT,
            chronic_conditions TEXT,
            current_medicines TEXT,
            emergency_contact_name TEXT,
            emergency_contact_phone TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_passport(data: dict):
    """Upserts the single local passport record (id=1, since this is single-user demo)."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM health_passport LIMIT 1")
    existing = cur.fetchone()

    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")

    if existing:
        cur.execute("""
            UPDATE health_passport SET
                full_name=?, blood_group=?, date_of_birth=?, allergies=?,
                chronic_conditions=?, current_medicines=?,
                emergency_contact_name=?, emergency_contact_phone=?, updated_at=?
            WHERE id=?
        """, (
            data["full_name"], data["blood_group"], data["date_of_birth"],
            data["allergies"], data["chronic_conditions"], data["current_medicines"],
            data["emergency_contact_name"], data["emergency_contact_phone"], now,
            existing[0],
        ))
    else:
        cur.execute("""
            INSERT INTO health_passport
            (full_name, blood_group, date_of_birth, allergies, chronic_conditions,
             current_medicines, emergency_contact_name, emergency_contact_phone, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["full_name"], data["blood_group"], data["date_of_birth"],
            data["allergies"], data["chronic_conditions"], data["current_medicines"],
            data["emergency_contact_name"], data["emergency_contact_phone"], now,
        ))
    conn.commit()
    conn.close()


def get_passport() -> dict | None:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM health_passport LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def generate_qr_code(passport: dict) -> bytes:
    """
    Generates a QR code encoding a compact emergency summary.
    Returns PNG image bytes ready to display in Streamlit.
    """
    summary = (
        f"VERIMED HEALTH PASSPORT\n"
        f"Name: {passport.get('full_name', '')}\n"
        f"Blood Group: {passport.get('blood_group', '')}\n"
        f"DOB: {passport.get('date_of_birth', '')}\n"
        f"Allergies: {passport.get('allergies', 'None listed')}\n"
        f"Chronic Conditions: {passport.get('chronic_conditions', 'None listed')}\n"
        f"Current Medicines: {passport.get('current_medicines', 'None listed')}\n"
        f"Emergency Contact: {passport.get('emergency_contact_name', '')} "
        f"({passport.get('emergency_contact_phone', '')})"
    )

    qr = qrcode.QRCode(version=None, box_size=8, border=3)
    qr.add_data(summary)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0F6FFF", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
