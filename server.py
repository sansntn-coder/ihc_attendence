#!/usr/bin/env python3

import csv
import hashlib
import hmac
import io
import json
import os
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "attendance.db"
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DB_BACKEND = "postgres" if DATABASE_URL else "sqlite"
SESSION_COOKIE = "ihc_session"
EMPLOYEE_SESSION_COOKIE = "ihc_employee_session"
HOST = os.environ.get("BIND_HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
STANDARD_SHIFT_HOURS = 8.0
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}


def dict_row_factory(cursor, row):
    return {cursor.description[idx][0]: row[idx] for idx in range(len(cursor.description))}


def now_utc():
    return datetime.utcnow()


def today_key():
    return datetime.now().strftime("%Y-%m-%d")


def month_key(date_key):
    return date_key[:7]


def pbkdf2_hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return f"{salt}${derived.hex()}"


def verify_password(password, stored_hash):
    salt, digest = stored_hash.split("$", 1)
    expected = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000).hex()
    return hmac.compare_digest(expected, digest)


def postgres_sql(sql):
    return sql.replace("?", "%s")


def get_connection():
    if DB_BACKEND == "sqlite":
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = dict_row_factory
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    import psycopg
    from psycopg.rows import dict_row

    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    return conn


def db_execute(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(postgres_sql(sql) if DB_BACKEND == "postgres" else sql, params)
        return cur


def db_fetchone(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(postgres_sql(sql) if DB_BACKEND == "postgres" else sql, params)
        return cur.fetchone()


def db_fetchall(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(postgres_sql(sql) if DB_BACKEND == "postgres" else sql, params)
        return cur.fetchall()


def init_db():
    conn = get_connection()
    if DB_BACKEND == "sqlite":
        init_sqlite(conn)
    else:
        init_postgres(conn)
    conn.commit()
    conn.close()


def init_sqlite(conn):
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            admin_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY(admin_id) REFERENCES admins(id)
        );

        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            department TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS employee_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS attendance_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            attendance_date TEXT NOT NULL,
            status TEXT NOT NULL,
            in_time TEXT,
            out_time TEXT,
            overtime_hours REAL NOT NULL DEFAULT 0,
            on_leave INTEGER NOT NULL DEFAULT 0,
            leave_type TEXT NOT NULL DEFAULT '',
            last_updated_at TEXT,
            UNIQUE(employee_id, attendance_date),
            FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS activity_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            attendance_date TEXT NOT NULL,
            status TEXT NOT NULL,
            leave_type TEXT NOT NULL DEFAULT '',
            details TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS employee_sessions (
            token TEXT PRIMARY KEY,
            employee_user_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY(employee_user_id) REFERENCES employee_users(id) ON DELETE CASCADE
        );
        """
    )
    bootstrap_seed(conn)


def init_postgres(conn):
    db_execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS admins (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP
        )
        """,
    )
    db_execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            admin_id INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
            expires_at TIMESTAMP NOT NULL
        )
        """,
    )
    db_execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS employees (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            department TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
        """,
    )
    db_execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS employee_users (
            id SERIAL PRIMARY KEY,
            employee_id INTEGER UNIQUE NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
        """,
    )
    db_execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS attendance_entries (
            id SERIAL PRIMARY KEY,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            attendance_date DATE NOT NULL,
            status TEXT NOT NULL,
            in_time TIMESTAMP,
            out_time TIMESTAMP,
            overtime_hours DOUBLE PRECISION NOT NULL DEFAULT 0,
            on_leave BOOLEAN NOT NULL DEFAULT FALSE,
            leave_type TEXT NOT NULL DEFAULT '',
            last_updated_at TIMESTAMP,
            UNIQUE(employee_id, attendance_date)
        )
        """,
    )
    db_execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS activity_records (
            id SERIAL PRIMARY KEY,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            attendance_date DATE NOT NULL,
            status TEXT NOT NULL,
            leave_type TEXT NOT NULL DEFAULT '',
            details TEXT NOT NULL,
            occurred_at TIMESTAMP NOT NULL
        )
        """,
    )
    db_execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS employee_sessions (
            token TEXT PRIMARY KEY,
            employee_user_id INTEGER NOT NULL REFERENCES employee_users(id) ON DELETE CASCADE,
            expires_at TIMESTAMP NOT NULL
        )
        """,
    )
    bootstrap_seed(conn)


