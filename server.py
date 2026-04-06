import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
DB_PATH = Path(os.environ.get("DB_PATH", DATA_DIR / "calorie_compass.db"))
SESSION_COOKIE = "calorie_compass_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30
STATIC_FILES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/login": "login.html",
    "/login.html": "login.html",
    "/register": "register.html",
    "/register.html": "register.html",
    "/styles.css": "styles.css",
    "/app.js": "app.js",
    "/login.js": "login.js",
    "/register.js": "register.js",
}


def db_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS foods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                manufacturer TEXT NOT NULL,
                calories REAL NOT NULL,
                protein REAL NOT NULL,
                fat REAL NOT NULL,
                carbs REAL NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(name, manufacturer)
            );

            CREATE TABLE IF NOT EXISTS goals (
                user_id INTEGER PRIMARY KEY,
                calories REAL NOT NULL,
                protein REAL NOT NULL,
                fat REAL NOT NULL,
                carbs REAL NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                food_id INTEGER NOT NULL,
                entry_date TEXT NOT NULL,
                grams REAL NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE CASCADE
            );
            """
        )


def now_iso():
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def hash_password(password, salt):
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return digest.hex()


def create_session(connection, user_id):
    token = secrets.token_urlsafe(32)
    created_at = datetime.now(UTC)
    expires_at = created_at + timedelta(days=30)
    connection.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, created_at.isoformat() + "Z", expires_at.isoformat() + "Z"),
    )
    connection.commit()
    return token


def get_goals(connection, user_id):
    row = connection.execute(
        "SELECT calories, protein, fat, carbs FROM goals WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if row:
        return dict(row)
    return {"calories": 2200, "protein": 160, "fat": 70, "carbs": 220}


def compute_entry_payload(row):
    ratio = row["grams"] / 100
    return {
        "id": row["id"],
        "food_id": row["food_id"],
        "food_name": row["name"],
        "manufacturer": row["manufacturer"],
        "grams": row["grams"],
        "date": row["entry_date"],
        "created_at": row["created_at"],
        "calories": row["calories"] * ratio,
        "protein": row["protein"] * ratio,
        "fat": row["fat"] * ratio,
        "carbs": row["carbs"] * ratio,
    }


def get_entries_for_date(connection, user_id, date_value):
    rows = connection.execute(
        """
        SELECT entries.id, entries.food_id, entries.entry_date, entries.grams, entries.created_at,
               foods.name, foods.manufacturer, foods.calories, foods.protein, foods.fat, foods.carbs
        FROM entries
        JOIN foods ON foods.id = entries.food_id
        WHERE entries.user_id = ? AND entries.entry_date = ?
        ORDER BY entries.created_at DESC
        """,
        (user_id, date_value),
    ).fetchall()
    return [compute_entry_payload(row) for row in rows]


def totals_from_entries(entries):
    totals = {"calories": 0, "protein": 0, "fat": 0, "carbs": 0}
    for entry in entries:
        totals["calories"] += entry["calories"]
        totals["protein"] += entry["protein"]
        totals["fat"] += entry["fat"]
        totals["carbs"] += entry["carbs"]
    return totals


def completion_status(totals, goals):
    ratios = []
    for key in ("calories", "protein", "fat", "carbs"):
        goal = goals[key]
        ratios.append((totals[key] / goal) if goal else 0)

    if all(0.9 <= ratio <= 1.1 for ratio in ratios):
        return {"kind": "good", "label": "Норма выполнена", "className": "status-good"}
    if all(0.75 <= ratio <= 1.25 for ratio in ratios):
        return {"kind": "warn", "label": "Близко к цели", "className": "status-warn"}
    return {"kind": "bad", "label": "Норма не выполнена", "className": "status-bad"}


def get_analytics(connection, user_id, days):
    goals = get_goals(connection, user_id)
    today_date = datetime.now().date()
    items = []

    for offset in range(days - 1, -1, -1):
        date_value = (today_date - timedelta(days=offset)).isoformat()
        entries = get_entries_for_date(connection, user_id, date_value)
        totals = totals_from_entries(entries)
        items.append(
            {
                "date": date_value,
                "totals": totals,
                "status": completion_status(totals, goals),
            }
        )

    return items


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/healthz":
            return self.send_json(200, {"ok": True})

        if parsed.path in STATIC_FILES:
            return self.serve_static(parsed.path)

        if parsed.path == "/api/auth/me":
            return self.handle_auth_me()
        if parsed.path == "/api/foods":
            return self.handle_get_foods()
        if parsed.path == "/api/goals":
            return self.handle_get_goals()
        if parsed.path == "/api/entries":
            return self.handle_get_entries(parsed.query)
        if parsed.path == "/api/analytics":
            return self.handle_get_analytics(parsed.query)

        self.send_error(404, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/auth/register":
            return self.handle_register()
        if parsed.path == "/api/auth/login":
            return self.handle_login()
        if parsed.path == "/api/auth/logout":
            return self.handle_logout()
        if parsed.path == "/api/foods":
            return self.handle_create_food()
        if parsed.path == "/api/entries":
            return self.handle_create_entry()

        self.send_error(404, "Not found")

    def do_PUT(self):
        if self.path == "/api/goals":
            return self.handle_update_goals()
        self.send_error(404, "Not found")

    def do_PATCH(self):
        if self.path.startswith("/api/foods/"):
            return self.handle_update_food()
        self.send_error(404, "Not found")

    def do_DELETE(self):
        if self.path.startswith("/api/foods/"):
            return self.handle_delete_food()
        if self.path.startswith("/api/entries/"):
            return self.handle_delete_entry()
        self.send_error(404, "Not found")

    def serve_static(self, path):
        file_path = BASE_DIR / STATIC_FILES[path]
        if not file_path.exists():
            self.send_error(404, "File not found")
            return

        mime_type = "text/html; charset=utf-8"
        if file_path.suffix == ".css":
            mime_type = "text/css; charset=utf-8"
        elif file_path.suffix == ".js":
            mime_type = "application/javascript; charset=utf-8"

        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.end_headers()
        self.wfile.write(file_path.read_bytes())

    def handle_register(self):
        payload = self.read_json()
        name = (payload.get("name") or "").strip()
        email = (payload.get("email") or "").strip().lower()
        password = payload.get("password") or ""

        if not name or not email or len(password) < 6:
            return self.send_json(400, {"error": "Укажите имя, email и пароль не короче 6 символов."})

        salt = secrets.token_hex(16)
        password_hash = hash_password(password, salt)

        with db_connection() as connection:
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO users (name, email, password_hash, password_salt, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (name, email, password_hash, salt, now_iso()),
                )
                connection.commit()
            except sqlite3.IntegrityError:
                return self.send_json(409, {"error": "Пользователь с таким email уже существует."})

            user_id = cursor.lastrowid
            connection.execute(
                """
                INSERT INTO goals (user_id, calories, protein, fat, carbs, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, 2200, 160, 70, 220, now_iso()),
            )
            connection.commit()
            token = create_session(connection, user_id)

        return self.send_auth_response(user_id, name, email, token)

    def handle_login(self):
        payload = self.read_json()
        email = (payload.get("email") or "").strip().lower()
        password = payload.get("password") or ""

        with db_connection() as connection:
            user = connection.execute(
                "SELECT id, name, email, password_hash, password_salt FROM users WHERE email = ?",
                (email,),
            ).fetchone()

            if not user:
                return self.send_json(401, {"error": "Неверный email или пароль."})

            expected_hash = hash_password(password, user["password_salt"])
            if not hmac.compare_digest(expected_hash, user["password_hash"]):
                return self.send_json(401, {"error": "Неверный email или пароль."})

            token = create_session(connection, user["id"])

        return self.send_auth_response(user["id"], user["name"], user["email"], token)

    def handle_logout(self):
        token = self.get_session_token()
        if token:
            with db_connection() as connection:
                connection.execute("DELETE FROM sessions WHERE token = ?", (token,))
                connection.commit()

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Set-Cookie", self.build_session_cookie("", 0))
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))

    def handle_auth_me(self):
        user = self.require_user()
        if not user:
            return
        self.send_json(200, {"user": user})

    def handle_get_foods(self):
        user = self.require_user()
        if not user:
            return

        with db_connection() as connection:
            rows = connection.execute(
                """
                SELECT id, name, manufacturer, calories, protein, fat, carbs
                FROM foods
                ORDER BY name COLLATE NOCASE, manufacturer COLLATE NOCASE
                """
            ).fetchall()
        foods = [dict(row) for row in rows]
        self.send_json(200, {"foods": foods})

    def handle_create_food(self):
        user = self.require_user()
        if not user:
            return

        payload = self.read_json()
        food = self.validate_food_payload(payload)
        if isinstance(food, tuple):
            return self.send_json(*food)

        with db_connection() as connection:
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO foods (name, manufacturer, calories, protein, fat, carbs, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        food["name"],
                        food["manufacturer"],
                        food["calories"],
                        food["protein"],
                        food["fat"],
                        food["carbs"],
                        now_iso(),
                        now_iso(),
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError:
                return self.send_json(409, {"error": "Такое блюдо с этим изготовителем уже есть в справочнике."})

        self.send_json(201, {"id": cursor.lastrowid})

    def handle_update_food(self):
        user = self.require_user()
        if not user:
            return

        food_id = self.extract_id(self.path, "/api/foods/")
        if not food_id:
            return self.send_json(400, {"error": "Некорректный идентификатор блюда."})

        payload = self.read_json()
        food = self.validate_food_payload(payload)
        if isinstance(food, tuple):
            return self.send_json(*food)

        with db_connection() as connection:
            try:
                cursor = connection.execute(
                    """
                    UPDATE foods
                    SET name = ?, manufacturer = ?, calories = ?, protein = ?, fat = ?, carbs = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        food["name"],
                        food["manufacturer"],
                        food["calories"],
                        food["protein"],
                        food["fat"],
                        food["carbs"],
                        now_iso(),
                        food_id,
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError:
                return self.send_json(409, {"error": "Такое блюдо с этим изготовителем уже есть в справочнике."})

        if cursor.rowcount == 0:
            return self.send_json(404, {"error": "Блюдо не найдено."})
        self.send_json(200, {"ok": True})

    def handle_delete_food(self):
        user = self.require_user()
        if not user:
            return

        food_id = self.extract_id(self.path, "/api/foods/")
        if not food_id:
            return self.send_json(400, {"error": "Некорректный идентификатор блюда."})

        with db_connection() as connection:
            cursor = connection.execute("DELETE FROM foods WHERE id = ?", (food_id,))
            connection.commit()

        if cursor.rowcount == 0:
            return self.send_json(404, {"error": "Блюдо не найдено."})
        self.send_json(200, {"ok": True})

    def handle_get_goals(self):
        user = self.require_user()
        if not user:
            return

        with db_connection() as connection:
            goals = get_goals(connection, user["id"])
        self.send_json(200, {"goals": goals})

    def handle_update_goals(self):
        user = self.require_user()
        if not user:
            return

        payload = self.read_json()
        try:
            goals = {
                "calories": float(payload["calories"]),
                "protein": float(payload["protein"]),
                "fat": float(payload["fat"]),
                "carbs": float(payload["carbs"]),
            }
        except (KeyError, TypeError, ValueError):
            return self.send_json(400, {"error": "Передайте корректные значения целей."})

        with db_connection() as connection:
            connection.execute(
                """
                INSERT INTO goals (user_id, calories, protein, fat, carbs, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    calories = excluded.calories,
                    protein = excluded.protein,
                    fat = excluded.fat,
                    carbs = excluded.carbs,
                    updated_at = excluded.updated_at
                """,
                (user["id"], goals["calories"], goals["protein"], goals["fat"], goals["carbs"], now_iso()),
            )
            connection.commit()

        self.send_json(200, {"goals": goals})

    def handle_get_entries(self, query_string):
        user = self.require_user()
        if not user:
            return

        date_value = parse_qs(query_string).get("date", [""])[0]
        if not date_value:
            return self.send_json(400, {"error": "Нужно передать дату."})

        with db_connection() as connection:
            entries = get_entries_for_date(connection, user["id"], date_value)
        self.send_json(200, {"entries": entries})

    def handle_create_entry(self):
        user = self.require_user()
        if not user:
            return

        payload = self.read_json()
        try:
            food_id = int(payload["food_id"])
            grams = float(payload["grams"])
            date_value = payload["date"]
        except (KeyError, TypeError, ValueError):
            return self.send_json(400, {"error": "Передайте корректные данные записи."})

        if grams <= 0:
            return self.send_json(400, {"error": "Вес должен быть больше нуля."})

        with db_connection() as connection:
            food_exists = connection.execute("SELECT id FROM foods WHERE id = ?", (food_id,)).fetchone()
            if not food_exists:
                return self.send_json(404, {"error": "Блюдо не найдено в справочнике."})

            cursor = connection.execute(
                """
                INSERT INTO entries (user_id, food_id, entry_date, grams, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user["id"], food_id, date_value, grams, now_iso()),
            )
            connection.commit()

        self.send_json(201, {"id": cursor.lastrowid})

    def handle_delete_entry(self):
        user = self.require_user()
        if not user:
            return

        entry_id = self.extract_id(self.path, "/api/entries/")
        if not entry_id:
            return self.send_json(400, {"error": "Некорректный идентификатор записи."})

        with db_connection() as connection:
            cursor = connection.execute(
                "DELETE FROM entries WHERE id = ? AND user_id = ?",
                (entry_id, user["id"]),
            )
            connection.commit()

        if cursor.rowcount == 0:
            return self.send_json(404, {"error": "Запись не найдена."})
        self.send_json(200, {"ok": True})

    def handle_get_analytics(self, query_string):
        user = self.require_user()
        if not user:
            return

        raw_days = parse_qs(query_string).get("days", ["14"])[0]
        try:
            days = max(1, min(60, int(raw_days)))
        except ValueError:
            days = 14

        with db_connection() as connection:
            items = get_analytics(connection, user["id"], days)
        self.send_json(200, {"days": items})

    def validate_food_payload(self, payload):
        try:
            name = str(payload["name"]).strip()
            manufacturer = str(payload["manufacturer"]).strip()
            calories = float(payload["calories"])
            protein = float(payload["protein"])
            fat = float(payload["fat"])
            carbs = float(payload["carbs"])
        except (KeyError, TypeError, ValueError):
            return 400, {"error": "Передайте корректные данные блюда."}

        if not name or not manufacturer:
            return 400, {"error": "Название и изготовитель обязательны."}

        return {
            "name": name,
            "manufacturer": manufacturer,
            "calories": calories,
            "protein": protein,
            "fat": fat,
            "carbs": carbs,
        }

    def require_user(self):
        token = self.get_session_token()
        if not token:
            self.send_json(401, {"error": "Требуется авторизация."})
            return None

        with db_connection() as connection:
            row = connection.execute(
                """
                SELECT users.id, users.name, users.email, sessions.expires_at
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token = ?
                """,
                (token,),
            ).fetchone()

            if not row:
                self.send_json(401, {"error": "Сессия не найдена."})
                return None

            expires_at = datetime.fromisoformat(row["expires_at"].replace("Z", ""))
            if expires_at < datetime.now(UTC):
                connection.execute("DELETE FROM sessions WHERE token = ?", (token,))
                connection.commit()
                self.send_json(401, {"error": "Сессия истекла."})
                return None

            return {"id": row["id"], "name": row["name"], "email": row["email"]}

    def get_session_token(self):
        header = self.headers.get("Cookie")
        if not header:
            return None
        jar = cookies.SimpleCookie()
        jar.load(header)
        if SESSION_COOKIE not in jar:
            return None
        return jar[SESSION_COOKIE].value

    def send_auth_response(self, user_id, name, email, token):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Set-Cookie", self.build_session_cookie(token, SESSION_MAX_AGE))
        self.end_headers()
        self.wfile.write(json.dumps({"user": {"id": user_id, "name": name, "email": email}}).encode("utf-8"))

    def build_session_cookie(self, token, max_age):
        parts = [
            f"{SESSION_COOKIE}={token}",
            "Path=/",
            f"Max-Age={max_age}",
            "HttpOnly",
            "SameSite=Lax",
        ]
        if os.environ.get("COOKIE_SECURE", "false").lower() == "true":
            parts.append("Secure")
        return "; ".join(parts)

    def send_json(self, status, payload):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def read_json(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length else b"{}"
        try:
            return json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def extract_id(self, path, prefix):
        raw_value = path.removeprefix(prefix)
        try:
            return int(raw_value)
        except ValueError:
            return None

    def log_message(self, format_text, *args):
        print(f"{self.address_string()} - {format_text % args}")


if __name__ == "__main__":
    init_db()
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "4173"))
    server = ThreadingHTTPServer((host, port), AppHandler)
    print(f"Calorie Compass server running on http://{host}:{port} with DB {DB_PATH}")
    server.serve_forever()
