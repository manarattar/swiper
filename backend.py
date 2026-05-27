import copy
import csv
import io
import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from flask import session
from werkzeug.security import check_password_hash, generate_password_hash

from ml_recommender import cosine_similarity, load_model, meal_document, ml_scores, train_from_meals, vectorize

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

DATA_FILE = "meals_data.json"
DB_PATH = os.environ.get("DATABASE_PATH", "swipeeat.db")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
REQUIRED_MEAL_FIELDS = {
    "name",
    "img",
    "description",
    "category",
    "meatKind",
    "taste",
    "spicy",
    "emotion",
    "emoji",
}
OPTIONAL_DEFAULTS = {
    "price": "",
    "allergens": [],
    "available": True,
    "stock": 25,
    "lowStockThreshold": 5,
}
VALID_ORDER_STATUSES = {"new", "preparing", "completed", "cancelled"}
VALID_PAYMENT_STATUSES = {"unpaid", "paid", "refunded"}
VALID_TABLE_SESSION_STATUSES = {"open", "closed"}
SCHEMA_VERSION = "2026-05-02-multi-item-orders"
DEFAULT_RESTAURANT_SETTINGS = {
    "restaurantName": "SwipeEat",
    "tagline": "Freshly prepared. Build your order.",
    "logoUrl": "/static/logo.png",
    "contactPhone": "",
    "contactEmail": "",
    "address": "",
    "openingHours": "",
    "currency": "$",
    "taxRate": "0",
    "serviceFee": "0",
    "acceptingOrders": "true",
    "busyMessage": "Online ordering is paused right now. Please try again soon.",
}
_RECOMMENDER_MODEL = None


def normalize_meal(meal):
    normalized = copy.deepcopy(meal)
    normalized["name"] = str(normalized.get("name", "")).strip()
    normalized["img"] = str(normalized.get("img", "")).strip()
    normalized["description"] = str(normalized.get("description", "")).strip()
    normalized["category"] = str(normalized.get("category", "")).strip()
    normalized["meatKind"] = str(normalized.get("meatKind", "")).strip()
    normalized["taste"] = str(normalized.get("taste", "")).strip()
    normalized["emotion"] = str(normalized.get("emotion", "")).strip()
    normalized["emoji"] = str(normalized.get("emoji", "")).strip()
    normalized["spicy"] = bool(normalized.get("spicy", False))
    normalized["available"] = bool(normalized.get("available", True))
    normalized["price"] = str(normalized.get("price", "")).strip()
    normalized["stock"] = max(0, int(normalized.get("stock", 25) or 0))
    normalized["lowStockThreshold"] = max(0, int(normalized.get("lowStockThreshold", 5) or 0))

    allergens = normalized.get("allergens", [])
    if isinstance(allergens, str):
        allergens = [item.strip() for item in allergens.split(",") if item.strip()]
    normalized["allergens"] = allergens if isinstance(allergens, list) else []

    for key, value in OPTIONAL_DEFAULTS.items():
        normalized.setdefault(key, copy.deepcopy(value))
    return normalized


def validate_meals(meals):
    for index, meal in enumerate(meals):
        missing = REQUIRED_MEAL_FIELDS - set(meal)
        if missing:
            missing_fields = ", ".join(sorted(missing))
            raise ValueError(f"Meal at index {index} is missing: {missing_fields}")
        if not meal.get("name"):
            raise ValueError(f"Meal at index {index} needs a name")


def load_seed_meals():
    with open(DATA_FILE, "r", encoding="utf-8-sig") as f:
        meals = json.load(f)
    normalized = [normalize_meal(meal) for meal in meals]
    validate_meals(normalized)
    return normalized


class HybridRow(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class PostgresCursor:
    def __init__(self, cursor):
        self.cursor = cursor

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def fetchone(self):
        row = self.cursor.fetchone()
        return HybridRow(row) if row is not None else None

    def fetchall(self):
        return [HybridRow(row) for row in self.cursor.fetchall()]


class PostgresConnection:
    is_postgres = True

    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, params=None):
        query = self._adapt_query(query, params)
        cursor = self.connection.cursor(row_factory=dict_row)
        cursor.execute(query, params or ())
        return PostgresCursor(cursor)

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()

    def _adapt_query(self, query, params=None):
        query = query.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        query = query.replace("UNIQUE COLLATE NOCASE", "UNIQUE")
        query = query.replace("TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP", "TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP")
        if "INSERT OR IGNORE INTO schema_migrations" in query:
            query = query.replace("INSERT OR IGNORE INTO", "INSERT INTO")
            query = query.rstrip() + " ON CONFLICT (version) DO NOTHING"
        if isinstance(params, dict):
            return re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", r"%(\1)s", query)
        return query.replace("?", "%s")


def using_postgres():
    return DATABASE_URL.startswith(("postgres://", "postgresql://"))


@contextmanager
def connect_db():
    if using_postgres():
        if psycopg is None:
            raise RuntimeError("DATABASE_URL is set to Postgres but psycopg is not installed")
        conn = PostgresConnection(psycopg.connect(DATABASE_URL))
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def is_integrity_error(exc):
    return isinstance(exc, sqlite3.IntegrityError) or "IntegrityError" in exc.__class__.__name__ or "UniqueViolation" in exc.__class__.__name__


def adapt_column_definition(conn, definition):
    if getattr(conn, "is_postgres", False):
        return definition.replace("TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP", "TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP")
    return definition