def bootstrap_seed(conn):
    admin = db_fetchone(conn, "SELECT id FROM admins WHERE username = ?", ("admin",))
    if not admin:
        db_execute(
            conn,
            "INSERT INTO admins (username, password_hash, created_at) VALUES (?, ?, ?)",
            ("admin", pbkdf2_hash_password("admin123"), now_utc().isoformat()),
        )

    count = db_fetchone(conn, "SELECT COUNT(*) AS count FROM employees")["count"]
    if count:
        return

    created_at = now_utc().isoformat()
    employees = [
        ("Anika Sharma", "IHC Front Office", "EMP-101"),
        ("Rohan Mehta", "IHC Housekeeping", "EMP-132"),
        ("Zara Khan", "IHC Nursing", "EMP-147"),
    ]
    ids = []
    for employee in employees:
        db_execute(
            conn,
            "INSERT INTO employees (name, department, code, created_at) VALUES (?, ?, ?, ?)",
            (*employee, created_at),
        )
        row = db_fetchone(conn, "SELECT id FROM employees WHERE code = ?", (employee[2],))
        ids.append(row["id"])

    date_key = today_key()
    first_in = combine_selected_date_time(date_key)
    second_in = combine_selected_date_time(date_key, hour=8, minute=30)
    second_out = combine_selected_date_time(date_key, hour=18, minute=30)
    overtime = calculate_overtime_hours(second_in, second_out)

    for entry in [
        (ids[0], date_key, "Checked In", first_in, None, 0, bool_to_db(False), "", now_utc().isoformat()),
        (ids[1], date_key, "Checked Out", second_in, second_out, overtime, bool_to_db(False), "", now_utc().isoformat()),
        (ids[2], date_key, "Leave", None, None, 0, bool_to_db(True), "Sick", now_utc().isoformat()),
    ]:
        db_execute(
            conn,
            """
            INSERT INTO attendance_entries (
                employee_id, attendance_date, status, in_time, out_time, overtime_hours, on_leave, leave_type, last_updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            entry,
        )

    for record in [
        (ids[0], date_key, "Checked In", "", f"In time set to {format_time_label(first_in)}", now_utc().isoformat()),
        (ids[1], date_key, "Checked Out", "", f"In {format_time_label(second_in)} • Out {format_time_label(second_out)} • OT {overtime}h", now_utc().isoformat()),
        (ids[1], date_key, "Overtime Auto", "", f"Overtime auto-calculated to {overtime}h", now_utc().isoformat()),
        (ids[2], date_key, "Leave", "Sick", "Marked on leave for Sick", now_utc().isoformat()),
    ]:
        db_execute(
            conn,
            """
            INSERT INTO activity_records (employee_id, attendance_date, status, leave_type, details, occurred_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            record,
        )


def bool_to_db(value):
    return value if DB_BACKEND == "postgres" else int(bool(value))


def combine_selected_date_time(date_key, hour=None, minute=None, second=None):
    current = datetime.now()
    merged = datetime.strptime(date_key, "%Y-%m-%d").replace(
        hour=current.hour if hour is None else hour,
        minute=current.minute if minute is None else minute,
        second=current.second if second is None else second,
        microsecond=0,
    )
    return merged.isoformat()


def combine_selected_date_and_manual_time(date_key, time_value):
    if not time_value:
        return combine_selected_date_time(date_key)
    parts = time_value.split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    return combine_selected_date_time(date_key, hour=hour, minute=minute, second=0)


def parse_iso(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def to_json_value(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def format_timestamp(value):
    parsed = parse_iso(value)
    return "" if not parsed else parsed.strftime("%b %d, %Y, %I:%M %p")


def format_time_label(value):
    parsed = parse_iso(value)
    return "--" if not parsed else parsed.strftime("%I:%M %p").lstrip("0")


def calculate_overtime_hours(in_time, out_time):
    if not in_time or not out_time:
        return 0
    delta = parse_iso(out_time) - parse_iso(in_time)
    worked_hours = delta.total_seconds() / 3600
    return max(0, round(worked_hours - STANDARD_SHIFT_HOURS, 1))


def get_session_admin(conn, token):
    if not token:
        return None
    row = db_fetchone(
        conn,
        """
        SELECT admins.id, admins.username, admins.created_at, sessions.expires_at
        FROM sessions
        JOIN admins ON admins.id = sessions.admin_id
        WHERE sessions.token = ?
        """,
        (token,),
    )
    if not row:
        return None
    if parse_iso(row["expires_at"]) < now_utc():
        db_execute(conn, "DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
        return None
    return row


def get_session_employee(conn, token):
    if not token:
        return None
    row = db_fetchone(
        conn,
        """
        SELECT
            employee_users.id AS employee_user_id,
            employee_users.username,
            employee_users.employee_id,
            employee_sessions.expires_at
        FROM employee_sessions
        JOIN employee_users ON employee_users.id = employee_sessions.employee_user_id
        WHERE employee_sessions.token = ?
        """,
        (token,),
    )
    if not row:
        return None
    if parse_iso(row["expires_at"]) < now_utc():
        db_execute(conn, "DELETE FROM employee_sessions WHERE token = ?", (token,))
        conn.commit()
        return None
    return row


def build_monthly_summary(conn, selected_date):
    if DB_BACKEND == "postgres":
        rows = db_fetchall(
            conn,
            """
            SELECT attendance_date, status, overtime_hours
            FROM attendance_entries
            WHERE DATE_TRUNC('month', attendance_date) = DATE_TRUNC('month', CAST(? AS DATE))
            """,
            (selected_date,),
        )
    else:
        rows = db_fetchall(
            conn,
            """
            SELECT attendance_date, status, overtime_hours
            FROM attendance_entries
            WHERE attendance_date LIKE ?
            """,
            (f"{month_key(selected_date)}-%",),
        )
    worked_days = len({str(row["attendance_date"])[:10] for row in rows})
    present_days = sum(1 for row in rows if row["status"] in ("Checked In", "Checked Out"))
    leave_days = sum(1 for row in rows if row["status"] == "Leave")
    overtime_hours = round(sum(float(row["overtime_hours"] or 0) for row in rows), 1)
    return {
        "workedDays": worked_days,
        "presentDays": present_days,
        "leaveDays": leave_days,
        "overtimeHours": overtime_hours,
    }


def build_bootstrap_payload(conn, selected_date, admin, employee_session):
    employees = db_fetchall(
        conn,
        """
        SELECT
            employees.id,
            employees.name,
            employees.department,
            employees.code,
            employee_users.username AS login_username,
            attendance_entries.status,
            attendance_entries.in_time,
            attendance_entries.out_time,
            attendance_entries.overtime_hours,
            attendance_entries.on_leave,
            attendance_entries.leave_type,
            attendance_entries.last_updated_at
        FROM employees
        LEFT JOIN employee_users
          ON employee_users.employee_id = employees.id
        LEFT JOIN attendance_entries
          ON attendance_entries.employee_id = employees.id
         AND attendance_entries.attendance_date = ?
        ORDER BY employees.name ASC
        """,
        (selected_date,),
    )

    employee_payload = []
    checked_in = 0
    checked_out = 0
    leave_count = 0
    overtime_total = 0
    for row in employees:
        status = row["status"] or "Not Checked In"
        on_leave = bool(row["on_leave"]) if row["on_leave"] is not None else False
        overtime = round(float(row["overtime_hours"] or 0), 1)
        if status == "Checked In":
            checked_in += 1
        if status == "Checked Out":
            checked_out += 1
        if on_leave:
            leave_count += 1
        overtime_total += overtime
        employee_payload.append(
            {
                "id": row["id"],
                "name": row["name"],
                "department": row["department"],
                "code": row["code"],
                "loginUsername": row["login_username"] or "",
                "attendance": {
                    "status": status,
                    "inTime": to_json_value(row["in_time"]),
                    "outTime": to_json_value(row["out_time"]),
                    "overtimeHours": overtime,
                    "onLeave": on_leave,
                    "leaveType": row["leave_type"] or "",
                    "lastUpdatedAt": to_json_value(row["last_updated_at"]),
                },
            }
        )

    records = db_fetchall(
        conn,
        """
        SELECT
            activity_records.id,
            employees.name AS employee_name,
            employees.department,
            activity_records.status,
            activity_records.leave_type,
            activity_records.details,
            activity_records.occurred_at
        FROM activity_records
        JOIN employees ON employees.id = activity_records.employee_id
        WHERE activity_records.attendance_date = ?
        ORDER BY activity_records.occurred_at DESC, activity_records.id DESC
        """,
        (selected_date,),
    )

    admins = []
    if admin:
        admin_rows = db_fetchall(conn, "SELECT username, created_at FROM admins ORDER BY username ASC")
        admins = [
            {
                "username": row["username"],
                "createdAt": to_json_value(row["created_at"]),
                "createdAtLabel": format_timestamp(row["created_at"]),
            }
            for row in admin_rows
        ]

    total = len(employee_payload)
    presence_rate = 0 if total == 0 else round(((checked_in + checked_out) / total) * 100)
    current_employee = None
    self_records = []
    if employee_session:
        current_employee = next((employee for employee in employee_payload if employee["id"] == employee_session["employee_id"]), None)
        self_records_raw = db_fetchall(
            conn,
            """
            SELECT
                activity_records.id,
                activity_records.status,
                activity_records.leave_type,
                activity_records.details,
                activity_records.occurred_at
            FROM activity_records
            WHERE activity_records.employee_id = ?
            ORDER BY activity_records.occurred_at DESC, activity_records.id DESC
            LIMIT 10
            """,
            (employee_session["employee_id"],),
        )
        self_records = [
            {
                "id": row["id"],
                "status": row["status"],
                "leaveType": row["leave_type"] or "",
                "details": row["details"],
                "timestamp": to_json_value(row["occurred_at"]),
                "timestampLabel": format_timestamp(row["occurred_at"]),
            }
            for row in self_records_raw
        ]
    return {
        "isAdmin": bool(admin),
        "currentAdminUsername": admin["username"] if admin else "",
        "employeeLoggedIn": bool(employee_session),
        "currentEmployee": current_employee,
        "selectedDate": selected_date,
        "employees": employee_payload,
        "records": [
            {
                "id": row["id"],
                "employeeName": row["employee_name"],
                "department": row["department"],
                "status": row["status"],
                "leaveType": row["leave_type"] or "",
                "details": row["details"],
                "timestamp": to_json_value(row["occurred_at"]),
                "timestampLabel": format_timestamp(row["occurred_at"]),
            }
            for row in records
        ],
        "selfRecords": self_records,
        "admins": admins,
        "summary": {
            "checkedInCount": checked_in,
            "checkedOutCount": checked_out,
            "overtimeCount": round(overtime_total, 1),
            "leaveCount": leave_count,
            "todayPresenceRate": presence_rate,
            "activeEmployeesCount": checked_in,
        },
        "monthlySummary": build_monthly_summary(conn, selected_date),
    }


class AttendanceHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in STATIC_FILES:
            return self.serve_static(parsed.path)
        if parsed.path == "/api/bootstrap":
            return self.handle_bootstrap(parsed)
        if parsed.path == "/api/export":
            return self.handle_export(parsed)
        self.send_error(404, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/login":
            return self.handle_login()
        if parsed.path == "/api/logout":
            return self.handle_logout()
        if parsed.path == "/api/employee-login":
            return self.handle_employee_login()
        if parsed.path == "/api/employee-logout":
            return self.handle_employee_logout()
        if parsed.path == "/api/employees":
            return self.handle_create_employee()
        if parsed.path == "/api/attendance":
            return self.handle_attendance_action()
        if parsed.path == "/api/employee-attendance":
            return self.handle_employee_attendance_action()
        if parsed.path == "/api/admins":
            return self.handle_create_admin()
        if parsed.path == "/api/change-password":
            return self.handle_change_password()
        if parsed.path == "/api/employee-credentials":
            return self.handle_employee_credentials()
        self.send_error(404, "Not found")

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/employees/"):
            return self.handle_update_employee(parsed.path.rsplit("/", 1)[-1])
        self.send_error(404, "Not found")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/employees/"):
            return self.handle_delete_employee(parsed.path.rsplit("/", 1)[-1])
        self.send_error(404, "Not found")

    def serve_static(self, path):
        filename, content_type = STATIC_FILES[path]
        file_path = ROOT / filename
        if not file_path.exists():
            self.send_error(404, "File not found")
            return
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def parse_json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def send_json(self, status, payload, extra_headers=None):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def get_session_token(self):
        return self.get_cookie_value(SESSION_COOKIE)

    def get_employee_session_token(self):
        return self.get_cookie_value(EMPLOYEE_SESSION_COOKIE)

    def get_cookie_value(self, cookie_name):
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        jar = cookies.SimpleCookie()
        jar.load(raw)
        morsel = jar.get(cookie_name)
        return morsel.value if morsel else None

    def require_admin(self, conn):
        admin = get_session_admin(conn, self.get_session_token())
        if not admin:
            self.send_json(401, {"error": "Admin login required"})
            return None
        return admin

    def handle_bootstrap(self, parsed):
        selected_date = parse_qs(parsed.query).get("date", [today_key()])[0]
        conn = get_connection()
        admin = get_session_admin(conn, self.get_session_token())
        employee_session = get_session_employee(conn, self.get_employee_session_token())
        payload = build_bootstrap_payload(conn, selected_date, admin, employee_session)
        conn.close()
        self.send_json(200, payload)

    def handle_login(self):
        data = self.parse_json_body()
        conn = get_connection()
        admin = db_fetchone(conn, "SELECT * FROM admins WHERE username = ?", (data.get("username", "").strip(),))
        if not admin or not verify_password(data.get("password", ""), admin["password_hash"]):
            conn.close()
            return self.send_json(401, {"error": "Invalid admin username or password"})
        token = secrets.token_hex(24)
        expires_at = (now_utc() + timedelta(days=7)).isoformat()
        db_execute(conn, "INSERT INTO sessions (token, admin_id, expires_at) VALUES (?, ?, ?)", (token, admin["id"], expires_at))
        conn.commit()
        conn.close()
        cookie = cookies.SimpleCookie()
        cookie[SESSION_COOKIE] = token
        cookie[SESSION_COOKIE]["path"] = "/"
        cookie[SESSION_COOKIE]["httponly"] = True
        cookie[SESSION_COOKIE]["samesite"] = "Lax"
        self.send_json(200, {"ok": True}, {"Set-Cookie": cookie.output(header="").strip()})

    def handle_logout(self):
        conn = get_connection()
        token = self.get_session_token()
        if token:
            db_execute(conn, "DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
        conn.close()
        cookie = cookies.SimpleCookie()
        cookie[SESSION_COOKIE] = ""
        cookie[SESSION_COOKIE]["path"] = "/"
        cookie[SESSION_COOKIE]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
        self.send_json(200, {"ok": True}, {"Set-Cookie": cookie.output(header="").strip()})

    def handle_employee_login(self):
        data = self.parse_json_body()
        conn = get_connection()
        employee_user = db_fetchone(
            conn,
            """
            SELECT employee_users.*, employees.name, employees.department, employees.code
            FROM employee_users
            JOIN employees ON employees.id = employee_users.employee_id
            WHERE employee_users.username = ?
            """,
            (data.get("username", "").strip(),),
        )
        if not employee_user or not verify_password(data.get("password", ""), employee_user["password_hash"]):
            conn.close()
            return self.send_json(401, {"error": "Invalid employee username or password"})
        token = secrets.token_hex(24)
        expires_at = (now_utc() + timedelta(days=7)).isoformat()
        db_execute(conn, "INSERT INTO employee_sessions (token, employee_user_id, expires_at) VALUES (?, ?, ?)", (token, employee_user["id"], expires_at))
        conn.commit()
        conn.close()
        cookie = cookies.SimpleCookie()
        cookie[EMPLOYEE_SESSION_COOKIE] = token
        cookie[EMPLOYEE_SESSION_COOKIE]["path"] = "/"
        cookie[EMPLOYEE_SESSION_COOKIE]["httponly"] = True
        cookie[EMPLOYEE_SESSION_COOKIE]["samesite"] = "Lax"
        self.send_json(200, {"ok": True}, {"Set-Cookie": cookie.output(header="").strip()})

    def handle_employee_logout(self):
        conn = get_connection()
        token = self.get_employee_session_token()
        if token:
            db_execute(conn, "DELETE FROM employee_sessions WHERE token = ?", (token,))
            conn.commit()
        conn.close()
        cookie = cookies.SimpleCookie()
        cookie[EMPLOYEE_SESSION_COOKIE] = ""
        cookie[EMPLOYEE_SESSION_COOKIE]["path"] = "/"
        cookie[EMPLOYEE_SESSION_COOKIE]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
        self.send_json(200, {"ok": True}, {"Set-Cookie": cookie.output(header="").strip()})

    def handle_create_admin(self):
        conn = get_connection()
        admin = self.require_admin(conn)
        if not admin:
            conn.close()
            return
        data = self.parse_json_body()
        username = data.get("username", "").strip()
        password = data.get("password", "")
        if len(username) < 3 or len(password) < 8:
            conn.close()
            return self.send_json(400, {"error": "Admin username must be 3+ characters and password 8+ characters"})
        try:
            db_execute(
                conn,
                "INSERT INTO admins (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, pbkdf2_hash_password(password), now_utc().isoformat()),
            )
            conn.commit()
        except Exception:
            conn.close()
            return self.send_json(400, {"error": "Admin username already exists"})
        conn.close()
        self.send_json(201, {"ok": True})

    def handle_change_password(self):
        conn = get_connection()
        admin = self.require_admin(conn)
        if not admin:
            conn.close()
            return
        data = self.parse_json_body()
        current_password = data.get("currentPassword", "")
        new_password = data.get("newPassword", "")
        admin_row = db_fetchone(conn, "SELECT * FROM admins WHERE id = ?", (admin["id"],))
        if not verify_password(current_password, admin_row["password_hash"]):
            conn.close()
            return self.send_json(400, {"error": "Current password is incorrect"})
        if len(new_password) < 8:
            conn.close()
            return self.send_json(400, {"error": "New password must be at least 8 characters"})
        db_execute(conn, "UPDATE admins SET password_hash = ? WHERE id = ?", (pbkdf2_hash_password(new_password), admin["id"]))
        conn.commit()
        conn.close()
        self.send_json(200, {"ok": True})

    def handle_employee_credentials(self):
        conn = get_connection()
        if not self.require_admin(conn):
            conn.close()
            return
        data = self.parse_json_body()
        employee_id = int(data["employeeId"])
        username = data.get("username", "").strip()
        password = data.get("password", "")
        if len(username) < 3 or len(password) < 8:
            conn.close()
            return self.send_json(400, {"error": "Employee username must be 3+ characters and password 8+ characters"})
        existing = db_fetchone(conn, "SELECT id FROM employee_users WHERE employee_id = ?", (employee_id,))
        try:
            if existing:
                db_execute(
                    conn,
                    "UPDATE employee_users SET username = ?, password_hash = ? WHERE employee_id = ?",
                    (username, pbkdf2_hash_password(password), employee_id),
                )
            else:
                db_execute(
                    conn,
                    "INSERT INTO employee_users (employee_id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
                    (employee_id, username, pbkdf2_hash_password(password), now_utc().isoformat()),
                )
            conn.commit()
        except Exception:
            conn.close()
            return self.send_json(400, {"error": "Employee username already exists"})
        conn.close()
        self.send_json(200, {"ok": True})

    def handle_create_employee(self):
        conn = get_connection()
        if not self.require_admin(conn):
            conn.close()
            return
        data = self.parse_json_body()
        try:
            db_execute(
                conn,
                "INSERT INTO employees (name, department, code, created_at) VALUES (?, ?, ?, ?)",
                (data["name"].strip(), data["department"].strip(), data["code"].strip().upper(), now_utc().isoformat()),
            )
            conn.commit()
        except Exception:
            conn.close()
            return self.send_json(400, {"error": "Employee ID already exists"})
        conn.close()
        self.send_json(201, {"ok": True})

    def handle_update_employee(self, employee_id):
        conn = get_connection()
        if not self.require_admin(conn):
            conn.close()
            return
        data = self.parse_json_body()
        try:
            db_execute(
                conn,
                "UPDATE employees SET name = ?, department = ?, code = ? WHERE id = ?",
                (data["name"].strip(), data["department"].strip(), data["code"].strip().upper(), int(employee_id)),
            )
            conn.commit()
        except Exception:
            conn.close()
            return self.send_json(400, {"error": "Employee ID already exists"})
        conn.close()
        self.send_json(200, {"ok": True})

    def handle_delete_employee(self, employee_id):
        conn = get_connection()
        if not self.require_admin(conn):
            conn.close()
            return
        db_execute(conn, "DELETE FROM employees WHERE id = ?", (int(employee_id),))
        conn.commit()
        conn.close()
        self.send_json(200, {"ok": True})

    def handle_attendance_action(self):
        conn = get_connection()
        if not self.require_admin(conn):
            conn.close()
            return
        data = self.parse_json_body()
        employee_id = int(data["employeeId"])
        selected_date = data["date"]
        action = data["action"]
        manual_time = data.get("manualTime", "")
        employee = db_fetchone(conn, "SELECT * FROM employees WHERE id = ?", (employee_id,))
        if not employee:
            conn.close()
            return self.send_json(404, {"error": "Employee not found"})

        entry = db_fetchone(
            conn,
            "SELECT * FROM attendance_entries WHERE employee_id = ? AND attendance_date = ?",
            (employee_id, selected_date),
        )
        timestamp = combine_selected_date_and_manual_time(selected_date, manual_time)

        if action == "check_in":
            payload = {
                "status": "Checked In",
                "in_time": timestamp,
                "out_time": None,
                "overtime_hours": 0,
                "on_leave": bool_to_db(False),
                "leave_type": "",
                "last_updated_at": timestamp,
            }
            self.upsert_attendance(conn, employee_id, selected_date, payload)
            self.insert_record(conn, employee_id, selected_date, "Checked In", "", f"In time set to {format_time_label(timestamp)}", timestamp)
        elif action == "check_out":
            in_time = entry["in_time"] if entry and entry["in_time"] else timestamp
            overtime = calculate_overtime_hours(in_time, timestamp)
            payload = {
                "status": "Checked Out",
                "in_time": in_time,
                "out_time": timestamp,
                "overtime_hours": overtime,
                "on_leave": bool_to_db(False),
                "leave_type": "",
                "last_updated_at": timestamp,
            }
            self.upsert_attendance(conn, employee_id, selected_date, payload)
            self.insert_record(conn, employee_id, selected_date, "Checked Out", "", f"In {format_time_label(in_time)} • Out {format_time_label(timestamp)} • OT {overtime}h", timestamp)
            self.insert_record(conn, employee_id, selected_date, "Overtime Auto", "", f"Overtime auto-calculated to {overtime}h", timestamp)
        elif action == "leave":
            leave_type = data.get("leaveType", "")
            payload = {
                "status": "Leave",
                "in_time": None,
                "out_time": None,
                "overtime_hours": 0,
                "on_leave": bool_to_db(True),
                "leave_type": leave_type,
                "last_updated_at": timestamp,
            }
            self.upsert_attendance(conn, employee_id, selected_date, payload)
            self.insert_record(conn, employee_id, selected_date, "Leave", leave_type, f"Marked on leave for {leave_type}", timestamp)
        else:
            conn.close()
            return self.send_json(400, {"error": "Unknown action"})

        conn.commit()
        conn.close()
        self.send_json(200, {"ok": True})

    def handle_employee_attendance_action(self):
        conn = get_connection()
        employee_session = get_session_employee(conn, self.get_employee_session_token())
        if not employee_session:
            conn.close()
            return self.send_json(401, {"error": "Employee login required"})
        data = self.parse_json_body()
        employee_id = employee_session["employee_id"]
        selected_date = today_key()
        action = data["action"]
        entry = db_fetchone(
            conn,
            "SELECT * FROM attendance_entries WHERE employee_id = ? AND attendance_date = ?",
            (employee_id, selected_date),
        )
        timestamp = combine_selected_date_time(selected_date)

        if action == "check_in":
            payload = {
                "status": "Checked In",
                "in_time": timestamp,
                "out_time": None,
                "overtime_hours": 0,
                "on_leave": bool_to_db(False),
                "leave_type": "",
                "last_updated_at": timestamp,
            }
            self.upsert_attendance(conn, employee_id, selected_date, payload)
            self.insert_record(conn, employee_id, selected_date, "Checked In", "", f"Self check-in at {format_time_label(timestamp)}", timestamp)
        elif action == "check_out":
            in_time = entry["in_time"] if entry and entry["in_time"] else timestamp
            overtime = calculate_overtime_hours(in_time, timestamp)
            payload = {
                "status": "Checked Out",
                "in_time": in_time,
                "out_time": timestamp,
                "overtime_hours": overtime,
                "on_leave": bool_to_db(False),
                "leave_type": "",
                "last_updated_at": timestamp,
            }
            self.upsert_attendance(conn, employee_id, selected_date, payload)
            self.insert_record(conn, employee_id, selected_date, "Checked Out", "", f"Self check-out at {format_time_label(timestamp)} • OT {overtime}h", timestamp)
            self.insert_record(conn, employee_id, selected_date, "Overtime Auto", "", f"Overtime auto-calculated to {overtime}h", timestamp)
        else:
            conn.close()
            return self.send_json(400, {"error": "Unknown employee action"})

        conn.commit()
        conn.close()
        self.send_json(200, {"ok": True})

    def upsert_attendance(self, conn, employee_id, selected_date, payload):
        db_execute(
            conn,
            """
            INSERT INTO attendance_entries (
                employee_id, attendance_date, status, in_time, out_time, overtime_hours, on_leave, leave_type, last_updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(employee_id, attendance_date) DO UPDATE SET
                status = excluded.status,
                in_time = excluded.in_time,
                out_time = excluded.out_time,
                overtime_hours = excluded.overtime_hours,
                on_leave = excluded.on_leave,
                leave_type = excluded.leave_type,
                last_updated_at = excluded.last_updated_at
            """,
            (
                employee_id,
                selected_date,
                payload["status"],
                payload["in_time"],
                payload["out_time"],
                payload["overtime_hours"],
                payload["on_leave"],
                payload["leave_type"],
                payload["last_updated_at"],
            ),
        )

    def insert_record(self, conn, employee_id, selected_date, status, leave_type, details, occurred_at):
        db_execute(
            conn,
            """
            INSERT INTO activity_records (employee_id, attendance_date, status, leave_type, details, occurred_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (employee_id, selected_date, status, leave_type, details, occurred_at),
        )

    def handle_export(self, parsed):
        conn = get_connection()
        admin = self.require_admin(conn)
        if not admin:
            conn.close()
            return
        params = parse_qs(parsed.query)
        selected_date = params.get("date", [today_key()])[0]
        file_format = params.get("format", ["csv"])[0]
        payload = build_bootstrap_payload(conn, selected_date, admin, None)
        conn.close()

        rows = payload["employees"]
        if file_format == "csv":
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(["Employee", "Team / Unit", "Employee ID", "Status", "In Time", "Out Time", "Overtime Hours", "Leave Type"])
            for row in rows:
                attendance = row["attendance"]
                writer.writerow(
                    [
                        row["name"],
                        row["department"],
                        row["code"],
                        attendance["status"],
                        format_time_label(attendance["inTime"]),
                        format_time_label(attendance["outTime"]),
                        attendance["overtimeHours"],
                        attendance["leaveType"] or "--",
                    ]
                )
            data = buffer.getvalue().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="ihc-report-{selected_date}.csv"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        table = [
            "<table><tr><th>Employee</th><th>Team / Unit</th><th>Employee ID</th><th>Status</th><th>In Time</th><th>Out Time</th><th>Overtime Hours</th><th>Leave Type</th></tr>"
        ]
        for row in rows:
            attendance = row["attendance"]
            table.append(
                "<tr>"
                f"<td>{row['name']}</td>"
                f"<td>{row['department']}</td>"
                f"<td>{row['code']}</td>"
                f"<td>{attendance['status']}</td>"
                f"<td>{format_time_label(attendance['inTime'])}</td>"
                f"<td>{format_time_label(attendance['outTime'])}</td>"
                f"<td>{attendance['overtimeHours']}</td>"
                f"<td>{attendance['leaveType'] or '--'}</td>"
                "</tr>"
            )
        table.append("</table>")
        data = "".join(table).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.ms-excel")
        self.send_header("Content-Disposition", f'attachment; filename="ihc-report-{selected_date}.xls"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), AttendanceHandler)
    print(f"Serving IHC Attendance on http://{HOST}:{PORT} using {DB_BACKEND}")
    server.serve_forever()


if __name__ == "__main__":
    main()
