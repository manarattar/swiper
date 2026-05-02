import copy
import csv
import io
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from flask import session
from werkzeug.security import check_password_hash, generate_password_hash

DATA_FILE = "meals_data.json"
DB_PATH = os.environ.get("DATABASE_PATH", "swipeeat.db")
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
SCHEMA_VERSION = "2026-05-02-multi-item-orders"


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


@contextmanager
def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def ensure_column(conn, table, column, definition):
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
            total_price REAL NOT NULL DEFAULT 0,
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
    ensure_column(conn, "orders", "total_price", "REAL NOT NULL DEFAULT 0")
    ensure_column(conn, "orders", "payment_status", "TEXT NOT NULL DEFAULT 'unpaid'")
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
        CREATE TABLE IF NOT EXISTS swipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meal_name TEXT NOT NULL,
            liked INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
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


def row_to_meal(row):
    return {
        "name": row["name"],
        "img": row["img"],
        "description": row["description"],
        "category": row["category"],
        "meatKind": row["meatKind"],
        "taste": row["taste"],
        "spicy": bool(row["spicy"]),
        "emotion": row["emotion"],
        "emoji": row["emoji"],
        "price": row["price"],
        "allergens": json.loads(row["allergens"] or "[]"),
        "available": bool(row["available"]),
        "stock": row["stock"],
        "lowStockThreshold": row["low_stock_threshold"],
        "lowStock": row["stock"] <= row["low_stock_threshold"],
    }


def row_to_order(row, items=None):
    items = items or []
    display_name = row["meal_name"]
    if len(items) > 1:
        display_name = f"{items[0]['mealName']} + {len(items) - 1} more"
    return {
        "id": row["id"],
        "mealName": display_name,
        "quantity": row["quantity"],
        "tableNumber": row["table_number"],
        "notes": row["notes"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "trackingToken": row["tracking_token"],
        "trackingUrl": order_tracking_url(row["tracking_token"]),
        "unitPrice": row["unit_price"],
        "totalPrice": row["total_price"],
        "paymentStatus": row["payment_status"],
        "estimatedMinutes": estimate_prep_minutes(row["status"]),
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
            conn.execute("DELETE FROM meals")
            conn.execute("DELETE FROM admin_users")
            conn.execute("DELETE FROM schema_migrations WHERE version != ?", (SCHEMA_VERSION,))
            conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('meals', 'orders', 'order_items', 'swipes', 'admin_users')")
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


def exportOrdersCsv():
    init_database()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "meal", "quantity", "table", "status", "payment_status", "total", "created_at", "tracking_token"])
    with connect_db() as conn:
        rows = conn.execute("SELECT * FROM orders ORDER BY id DESC").fetchall()
    for row in rows:
        writer.writerow([
            row["id"],
            row["meal_name"],
            row["quantity"],
            row["table_number"],
            row["status"],
            row["payment_status"],
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
    except sqlite3.IntegrityError:
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
    except sqlite3.IntegrityError:
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

def normalize_quantity(quantity):
    try:
        normalized = int(quantity)
    except (TypeError, ValueError):
        raise ValueError("Quantity must be a number")
    if normalized < 1:
        raise ValueError("Quantity must be at least 1")
    return normalized


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


def addOrder(meal_name=None, quantity=1, table_number="", notes="", items=None):
    init_database()
    normalized_items = normalize_order_items(items, meal_name, quantity, notes)
    table_number = str(table_number or "").strip()[:40]
    order_notes = str(notes or "").strip()[:240]
    total_quantity = sum(item["quantity"] for item in normalized_items)
    total_price = round(sum(item["totalPrice"] for item in normalized_items), 2)
    first_item = normalized_items[0]
    display_name = first_item["mealName"] if len(normalized_items) == 1 else f"{first_item['mealName']} + {len(normalized_items) - 1} more"
    unit_price = first_item["unitPrice"] if len(normalized_items) == 1 else 0
    token = uuid.uuid4().hex[:12]
    created_at = datetime.now(timezone.utc).isoformat()
    with connect_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO orders (
                meal_name, quantity, table_number, notes, status,
                tracking_token, unit_price, total_price, payment_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'new', ?, ?, ?, 'unpaid', ?, ?)
            """,
            (display_name, total_quantity, table_number, order_notes, token, unit_price, total_price, created_at, created_at),
        )
        order_id = cursor.lastrowid
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
    return row_to_order(row, items) if row else None



def getOrderByToken(token):
    init_database()
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM orders WHERE tracking_token = ?", (str(token or "").strip(),)).fetchone()
        items = getOrderItems(conn, row["id"]) if row else []
    return row_to_order(row, items) if row else None
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
        return [row_to_order(row, getOrderItems(conn, row["id"])) for row in rows]


def estimate_prep_minutes(status):
    if status == "completed":
        return 0
    if status == "preparing":
        return 8
    if status == "cancelled":
        return 0
    return 12


def updateOrderPaymentStatus(order_id, payment_status):
    init_database()
    payment_status = str(payment_status or "").strip().lower()
    if payment_status not in VALID_PAYMENT_STATUSES:
        raise ValueError(f"Invalid payment status: {payment_status}")
    updated_at = datetime.now(timezone.utc).isoformat()
    with connect_db() as conn:
        cursor = conn.execute(
            "UPDATE orders SET payment_status = ?, updated_at = ? WHERE id = ?",
            (payment_status, updated_at, order_id),
        )
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
        return [row_to_order(row, getOrderItems(conn, row["id"])) for row in rows]


def getInventorySummary():
    init_database()
    meals = getAllMeals()
    return {
        "lowStock": [meal for meal in meals if meal["available"] and meal["stock"] <= meal["lowStockThreshold"]],
        "soldOut": [meal for meal in meals if not meal["available"] or meal["stock"] <= 0],
        "meals": meals,
    }

def updateOrderStatus(order_id, status):
    init_database()
    status = str(status or "").strip().lower()
    if status not in VALID_ORDER_STATUSES:
        raise ValueError(f"Invalid order status: {status}")
    updated_at = datetime.now(timezone.utc).isoformat()
    with connect_db() as conn:
        cursor = conn.execute(
            "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
            (status, updated_at, order_id),
        )
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
            FROM orders
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

    ranked = sorted(acceptable_meals, key=lambda m: compute_score(m), reverse=True)
    recommendations = []
    for index, meal in enumerate(ranked[:limit], start=1):
        recommendation = copy.deepcopy(meal)
        recommendation["rank"] = index
        recommendation["matchScore"] = compute_score(meal)
        recommendation["reasons"] = preferenceExplanation(meal)
        recommendations.append(recommendation)
    return recommendations


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