def ensure_column(conn, table, column, definition):
    if getattr(conn, "is_postgres", False):
        row = conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = ? AND column_name = ?
            """,
            (table, column),
        ).fetchone()
        if row is None:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {adapt_column_definition(conn, definition)}")
        return
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def create_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'admin',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, description)
        VALUES (?, ?)
        """,
        (SCHEMA_VERSION, "Official readiness tables and order operations metadata"),
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            img TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            meatKind TEXT NOT NULL,
            taste TEXT NOT NULL,
            spicy INTEGER NOT NULL DEFAULT 0,
            emotion TEXT NOT NULL,
            emoji TEXT NOT NULL,
            price TEXT NOT NULL DEFAULT '',
            allergens TEXT NOT NULL DEFAULT '[]',
            available INTEGER NOT NULL DEFAULT 1,
            stock INTEGER NOT NULL DEFAULT 25,
            low_stock_threshold INTEGER NOT NULL DEFAULT 5,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meal_name TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            table_number TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'new',
            tracking_token TEXT NOT NULL DEFAULT '',
            unit_price REAL NOT NULL DEFAULT 0,
            subtotal_price REAL NOT NULL DEFAULT 0,
            tax_price REAL NOT NULL DEFAULT 0,
            service_fee REAL NOT NULL DEFAULT 0,
            total_price REAL NOT NULL DEFAULT 0,
            customer_name TEXT NOT NULL DEFAULT '',
            customer_phone TEXT NOT NULL DEFAULT '',
            payment_status TEXT NOT NULL DEFAULT 'unpaid',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    ensure_column(conn, "orders", "quantity", "INTEGER NOT NULL DEFAULT 1")
    ensure_column(conn, "orders", "table_number", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "orders", "notes", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "orders", "status", "TEXT NOT NULL DEFAULT 'new'")
    ensure_column(conn, "meals", "stock", "INTEGER NOT NULL DEFAULT 25")
    ensure_column(conn, "meals", "low_stock_threshold", "INTEGER NOT NULL DEFAULT 5")
    ensure_column(conn, "orders", "updated_at", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "orders", "tracking_token", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "orders", "unit_price", "REAL NOT NULL DEFAULT 0")
    ensure_column(conn, "orders", "subtotal_price", "REAL NOT NULL DEFAULT 0")
    ensure_column(conn, "orders", "tax_price", "REAL NOT NULL DEFAULT 0")
    ensure_column(conn, "orders", "service_fee", "REAL NOT NULL DEFAULT 0")
    ensure_column(conn, "orders", "total_price", "REAL NOT NULL DEFAULT 0")
    ensure_column(conn, "orders", "customer_name", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "orders", "customer_phone", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "orders", "payment_status", "TEXT NOT NULL DEFAULT 'unpaid'")
    ensure_column(conn, "orders", "estimated_minutes", "INTEGER NOT NULL DEFAULT 12")
    ensure_column(conn, "orders", "status_started_at", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "orders", "table_session_token", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "orders", "round_id", "INTEGER NOT NULL DEFAULT 0")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS table_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT NOT NULL UNIQUE,
            table_number TEXT NOT NULL DEFAULT '',
            guest_name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_table_sessions_token
        ON table_sessions(token)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS order_rounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_session_token TEXT NOT NULL DEFAULT '',
            round_number INTEGER NOT NULL DEFAULT 1,
            order_id INTEGER NOT NULL DEFAULT 0,
            subtotal_price REAL NOT NULL DEFAULT 0,
            total_price REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'sent',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_order_rounds_session
        ON order_rounds(table_session_token)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            meal_name TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            unit_price REAL NOT NULL DEFAULT 0,
            total_price REAL NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_order_items_order_id
        ON order_items(order_id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS order_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            from_value TEXT NOT NULL DEFAULT '',
            to_value TEXT NOT NULL DEFAULT '',
            actor TEXT NOT NULL DEFAULT 'system',
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_order_history_order_id
        ON order_history(order_id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS swipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meal_name TEXT NOT NULL,
            liked INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS restaurant_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT NOT NULL,
            source TEXT NOT NULL,
            message TEXT NOT NULL,
            path TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recommendation_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analytics_session_id TEXT NOT NULL DEFAULT '',
            table_session_token TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            query TEXT NOT NULL DEFAULT '',
            meal_name TEXT NOT NULL DEFAULT '',
            score REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_recommendation_events_created_at
        ON recommendation_events(created_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_app_events_created_at
        ON app_events(created_at)
        """
    )
    for key, value in DEFAULT_RESTAURANT_SETTINGS.items():
        if getattr(conn, "is_postgres", False):
            conn.execute(
                "INSERT INTO restaurant_settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO NOTHING",
                (key, value),
            )
        else:
            conn.execute(
                "INSERT OR IGNORE INTO restaurant_settings (key, value) VALUES (?, ?)",
                (key, value),
            )
    conn.commit()


def meal_to_params(meal):
    normalized = normalize_meal(meal)
    validate_meals([normalized])
    return {
        "name": normalized["name"],
        "img": normalized["img"],
        "description": normalized["description"],
        "category": normalized["category"],
        "meatKind": normalized["meatKind"],
        "taste": normalized["taste"],
        "spicy": 1 if normalized["spicy"] else 0,
        "emotion": normalized["emotion"],
        "emoji": normalized["emoji"],
        "price": normalized["price"],
        "allergens": json.dumps(normalized["allergens"], ensure_ascii=False),
        "available": 1 if normalized["available"] else 0,
        "stock": normalized["stock"],
        "lowStockThreshold": normalized["lowStockThreshold"],
    }


def row_get(row, *keys, default=None):
    for key in keys:
        try:
            return row[key]
        except (KeyError, IndexError):
            continue
    return default


def row_to_meal(row):
    low_stock_threshold = row_get(row, "low_stock_threshold", "lowstockthreshold", default=5)
    stock = row_get(row, "stock", default=0)
    return {
        "name": row_get(row, "name", default=""),
        "img": row_get(row, "img", default=""),
        "description": row_get(row, "description", default=""),
        "category": row_get(row, "category", default=""),
        "meatKind": row_get(row, "meatKind", "meatkind", default=""),
        "taste": row_get(row, "taste", default=""),
        "spicy": bool(row_get(row, "spicy", default=False)),
        "emotion": row_get(row, "emotion", default=""),
        "emoji": row_get(row, "emoji", default=""),
        "price": row_get(row, "price", default=""),
        "allergens": json.loads(row_get(row, "allergens", default="[]") or "[]"),
        "available": bool(row_get(row, "available", default=True)),
        "stock": stock,
        "lowStockThreshold": low_stock_threshold,
        "lowStock": stock <= low_stock_threshold,
    }


def parse_timestamp(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def minutes_since(value):
    parsed = parse_timestamp(value)
    if parsed is None:
        return 0
    return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds() // 60))


def row_to_order_history(row):
    return {
        "id": row["id"],
        "orderId": row["order_id"],
        "action": row["action"],
        "fromValue": row_get(row, "from_value", default=""),
        "toValue": row_get(row, "to_value", default=""),
        "actor": row_get(row, "actor", default="system"),
        "note": row_get(row, "note", default=""),
        "createdAt": row["created_at"],
    }


def row_to_order(row, items=None):
    items = items or []
    display_name = row["meal_name"]
    if len(items) > 1:
        display_name = f"{items[0]['mealName']} + {len(items) - 1} more"
    subtotal_price = row_get(row, "subtotal_price", default=row["total_price"])
    tax_price = row_get(row, "tax_price", default=0)
    service_fee = row_get(row, "service_fee", default=0)
    if (subtotal_price or 0) == 0 and (tax_price or 0) == 0 and (service_fee or 0) == 0 and (row["total_price"] or 0) > 0:
        subtotal_price = row["total_price"]
    estimated_minutes = int(row_get(row, "estimated_minutes", default=estimate_prep_minutes(row["status"])) or 0)
    if row["status"] in ("completed", "cancelled"):
        estimated_minutes = 0
    status_started_at = row_get(row, "status_started_at", default=row["created_at"]) or row["created_at"]
    elapsed_minutes = minutes_since(row["created_at"])
    status_age_minutes = minutes_since(status_started_at)
    return {
        "id": row["id"],
        "mealName": display_name,
        "quantity": row["quantity"],
        "tableNumber": row["table_number"],
        "customerName": row_get(row, "customer_name", default=""),
        "customerPhone": row_get(row, "customer_phone", default=""),
        "notes": row["notes"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "trackingToken": row["tracking_token"],
        "trackingUrl": order_tracking_url(row["tracking_token"]),
        "unitPrice": row["unit_price"],
        "subtotalPrice": subtotal_price,
        "taxPrice": tax_price,
        "serviceFee": service_fee,
        "totalPrice": row["total_price"],
        "paymentStatus": row["payment_status"],
        "estimatedMinutes": estimated_minutes,
        "statusStartedAt": status_started_at,
        "elapsedMinutes": elapsed_minutes,
        "statusAgeMinutes": status_age_minutes,
        "isDelayed": row["status"] in ("new", "preparing") and status_age_minutes > max(estimated_minutes, 1),
        "tableSessionToken": row_get(row, "table_session_token", default=""),
        "roundId": row_get(row, "round_id", default=0),
        "items": items,
        "itemCount": len(items) if items else 1,
    }


def insert_meal(conn, meal):
    params = meal_to_params(meal)
    conn.execute(
        """
        INSERT INTO meals (
            name, img, description, category, meatKind, taste, spicy,
            emotion, emoji, price, allergens, available, stock, low_stock_threshold
        ) VALUES (
            :name, :img, :description, :category, :meatKind, :taste, :spicy,
            :emotion, :emoji, :price, :allergens, :available, :stock, :lowStockThreshold
        )
        """,
        params,
    )


def seed_if_empty(conn):
    count = conn.execute("SELECT COUNT(*) FROM meals").fetchone()[0]
    if count:
        return
    for meal in load_seed_meals():
        insert_meal(conn, meal)
    conn.commit()


def init_database(db_path=None, reset=False):
    global DB_PATH
    if db_path is not None:
        DB_PATH = str(db_path)
    with connect_db() as conn:
        create_schema(conn)
        if reset:
            conn.execute("DELETE FROM swipes")
            conn.execute("DELETE FROM order_items")
            conn.execute("DELETE FROM orders")
            conn.execute("DELETE FROM order_rounds")
            conn.execute("DELETE FROM table_sessions")
            conn.execute("DELETE FROM recommendation_events")
            conn.execute("DELETE FROM meals")
            conn.execute("DELETE FROM admin_users")
            conn.execute("DELETE FROM app_events")
            conn.execute("DELETE FROM order_history")
            conn.execute("DELETE FROM restaurant_settings")
            conn.execute("DELETE FROM schema_migrations WHERE version != ?", (SCHEMA_VERSION,))
            if not getattr(conn, "is_postgres", False):
                conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('meals', 'orders', 'order_items', 'order_history', 'order_rounds', 'table_sessions', 'recommendation_events', 'swipes', 'admin_users', 'app_events')")
            conn.commit()
        seed_if_empty(conn)



def ensureDefaultAdminUser(username="admin", password="admin", role="admin"):
    init_database()
    username = str(username or "admin").strip().lower() or "admin"
    password = str(password or "admin")
    role = str(role or "admin").strip().lower() or "admin"
    with connect_db() as conn:
        row = conn.execute("SELECT id FROM admin_users WHERE lower(username) = lower(?)", (username,)).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO admin_users (username, password_hash, role, active)
                VALUES (?, ?, ?, 1)
                """,
                (username, generate_password_hash(password), role),
            )
            conn.commit()


def authenticateAdmin(username, password, fallback_password=None):
    init_database()
    username = str(username or "admin").strip().lower() or "admin"
    password = str(password or "")
    with connect_db() as conn:
        row = conn.execute(
            "SELECT username, password_hash, role, active FROM admin_users WHERE lower(username) = lower(?)",
            (username,),
        ).fetchone()
    if row and row["active"] and check_password_hash(row["password_hash"], password):
        return {"username": row["username"], "role": row["role"]}
    if fallback_password is not None and password == fallback_password and username == "admin":
        ensureDefaultAdminUser("admin", fallback_password, "admin")
        return {"username": "admin", "role": "admin"}
    return None


def getSchemaMigrations():
    init_database()
    with connect_db() as conn:
        rows = conn.execute("SELECT version, description, applied_at FROM schema_migrations ORDER BY applied_at DESC").fetchall()
    return [dict(row) for row in rows]


def getAdminUsers():
    init_database()
    with connect_db() as conn:
        rows = conn.execute("SELECT username, role, active, created_at FROM admin_users ORDER BY username").fetchall()
    return [dict(row) for row in rows]


def getRestaurantSettings():
    init_database()
    settings = dict(DEFAULT_RESTAURANT_SETTINGS)
    with connect_db() as conn:
        rows = conn.execute("SELECT key, value FROM restaurant_settings").fetchall()
    settings.update({row["key"]: row["value"] for row in rows})
    return settings


def restaurantAcceptsOrders():
    settings = getRestaurantSettings()
    return str(settings.get("acceptingOrders", "true")).strip().lower() in {"1", "true", "yes", "on"}


def getOrderingPauseMessage():
    settings = getRestaurantSettings()
    return settings.get("busyMessage") or "Online ordering is paused right now. Please try again soon."


def updateRestaurantSettings(updates):
    init_database()
    allowed = set(DEFAULT_RESTAURANT_SETTINGS)
    cleaned = {}
    for key in allowed:
        if key in updates:
            cleaned[key] = str(updates.get(key, "")).strip()[:500]
    if "restaurantName" in cleaned and not cleaned["restaurantName"]:
        raise ValueError("Restaurant name is required")
    if "currency" in cleaned:
        cleaned["currency"] = cleaned["currency"][:4] or "$"
    if "acceptingOrders" in cleaned:
        cleaned["acceptingOrders"] = "true" if str(cleaned["acceptingOrders"]).lower() in {"1", "true", "yes", "on"} else "false"
    if "busyMessage" in cleaned and not cleaned["busyMessage"]:
        cleaned["busyMessage"] = DEFAULT_RESTAURANT_SETTINGS["busyMessage"]
    updated_at = datetime.now(timezone.utc).isoformat()
    with connect_db() as conn:
        for key, value in cleaned.items():
            if getattr(conn, "is_postgres", False):
                conn.execute(
                    """
                    INSERT INTO restaurant_settings (key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at
                    """,
                    (key, value, updated_at),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO restaurant_settings (key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                    """,
                    (key, value, updated_at),
                )
        conn.commit()
    return getRestaurantSettings()


def recordAppEvent(level, source, message, path=""):
    init_database()
    created_at = datetime.now(timezone.utc).isoformat()
    with connect_db() as conn:
        conn.execute(
            "INSERT INTO app_events (level, source, message, path, created_at) VALUES (?, ?, ?, ?, ?)",
            (str(level or "info")[:20], str(source or "app")[:80], str(message or "")[:1000], str(path or "")[:240], created_at),
        )
        conn.commit()


def getProductionStatus(limit=20):
    init_database()
    with connect_db() as conn:
        counts = {
            "meals": conn.execute("SELECT COUNT(*) FROM meals").fetchone()[0],
            "orders": conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
            "activeOrders": conn.execute("SELECT COUNT(*) FROM orders WHERE status IN ('new', 'preparing')").fetchone()[0],
            "events": conn.execute("SELECT COUNT(*) FROM app_events").fetchone()[0],
        }
        events = conn.execute(
            "SELECT id, level, source, message, path, created_at FROM app_events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return {
        "database": "postgres" if using_postgres() else "sqlite",
        "status": "ok",
        "counts": counts,
        "recentEvents": [dict(row) for row in events],
        "settings": getRestaurantSettings(),
    }


def exportOrdersCsv():
    init_database()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "meal", "quantity", "table", "customer_name", "customer_phone", "status", "payment_status", "subtotal", "tax", "service_fee", "total", "created_at", "tracking_token"])
    with connect_db() as conn:
        rows = conn.execute("SELECT * FROM orders ORDER BY id DESC").fetchall()
    for row in rows:
        writer.writerow([
            row["id"],
            row["meal_name"],
            row["quantity"],
            row["table_number"],
            row_get(row, "customer_name", default=""),
            row_get(row, "customer_phone", default=""),
            row["status"],
            row["payment_status"],
            row_get(row, "subtotal_price", default=row["total_price"]),
            row_get(row, "tax_price", default=0),
            row_get(row, "service_fee", default=0),
            row["total_price"],
            row["created_at"],
            row["tracking_token"],
        ])
    return output.getvalue()


def exportMealsCsv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["name", "category", "meat_kind", "taste", "available", "stock", "price", "allergens"])
    for meal in getAllMeals():
        writer.writerow([
            meal["name"],
            meal["category"],
            meal["meatKind"],
            meal["taste"],
            "yes" if meal["available"] else "no",
            meal["stock"],
            meal["price"],
            ", ".join(meal.get("allergens", [])),
        ])
    return output.getvalue()
def getAllMeals(include_unavailable=True):
    init_database()
    query = "SELECT * FROM meals"
    params = []
    if not include_unavailable:
        query += " WHERE available = ?"
        params.append(1)
    query += " ORDER BY id"
    with connect_db() as conn:
        return [row_to_meal(row) for row in conn.execute(query, params).fetchall()]


def findMealIndex(name):
    init_database()
    with connect_db() as conn:
        row = conn.execute("SELECT id FROM meals WHERE lower(name) = lower(?)", (name.strip(),)).fetchone()
    return row["id"] if row else None


def getMealByName(name):
    init_database()
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM meals WHERE lower(name) = lower(?)", (name.strip(),)).fetchone()
    return row_to_meal(row) if row else None


def addMeal(meal):
    init_database()
    normalized = normalize_meal(meal)
    validate_meals([normalized])
    try:
        with connect_db() as conn:
            insert_meal(conn, normalized)
            conn.commit()
    except Exception as exc:
        if not is_integrity_error(exc):
            raise
        raise ValueError(f"Meal already exists: {normalized['name']}")
    return getMealByName(normalized["name"])


def updateMealRecord(original_name, updates):
    init_database()
    existing = getMealByName(original_name)
    if existing is None:
        raise ValueError(f"Meal not found: {original_name}")
    updated = normalize_meal({**existing, **updates})
    params = meal_to_params(updated)
    params["original_name"] = original_name.strip()
    try:
        with connect_db() as conn:
            conn.execute(
                """
                UPDATE meals
                SET name = :name,
                    img = :img,
                    description = :description,
                    category = :category,
                    meatKind = :meatKind,
                    taste = :taste,
                    spicy = :spicy,
                    emotion = :emotion,
                    emoji = :emoji,
                    price = :price,
                    allergens = :allergens,
                    available = :available,
                    stock = :stock,
                    low_stock_threshold = :lowStockThreshold,
                    updated_at = CURRENT_TIMESTAMP
                WHERE lower(name) = lower(:original_name)
                """,
                params,
            )
            conn.commit()
    except Exception as exc:
        if not is_integrity_error(exc):
            raise
        raise ValueError(f"Meal already exists: {updated['name']}")
    return getMealByName(updated["name"])


def deleteMealRecord(name):
    init_database()
    existing = getMealByName(name)
    if existing is None:
        raise ValueError(f"Meal not found: {name}")
    with connect_db() as conn:
        conn.execute("DELETE FROM meals WHERE lower(name) = lower(?)", (name.strip(),))
        conn.commit()
    return existing


def row_to_order_item(row):
    return {
        "mealName": row["meal_name"],
        "quantity": row["quantity"],
        "unitPrice": row["unit_price"],
        "totalPrice": row["total_price"],
        "notes": row["notes"],
    }


def getOrderItems(conn, order_id):
    rows = conn.execute(
        """
        SELECT meal_name, quantity, unit_price, total_price, notes
        FROM order_items
        WHERE order_id = ?
        ORDER BY id
        """,
        (order_id,),
    ).fetchall()
    return [row_to_order_item(row) for row in rows]

def recordOrderHistory(conn, order_id, action, from_value="", to_value="", actor="system", note=""):
    conn.execute(
        """
        INSERT INTO order_history (order_id, action, from_value, to_value, actor, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (order_id, str(action or "")[:40], str(from_value or "")[:80], str(to_value or "")[:80], str(actor or "system")[:80], str(note or "")[:240], datetime.now(timezone.utc).isoformat()),
    )


def getOrderHistory(conn, order_id):
    rows = conn.execute(
        """
        SELECT id, order_id, action, from_value, to_value, actor, note, created_at
        FROM order_history
        WHERE order_id = ?
        ORDER BY id DESC
        LIMIT 20
        """,
        (order_id,),
    ).fetchall()
    return [row_to_order_history(row) for row in rows]


def normalize_quantity(quantity):
    try:
        normalized = int(quantity)
    except (TypeError, ValueError):
        raise ValueError("Quantity must be a number")
    if normalized < 1:
        raise ValueError("Quantity must be at least 1")
    return normalized


def parse_setting_number(value):
    try:
        return float(str(value or "0").replace("%", "").strip() or 0)
    except ValueError:
        return 0.0


def calculate_order_totals(subtotal):
    settings = getRestaurantSettings()
    tax_rate = max(0.0, parse_setting_number(settings.get("taxRate")))
    service_fee = max(0.0, parse_setting_number(settings.get("serviceFee")))
    tax_price = round(subtotal * (tax_rate / 100), 2)
    service_fee_price = round(service_fee, 2)
    return {
        "subtotalPrice": round(subtotal, 2),
        "taxPrice": tax_price,
        "serviceFee": service_fee_price,
        "totalPrice": round(subtotal + tax_price + service_fee_price, 2),
    }


def table_session_to_dict(row):
    return {
        "id": row["id"],
        "token": row["token"],
        "tableNumber": row_get(row, "table_number", default=""),
        "guestName": row_get(row, "guest_name", default=""),
        "status": row_get(row, "status", default="open"),
        "createdAt": row_get(row, "created_at", default=""),
        "updatedAt": row_get(row, "updated_at", default=""),
    }


def getTableSessionByToken(token):
    init_database()
    token = str(token or "").strip()
    if not token:
        return None
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM table_sessions WHERE token = ?", (token,)).fetchone()
    return table_session_to_dict(row) if row else None


def createTableSession(table_number="", guest_name=""):
    init_database()
    table_number = str(table_number or "").strip()[:40]
    guest_name = str(guest_name or "").strip()[:80]
    token = uuid.uuid4().hex[:12]
    created_at = datetime.now(timezone.utc).isoformat()
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO table_sessions (token, table_number, guest_name, status, created_at, updated_at)
            VALUES (?, ?, ?, 'open', ?, ?)
            """,
            (token, table_number, guest_name, created_at, created_at),
        )
        conn.commit()
    session["tableSessionToken"] = token
    return getTableSessionByToken(token)


def getOrCreateTableSession(table_number="", guest_name="", token=""):
    init_database()
    token = str(token or session.get("tableSessionToken") or "").strip()
    table_number = str(table_number or "").strip()[:40]
    guest_name = str(guest_name or "").strip()[:80]
    if token:
        existing = getTableSessionByToken(token)
        if existing and existing["status"] == "open":
            with connect_db() as conn:
                conn.execute(
                    """
                    UPDATE table_sessions
                    SET table_number = CASE WHEN ? != '' THEN ? ELSE table_number END,
                        guest_name = CASE WHEN ? != '' THEN ? ELSE guest_name END,
                        updated_at = ?
                    WHERE token = ?
                    """,
                    (table_number, table_number, guest_name, guest_name, datetime.now(timezone.utc).isoformat(), token),
                )
                conn.commit()
            session["tableSessionToken"] = token
            return getTableSessionByToken(token)
    if not table_number:
        return None
    return createTableSession(table_number, guest_name)


def closeTableSession(token):
    init_database()
    token = str(token or "").strip()
    if not token:
        raise ValueError("Table session token is required")
    updated_at = datetime.now(timezone.utc).isoformat()
    with connect_db() as conn:
        cursor = conn.execute(
            "UPDATE table_sessions SET status = 'closed', updated_at = ? WHERE token = ?",
            (updated_at, token),
        )
        conn.commit()
    if cursor.rowcount == 0:
        raise ValueError("Table session not found")
    if session.get("tableSessionToken") == token:
        session.pop("tableSessionToken", None)
    return getTableSessionByToken(token)


def createOrderRound(conn, table_session_token, order_id, subtotal_price, total_price):
    if not table_session_token:
        return 0
    row = conn.execute(
        "SELECT COALESCE(MAX(round_number), 0) AS max_round FROM order_rounds WHERE table_session_token = ?",
        (table_session_token,),
    ).fetchone()
    round_number = int(row_get(row, "max_round", "maxround", default=0) or 0) + 1
    created_at = datetime.now(timezone.utc).isoformat()
    insert_sql = """
        INSERT INTO order_rounds (table_session_token, round_number, order_id, subtotal_price, total_price, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'sent', ?)
    """
    if getattr(conn, "is_postgres", False):
        insert_sql += " RETURNING id"
    cursor = conn.execute(insert_sql, (table_session_token, round_number, order_id, subtotal_price, total_price, created_at))
    return cursor.fetchone()["id"] if getattr(conn, "is_postgres", False) else cursor.lastrowid


def getTableSessionBill(token):
    init_database()
    token = str(token or "").strip()
    table_session = getTableSessionByToken(token)
    if table_session is None:
        raise ValueError("Table session not found")
    with connect_db() as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE table_session_token = ? ORDER BY id ASC",
            (token,),
        ).fetchall()
        orders = []
        for row in rows:
            order = row_to_order(row, getOrderItems(conn, row["id"]))
            order["history"] = getOrderHistory(conn, row["id"])
            orders.append(order)
        round_rows = conn.execute(
            "SELECT * FROM order_rounds WHERE table_session_token = ? ORDER BY round_number ASC",
            (token,),
        ).fetchall()
    active_orders = [order for order in orders if order["status"] != "cancelled"]
    return {
        "session": table_session,
        "orders": orders,
        "rounds": [
            {
                "id": row["id"],
                "roundNumber": row_get(row, "round_number", default=1),
                "orderId": row_get(row, "order_id", default=0),
                "subtotalPrice": row_get(row, "subtotal_price", default=0),
                "totalPrice": row_get(row, "total_price", default=0),
                "status": row_get(row, "status", default="sent"),
                "createdAt": row_get(row, "created_at", default=""),
            }
            for row in round_rows
        ],
        "totals": {
            "orders": len(active_orders),
            "items": sum(order["quantity"] for order in active_orders),
            "subtotalPrice": round(sum(order["subtotalPrice"] for order in active_orders), 2),
            "taxPrice": round(sum(order["taxPrice"] for order in active_orders), 2),
            "serviceFee": round(sum(order["serviceFee"] for order in active_orders), 2),
            "totalPrice": round(sum(order["totalPrice"] for order in active_orders), 2),
        },
    }


def normalize_order_items(items=None, meal_name=None, quantity=1, notes=""):
    if items is None:
        items = [{"mealName": meal_name, "quantity": quantity, "notes": notes}]
    if not isinstance(items, list) or not items:
        raise ValueError("Order needs at least one item")
    normalized = []
    for item in items:
        item_meal_name = str(item.get("mealName") or item.get("meal_name") or "").strip()
        if not item_meal_name:
            raise ValueError("Order item needs a meal name")
        item_quantity = normalize_quantity(item.get("quantity", 1))
        item_notes = str(item.get("notes") or "").strip()[:160]
        meal = getMealByName(item_meal_name)
        if meal is None or not meal.get("available", True):
            raise ValueError(f"Meal not available: {item_meal_name}")
        if meal.get("stock", 0) < item_quantity:
            raise ValueError(f"Not enough stock for: {item_meal_name}")
        unit_price = parse_price(meal.get("price"))
        normalized.append({
            "meal": meal,
            "mealName": meal["name"],
            "quantity": item_quantity,
            "notes": item_notes,
            "unitPrice": unit_price,
            "totalPrice": round(unit_price * item_quantity, 2),
        })
    stock_by_meal = {}
    for item in normalized:
        stock_by_meal[item["mealName"].lower()] = stock_by_meal.get(item["mealName"].lower(), 0) + item["quantity"]
    for key, total_quantity in stock_by_meal.items():
        meal = next(item["meal"] for item in normalized if item["mealName"].lower() == key)
        if meal.get("stock", 0) < total_quantity:
            raise ValueError(f"Not enough stock for: {meal['name']}")
    return normalized


def addOrder(meal_name=None, quantity=1, table_number="", notes="", items=None, customer_name="", customer_phone="", table_session_token=""):
    init_database()
    normalized_items = normalize_order_items(items, meal_name, quantity, notes)
    table_number = str(table_number or "").strip()[:40]
    order_notes = str(notes or "").strip()[:240]
    customer_name = str(customer_name or "").strip()[:80]
    customer_phone = str(customer_phone or "").strip()[:40]
    table_session = getOrCreateTableSession(table_number, customer_name, table_session_token)
    table_session_token = table_session["token"] if table_session else ""
    total_quantity = sum(item["quantity"] for item in normalized_items)
    subtotal_price = round(sum(item["totalPrice"] for item in normalized_items), 2)
    totals = calculate_order_totals(subtotal_price)
    first_item = normalized_items[0]
    display_name = first_item["mealName"] if len(normalized_items) == 1 else f"{first_item['mealName']} + {len(normalized_items) - 1} more"
    unit_price = first_item["unitPrice"] if len(normalized_items) == 1 else 0
    token = uuid.uuid4().hex[:12]
    created_at = datetime.now(timezone.utc).isoformat()
    with connect_db() as conn:
        insert_order_sql = """
            INSERT INTO orders (
                meal_name, quantity, table_number, notes, status,
                tracking_token, unit_price, subtotal_price, tax_price, service_fee, total_price, customer_name, customer_phone, payment_status, estimated_minutes, status_started_at, table_session_token, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'new', ?, ?, ?, ?, ?, ?, ?, ?, 'unpaid', ?, ?, ?, ?, ?)
            """
        if getattr(conn, "is_postgres", False):
            insert_order_sql += " RETURNING id"
        cursor = conn.execute(
            insert_order_sql,
            (display_name, total_quantity, table_number, order_notes, token, unit_price, totals["subtotalPrice"], totals["taxPrice"], totals["serviceFee"], totals["totalPrice"], customer_name, customer_phone, estimate_prep_minutes("new"), created_at, table_session_token, created_at, created_at),
        )
        order_id = cursor.fetchone()["id"] if getattr(conn, "is_postgres", False) else cursor.lastrowid
        round_id = createOrderRound(conn, table_session_token, order_id, totals["subtotalPrice"], totals["totalPrice"])
        if round_id:
            conn.execute("UPDATE orders SET round_id = ? WHERE id = ?", (round_id, order_id))
        recordOrderHistory(conn, order_id, "created", "", "new", "customer", "Order placed")
        for item in normalized_items:
            conn.execute(
                """
                INSERT INTO order_items (order_id, meal_name, quantity, unit_price, total_price, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (order_id, item["mealName"], item["quantity"], item["unitPrice"], item["totalPrice"], item["notes"], created_at),
            )
            conn.execute(
                """
                UPDATE meals
                SET stock = stock - ?,
                    available = CASE WHEN stock - ? <= 0 THEN 0 ELSE available END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE lower(name) = lower(?)
                """,
                (item["quantity"], item["quantity"], item["mealName"]),
            )
        conn.commit()
    return getOrderById(order_id)

def getOrderById(order_id):
    init_database()
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        items = getOrderItems(conn, order_id) if row else []
        history = getOrderHistory(conn, order_id) if row else []
    order = row_to_order(row, items) if row else None
    if order is not None:
        order["history"] = history
    return order


def getOrderByToken(token):
    init_database()
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM orders WHERE tracking_token = ?", (str(token or "").strip(),)).fetchone()
        items = getOrderItems(conn, row["id"]) if row else []
        history = getOrderHistory(conn, row["id"]) if row else []
    order = row_to_order(row, items) if row else None
    if order is not None:
        order["history"] = history
    return order
def getOrders(limit=None, status=None, payment_status=None):
    init_database()
    query = "SELECT * FROM orders"
    params = []
    clauses = []
    if status is not None:
        if status == "active":
            clauses.append("status IN ('new', 'preparing')")
        else:
            if status not in VALID_ORDER_STATUSES:
                raise ValueError(f"Invalid order status: {status}")
            clauses.append("status = ?")
            params.append(status)
    if payment_status:
        payment_status = str(payment_status).strip().lower()
        if payment_status not in VALID_PAYMENT_STATUSES:
            raise ValueError(f"Invalid payment status: {payment_status}")
        clauses.append("payment_status = ?")
        params.append(payment_status)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id DESC"
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    with connect_db() as conn:
        rows = conn.execute(query, params).fetchall()
        orders = []
        for row in rows:
            order = row_to_order(row, getOrderItems(conn, row["id"]))
            order["history"] = getOrderHistory(conn, row["id"])
            orders.append(order)
        return orders


def estimate_prep_minutes(status):
    if status == "completed":
        return 0
    if status == "preparing":
        return 8
    if status == "cancelled":
        return 0
    return 12


def updateOrderPaymentStatus(order_id, payment_status, actor="admin"):
    init_database()
    payment_status = str(payment_status or "").strip().lower()
    if payment_status not in VALID_PAYMENT_STATUSES:
        raise ValueError(f"Invalid payment status: {payment_status}")
    updated_at = datetime.now(timezone.utc).isoformat()
    with connect_db() as conn:
        existing = conn.execute("SELECT payment_status FROM orders WHERE id = ?", (order_id,)).fetchone()
        if existing is None:
            raise ValueError(f"Order not found: {order_id}")
        cursor = conn.execute(
            "UPDATE orders SET payment_status = ?, updated_at = ? WHERE id = ?",
            (payment_status, updated_at, order_id),
        )
        if existing["payment_status"] != payment_status:
            recordOrderHistory(conn, order_id, "payment", existing["payment_status"], payment_status, actor, "Payment status changed")
        conn.commit()
    if cursor.rowcount == 0:
        raise ValueError(f"Order not found: {order_id}")
    return getOrderById(order_id)


def searchOrders(term="", status=None, payment_status=None, limit=50):
    init_database()
    query = "SELECT * FROM orders"
    params = []
    clauses = []
    if status:
        if status == "active":
            clauses.append("status IN ('new', 'preparing')")
        elif status in VALID_ORDER_STATUSES:
            clauses.append("status = ?")
            params.append(status)
        else:
            raise ValueError(f"Invalid order status: {status}")
    if payment_status:
        payment_status = str(payment_status).strip().lower()
        if payment_status not in VALID_PAYMENT_STATUSES:
            raise ValueError(f"Invalid payment status: {payment_status}")
        clauses.append("payment_status = ?")
        params.append(payment_status)
    term = str(term or "").strip()
    if term:
        clauses.append("(CAST(id AS TEXT) = ? OR lower(meal_name) LIKE lower(?) OR lower(table_number) LIKE lower(?) OR lower(status) LIKE lower(?) OR lower(payment_status) LIKE lower(?))")
        like = f"%{term}%"
        params.extend([term, like, like, like, like])
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with connect_db() as conn:
        rows = conn.execute(query, params).fetchall()
        orders = []
        for row in rows:
            order = row_to_order(row, getOrderItems(conn, row["id"]))
            order["history"] = getOrderHistory(conn, row["id"])
            orders.append(order)
        return orders


def getInventorySummary():
    init_database()
    meals = getAllMeals()
    return {
        "lowStock": [meal for meal in meals if meal["available"] and meal["stock"] <= meal["lowStockThreshold"]],
        "soldOut": [meal for meal in meals if not meal["available"] or meal["stock"] <= 0],
        "meals": meals,
    }

def updateOrderStatus(order_id, status, actor="admin"):
    init_database()
    status = str(status or "").strip().lower()
    if status not in VALID_ORDER_STATUSES:
        raise ValueError(f"Invalid order status: {status}")
    updated_at = datetime.now(timezone.utc).isoformat()
    with connect_db() as conn:
        existing = conn.execute("SELECT status, estimated_minutes FROM orders WHERE id = ?", (order_id,)).fetchone()
        if existing is None:
            raise ValueError(f"Order not found: {order_id}")
        estimated_minutes = 0 if status in ("completed", "cancelled") else int(row_get(existing, "estimated_minutes", default=estimate_prep_minutes(status)) or estimate_prep_minutes(status))
        if existing["status"] == status:
            cursor = conn.execute(
                "UPDATE orders SET status = ?, estimated_minutes = ?, updated_at = ? WHERE id = ?",
                (status, estimated_minutes, updated_at, order_id),
            )
        else:
            cursor = conn.execute(
                "UPDATE orders SET status = ?, estimated_minutes = ?, status_started_at = ?, updated_at = ? WHERE id = ?",
                (status, estimated_minutes, updated_at, updated_at, order_id),
            )
            recordOrderHistory(conn, order_id, "status", existing["status"], status, actor, "Order status changed")
        conn.commit()
    if cursor.rowcount == 0:
        raise ValueError(f"Order not found: {order_id}")
    return getOrderById(order_id)


def updateOrderEta(order_id, estimated_minutes, actor="admin"):
    init_database()
    try:
        estimated_minutes = int(estimated_minutes)
    except (TypeError, ValueError):
        raise ValueError("ETA must be a number")
    if estimated_minutes < 0 or estimated_minutes > 180:
        raise ValueError("ETA must be between 0 and 180 minutes")
    updated_at = datetime.now(timezone.utc).isoformat()
    with connect_db() as conn:
        existing = conn.execute("SELECT estimated_minutes FROM orders WHERE id = ?", (order_id,)).fetchone()
        if existing is None:
            raise ValueError(f"Order not found: {order_id}")
        cursor = conn.execute(
            "UPDATE orders SET estimated_minutes = ?, updated_at = ? WHERE id = ?",
            (estimated_minutes, updated_at, order_id),
        )
        if int(row_get(existing, "estimated_minutes", default=0) or 0) != estimated_minutes:
            recordOrderHistory(conn, order_id, "eta", row_get(existing, "estimated_minutes", default=""), estimated_minutes, actor, "ETA changed")
        conn.commit()
    if cursor.rowcount == 0:
        raise ValueError(f"Order not found: {order_id}")
    return getOrderById(order_id)


def getAnalyticsSessionId():
    if "analyticsSessionId" not in session:
        session["analyticsSessionId"] = str(uuid.uuid4())
    return session["analyticsSessionId"]


def recordSwipe(meal_name, liked):
    init_database()
    created_at = datetime.now(timezone.utc).isoformat()
    with connect_db() as conn:
        conn.execute(
            "INSERT INTO swipes (meal_name, liked, session_id, created_at) VALUES (?, ?, ?, ?)",
            (meal_name, 1 if liked else 0, getAnalyticsSessionId(), created_at),
        )
        conn.commit()


def getAdminAnalytics():
    init_database()
    with connect_db() as conn:
        total_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        active_orders = conn.execute("SELECT COUNT(*) FROM orders WHERE status IN ('new', 'preparing')").fetchone()[0]
        total_swipes = conn.execute("SELECT COUNT(*) FROM swipes").fetchone()[0]
        total_recommendations = conn.execute("SELECT COUNT(*) FROM recommendation_events").fetchone()[0]
        open_table_sessions = conn.execute("SELECT COUNT(*) FROM table_sessions WHERE status = 'open'").fetchone()[0]
        total_likes = conn.execute("SELECT COUNT(*) FROM swipes WHERE liked = 1").fetchone()[0]
        total_dislikes = conn.execute("SELECT COUNT(*) FROM swipes WHERE liked = 0").fetchone()[0]
        available_meals = conn.execute("SELECT COUNT(*) FROM meals WHERE available = 1").fetchone()[0]
        hidden_meals = conn.execute("SELECT COUNT(*) FROM meals WHERE available = 0").fetchone()[0]
        revenue_total = conn.execute("SELECT COALESCE(SUM(total_price), 0) FROM orders WHERE status != 'cancelled'").fetchone()[0]
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        today_orders = conn.execute("SELECT COUNT(*) FROM orders WHERE created_at >= ?", (today_start,)).fetchone()[0]
        today_active_orders = conn.execute("SELECT COUNT(*) FROM orders WHERE created_at >= ? AND status IN ('new', 'preparing')", (today_start,)).fetchone()[0]
        today_revenue = conn.execute("SELECT COALESCE(SUM(total_price), 0) FROM orders WHERE created_at >= ? AND status != 'cancelled'", (today_start,)).fetchone()[0]
        payment_rows = conn.execute("SELECT payment_status, COUNT(*) AS count FROM orders GROUP BY payment_status").fetchall()
        status_rows = conn.execute("SELECT status, COUNT(*) AS count FROM orders GROUP BY status").fetchall()
        order_rows = conn.execute(
            """
            SELECT meal_name, SUM(quantity) AS order_count
            FROM order_items
            GROUP BY meal_name
            ORDER BY order_count DESC, meal_name ASC
            LIMIT 10
            """
        ).fetchall()
        low_stock_rows = conn.execute("""
            SELECT * FROM meals
            WHERE available = 1 AND stock <= low_stock_threshold
            ORDER BY stock ASC, name ASC
            LIMIT 10
            """).fetchall()
        swipe_rows = conn.execute(
            """
            SELECT meal_name,
                   SUM(CASE WHEN liked = 1 THEN 1 ELSE 0 END) AS likes,
                   SUM(CASE WHEN liked = 0 THEN 1 ELSE 0 END) AS dislikes,
                   COUNT(*) AS total
            FROM swipes
            GROUP BY meal_name
            ORDER BY total DESC, meal_name ASC
            LIMIT 10
            """
        ).fetchall()

    swipe_stats = []
    for row in swipe_rows:
        total = row["total"] or 0
        likes = row["likes"] or 0
        dislikes = row["dislikes"] or 0
        swipe_stats.append({
            "mealName": row["meal_name"],
            "likes": likes,
            "dislikes": dislikes,
            "total": total,
            "likeRate": round((likes / total) * 100) if total else 0,
        })

    return {
        "totals": {
            "orders": total_orders,
            "activeOrders": active_orders,
            "swipes": total_swipes,
            "recommendations": total_recommendations,
            "openTableSessions": open_table_sessions,
            "likes": total_likes,
            "dislikes": total_dislikes,
            "availableMeals": available_meals,
            "hiddenMeals": hidden_meals,
            "revenue": round(revenue_total or 0, 2),
            "todayOrders": today_orders,
            "todayActiveOrders": today_active_orders,
            "todayRevenue": round(today_revenue or 0, 2),
        },
        "orderStatusCounts": {row["status"]: row["count"] for row in status_rows},
        "paymentStatusCounts": {row["payment_status"]: row["count"] for row in payment_rows},
        "latestOrders": getOrders(limit=8),
        "ordersByMeal": [{"mealName": row["meal_name"], "orders": row["order_count"]} for row in order_rows],
        "lowStockMeals": [row_to_meal(row) for row in low_stock_rows],
        "swipeStats": swipe_stats,
    }


def parse_price(price):
    text = str(price or "")
    digits = "".join(ch for ch in text if ch.isdigit() or ch == ".")
    try:
        return round(float(digits), 2) if digits else 0.0
    except ValueError:
        return 0.0


def order_tracking_url(token):
    return f"/order/{token}"


def meal_matches_filters(meal, filters):
    if not filters:
        return True
    if filters.get("vegetarian") and meal.get("meatKind", "").lower() not in {"vegetarian", "vegan", "none"}:
        return False
    if filters.get("halal") and meal.get("meatKind", "").lower() in {"pork", "bacon", "ham"}:
        return False
    if filters.get("mild") and meal.get("spicy"):
        return False
    if filters.get("spicy") and not meal.get("spicy"):
        return False
    avoided = {item.strip().lower() for item in str(filters.get("avoidAllergens", "")).split(",") if item.strip()}
    allergens = {str(item).lower() for item in meal.get("allergens", [])}
    return not avoided.intersection(allergens)


def filteredMeals(filters=None, include_unavailable=False):
    meals = getAllMeals(include_unavailable=include_unavailable)
    return [meal for meal in meals if meal_matches_filters(meal, filters or {})]


def setDietaryFilters(filters):
    session["dietaryFilters"] = {
        "vegetarian": bool(filters.get("vegetarian")),
        "halal": bool(filters.get("halal")),
        "mild": bool(filters.get("mild")),
        "spicy": bool(filters.get("spicy")),
        "avoidAllergens": str(filters.get("avoidAllergens", "")).strip(),
    }
    session.pop("meals", None)
    session.pop("currentMealIndex", None)
    session.pop("swipeHistory", None)
    session.pop("recommendationReasons", None)
    session.pop("topRecommendations", None)
    initialize_session()
    return session["dietaryFilters"]

init_database()


def initialize_session():
    if "meals" not in session:
        session["meals"] = filteredMeals(session.get("dietaryFilters", {}), include_unavailable=False)
    if "currentMealIndex" not in session:
        session["currentMealIndex"] = 0
    if "userPreferences" not in session:
        session["userPreferences"] = {
            "origin": {},
            "meatKind": {},
            "taste": {},
            "spicy": {},
            "emotion": {},
        }
    if "swipeHistory" not in session:
        session["swipeHistory"] = []


def updatePreferences(meal, liked):
    weight = 1 if liked else -1
    prefs = session["userPreferences"]

    cat = meal.get("category", "Unknown")
    prefs["origin"][cat] = prefs["origin"].get(cat, 0) + (weight * 2)

    mk = meal.get("meatKind", "None")
    prefs["meatKind"][mk] = prefs["meatKind"].get(mk, 0) + (weight * 3)

    spicy_key = "Spicy" if meal.get("spicy") else "Not Spicy"
    prefs["spicy"][spicy_key] = prefs["spicy"].get(spicy_key, 0) + weight

    taste = meal.get("taste", "None")
    prefs["taste"][taste] = prefs["taste"].get(taste, 0) + (weight * 2)

    em = meal.get("emotion", "None")
    prefs["emotion"][em] = prefs["emotion"].get(em, 0) + (weight * 0.5)
    session["userPreferences"] = prefs


def preferenceExplanation(meal):
    prefs = session["userPreferences"]
    reasons = []
    checks = [
        ("category", "origin", meal.get("category")),
        ("meat kind", "meatKind", meal.get("meatKind")),
        ("taste", "taste", meal.get("taste")),
        ("spice level", "spicy", "Spicy" if meal.get("spicy") else "Not Spicy"),
        ("mood", "emotion", meal.get("emotion")),
    ]
    for label, pref_key, value in checks:
        if prefs[pref_key].get(value, 0) > 0:
            reasons.append(f"{label}: {value}")
    return reasons or ["balanced match from your swipes"]


def compute_score(m):
    prefs = session["userPreferences"]
    score = 0
    cat = m.get("category", "Unknown")
    mk = m.get("meatKind", "None")
    spicy_key = "Spicy" if m.get("spicy") else "Not Spicy"
    taste = m.get("taste", "None")
    em = m.get("emotion", "None")
    score += prefs["origin"].get(cat, 0) * 2
    score += prefs["meatKind"].get(mk, 0) * 3
    score += prefs["spicy"].get(spicy_key, 0)
    score += prefs["taste"].get(taste, 0) * 2
    score += prefs["emotion"].get(em, 0) * 0.5
    return score


def get_recommender_model(meals):
    global _RECOMMENDER_MODEL
    if _RECOMMENDER_MODEL is None:
        _RECOMMENDER_MODEL = load_model()
    return _RECOMMENDER_MODEL or train_from_meals(meals)


def getProgress():
    initialize_session()
    total = len(session["meals"])
    current = min(session["currentMealIndex"], total)
    percent = round((current / total) * 100) if total else 0
    return {
        "current": current,
        "total": total,
        "remaining": max(total - current, 0),
        "percent": percent,
    }


def rankedRecommendations(limit=3):
    initialize_session()
    meals = session.get("meals", [])
    acceptable_meals = [m for m in meals if not m.get("disliked", False)]
    if not acceptable_meals:
        acceptable_meals = meals

    model = get_recommender_model(meals)
    learned_scores = ml_scores(meals, session.get("swipeHistory", []), model)

    def final_score(meal):
        rule_score = compute_score(meal)
        ml_score = learned_scores.get(meal.get("name", ""), 0) * 10
        return rule_score + ml_score

    ranked = sorted(acceptable_meals, key=final_score, reverse=True)
    recommendations = []
    for index, meal in enumerate(ranked[:limit], start=1):
        recommendation = copy.deepcopy(meal)
        recommendation["rank"] = index
        recommendation["matchScore"] = round(final_score(meal), 4)
        recommendation["mlScore"] = round(learned_scores.get(meal.get("name", ""), 0), 4)
        recommendation["reasons"] = preferenceExplanation(meal)
        if recommendation["mlScore"] > 0:
            recommendation["reasons"].append("ML similarity from your swipe pattern")
        recommendations.append(recommendation)
    return recommendations


def promptRecommendationExplanation(prompt, meal):
    prompt_tokens = set(re.findall(r"[a-z0-9]+", str(prompt or "").lower()))
    reasons = []
    for value in (meal.get("category"), meal.get("meatKind"), meal.get("taste"), meal.get("emotion")):
        if value and str(value).lower() in prompt_tokens:
            reasons.append(f"matches {value}")
    if meal.get("spicy") and "spicy" in prompt_tokens:
        reasons.append("spicy preference")
    if not meal.get("spicy") and ("mild" in prompt_tokens or "not spicy" in str(prompt or "").lower()):
        reasons.append("mild preference")
    return reasons or ["closest AI food match from menu text"]


def recommendMealsForPrompt(prompt, limit=3):
    init_database()
    prompt = str(prompt or "").strip()[:240]
    meals = getAllMeals(include_unavailable=False)
    if not prompt:
        return rankedRecommendations(limit=limit)
    model = get_recommender_model(meals)
    prompt_vector = vectorize(prompt, model)
    scored = []
    for meal in meals:
        score = cosine_similarity(prompt_vector, vectorize(meal_document(meal), model))
        if score <= 0:
            score = 0
        scored.append((score, meal))
    scored.sort(key=lambda item: (item[0], parse_price(item[1].get("price"))), reverse=True)
    recommendations = []
    for index, (score, meal) in enumerate(scored[:limit], start=1):
        item = copy.deepcopy(meal)
        item["rank"] = index
        item["matchScore"] = round(score * 10, 4)
        item["mlScore"] = round(score, 4)
        item["reasons"] = promptRecommendationExplanation(prompt, meal)
        recommendations.append(item)
    return recommendations


def recordRecommendationEvent(source, query, recommendations, table_session_token=""):
    init_database()
    created_at = datetime.now(timezone.utc).isoformat()
    analytics_session_id = session.get("analyticsSessionId") or getAnalyticsSessionId()
    with connect_db() as conn:
        for item in recommendations:
            conn.execute(
                """
                INSERT INTO recommendation_events (analytics_session_id, table_session_token, source, query, meal_name, score, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analytics_session_id,
                    str(table_session_token or session.get("tableSessionToken") or "").strip(),
                    str(source or "")[:40],
                    str(query or "")[:240],
                    item.get("name", ""),
                    float(item.get("mlScore", 0) or 0),
                    created_at,
                ),
            )
        conn.commit()


def recommendMeals():
    recommendations = rankedRecommendations()
    session["topRecommendations"] = recommendations
    recommended = recommendations[0] if recommendations else None
    session["recommendationReasons"] = recommended.get("reasons", []) if recommended else []
    return recommended


def updateMeal():
    initialize_session()
    meals = session["meals"]
    current_index = session["currentMealIndex"]
    if current_index < len(meals):
        return meals[current_index], False

    final_meal = recommendMeals()
    return final_meal, True


def nextMeal(liked):
    initialize_session()
    meals = session["meals"]
    current_index = session["currentMealIndex"]
    if current_index >= len(meals):
        final_meal = recommendMeals()
        return final_meal, True

    meal = meals[current_index]
    swipeHistory = session["swipeHistory"]
    swipeHistory.append({"mealIndex": current_index, "liked": liked})
    session["swipeHistory"] = swipeHistory

    updatePreferences(meal, liked)
    recordSwipe(meal["name"], liked)
    if not liked:
        meal["disliked"] = True
    current_index += 1
    session["currentMealIndex"] = current_index

    if current_index >= len(meals):
        final_meal = recommendMeals()
        return final_meal, True
    return meals[current_index], False


def resetState():
    session.pop("meals", None)
    session.pop("currentMealIndex", None)
    session.pop("userPreferences", None)
    session.pop("swipeHistory", None)
    session.pop("recommendationReasons", None)
    session.pop("topRecommendations", None)
    initialize_session()


def goBackOneMeal():
    initialize_session()
    swipeHistory = session["swipeHistory"]
    if not swipeHistory:
        return None, False
    last_swipe = swipeHistory.pop()
    session["swipeHistory"] = swipeHistory
    old_index = last_swipe["mealIndex"]
    session["currentMealIndex"] = old_index
    meals = session["meals"]
    meal = meals[old_index]
    updatePreferences(meal, not last_swipe["liked"])
    if not last_swipe["liked"]:
        meal.pop("disliked", None)
        session["meals"] = meals
    session.pop("recommendationReasons", None)
    session.pop("topRecommendations", None)
    return meals[old_index], False
