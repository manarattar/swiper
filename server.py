import logging
import os
import secrets
import time
from collections import defaultdict, deque
from functools import wraps

from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for
from backend import (
    addMeal,
    addOrder,
    authenticateAdmin,
    deleteMealRecord,
    ensureDefaultAdminUser,
    exportMealsCsv,
    exportOrdersCsv,
    filteredMeals,
    getAdminAnalytics,
    getAdminUsers,
    getAllMeals,
    getInventorySummary,
    getOrderByToken,
    getProductionStatus,
    getRestaurantSettings,
    getOrderingPauseMessage,
    getOrders,
    getProgress,
    getSchemaMigrations,
    goBackOneMeal,
    nextMeal,
    resetState,
    recordAppEvent,
    restaurantAcceptsOrders,
    searchOrders,
    setDietaryFilters,
    updateMeal,
    updateMealRecord,
    updateOrderPaymentStatus,
    updateOrderStatus,
    updateRestaurantSettings,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() != "false"
app.config["ADMIN_USERNAME"] = os.environ.get("ADMIN_USERNAME", "admin")
app.config["ADMIN_PASSWORD"] = os.environ.get("ADMIN_PASSWORD", "admin")
app.config["CSRF_ENABLED"] = os.environ.get("CSRF_ENABLED", "true").lower() != "false"
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)
RATE_LIMITS = defaultdict(deque)


def is_admin_authenticated():
    return session.get("admin_authenticated") is True


def current_admin():
    return session.get("admin_user") or {"username": "admin", "role": "admin"}


def wants_json_response():
    return request.path.startswith(("/admin/", "/orders", "/dietary-filters", "/handle_swipe", "/go_back", "/get_current_meal"))


def client_ip():
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr or "unknown"


def rate_limited(bucket, limit, window_seconds):
    now = time.time()
    key = f"{bucket}:{client_ip()}"
    hits = RATE_LIMITS[key]
    while hits and now - hits[0] > window_seconds:
        hits.popleft()
    if len(hits) >= limit:
        return True
    hits.append(now)
    return False


def production_warnings():
    warnings = []
    if app.secret_key == "dev-secret-key-change-me":
        warnings.append("SECRET_KEY is using the development fallback")
    if app.config["ADMIN_PASSWORD"] == "admin":
        warnings.append("ADMIN_PASSWORD is using the development fallback")
    if not app.config.get("SESSION_COOKIE_SECURE"):
        warnings.append("SESSION_COOKIE_SECURE is disabled")
    if not app.config.get("CSRF_ENABLED"):
        warnings.append("CSRF protection is disabled")
    return warnings


def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def csrf_is_valid():
    provided = request.headers.get("X-CSRF-Token") or request.form.get("_csrf")
    return bool(provided and provided == session.get("csrf_token"))


@app.context_processor
def inject_security_helpers():
    return {"csrf_token": csrf_token, "current_admin": current_admin, "restaurant_settings": getRestaurantSettings()}


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; script-src 'self' 'unsafe-inline'; font-src 'self' https://cdnjs.cloudflare.com; connect-src 'self'; frame-ancestors 'none'")
    if request.is_secure or request.headers.get("X-Forwarded-Proto") == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.path.startswith(("/admin", "/kitchen")):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.before_request
def protect_admin_mutations():
    if app.config.get("TESTING") or not app.config.get("CSRF_ENABLED", True):
        return None
    if request.method not in {"POST", "PUT", "DELETE"}:
        return None
    if request.endpoint in {"admin_login"}:
        return None
    if request.path.startswith("/admin") and is_admin_authenticated() and not csrf_is_valid():
        logger.warning("Blocked admin request without a valid CSRF token: %s %s", request.method, request.path)
        return jsonify({"error": "Invalid CSRF token"}), 400
    return None


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if is_admin_authenticated():
            return view(*args, **kwargs)
        if request.path.startswith(("/admin/meals", "/admin/analytics", "/admin/orders", "/admin/inventory", "/admin/qr-codes", "/admin/export", "/admin/system", "/admin/settings", "/kitchen")):
            return jsonify({"error": "Admin login required"}), 401
        return redirect(url_for("admin_login", next=request.path))
    return wrapped


def safe_next_url(value):
    value = value or url_for("admin")
    if value.startswith("/") and not value.startswith("//"):
        return value
    return url_for("admin")


def csv_response(filename, body):
    return Response(
        body,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/landingpage")
def landing():
    return render_template("landingpage.html")


@app.route("/")
def welcome():
    return render_template("welcome.html")


@app.route("/food-swipe")
def food_swipe():
    return render_template("index.html")


@app.route("/menu")
def menu():
    table = request.args.get("table", "")
    return render_template("menu.html", meals=getAllMeals(include_unavailable=False), table_number=table)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    next_url = safe_next_url(request.args.get("next") or url_for("admin"))
    ensureDefaultAdminUser(app.config["ADMIN_USERNAME"], app.config["ADMIN_PASSWORD"], "admin")
    if request.method == "POST":
        username = request.form.get("username", app.config["ADMIN_USERNAME"])
        password = request.form.get("password", "")
        next_url = safe_next_url(request.form.get("next") or url_for("admin"))
        if session.get("admin_login_attempts", 0) >= 5 or (not app.config.get("TESTING") and rate_limited("admin-login", 6, 900)):
            error = "Too many login attempts. Please wait a few minutes."
        else:
            admin_user = authenticateAdmin(username, password, fallback_password=app.config["ADMIN_PASSWORD"])
            if admin_user:
                session["admin_authenticated"] = True
                session["admin_user"] = admin_user
                session.pop("admin_login_attempts", None)
                csrf_token()
                logger.info("Admin login succeeded for %s", admin_user["username"])
                return redirect(next_url)
            session["admin_login_attempts"] = session.get("admin_login_attempts", 0) + 1
            error = "Invalid admin credentials"
            logger.warning("Admin login failed for %s", username)
    return render_template("admin_login.html", error=error, next_url=next_url, username=app.config["ADMIN_USERNAME"])


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin_authenticated", None)
    session.pop("admin_user", None)
    session.pop("csrf_token", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin():
    return render_template("admin.html", meals=getAllMeals())


@app.route("/meal-of-the-day")
def meal_of_the_day():
    meal, _ = updateMeal()
    if not meal:
        return redirect(url_for("food_swipe"))
    recommendations = session.get("topRecommendations", [meal])
    reasons = session.get("recommendationReasons", meal.get("reasons", []))
    return render_template(
        "meal_of_the_day.html",
        meal=meal,
        reasons=reasons,
        recommendations=recommendations,
    )


@app.route("/get_current_meal", methods=["GET"])
def get_current_meal():
    meal, isMealOfTheDay = updateMeal()
    if not meal:
        return jsonify({"meal": None, "isMealOfTheDay": False, "progress": getProgress()})
    return jsonify({"meal": meal, "isMealOfTheDay": isMealOfTheDay, "progress": getProgress()})


@app.route("/handle_swipe", methods=["POST"])
def handle_swipe():
    data = request.get_json() or {}
    liked = data.get("liked", False)
    newMeal, isMealOfTheDay = nextMeal(liked)
    return jsonify({"meal": newMeal, "isMealOfTheDay": isMealOfTheDay, "progress": getProgress()})


@app.route("/go_back", methods=["POST"])
def go_back():
    meal, isMealOfTheDay = goBackOneMeal()
    return jsonify({"meal": meal, "isMealOfTheDay": isMealOfTheDay, "progress": getProgress()})


@app.route("/admin/meals", methods=["GET"])
@admin_required
def admin_meals():
    return jsonify({"meals": getAllMeals()})


@app.route("/admin/meals", methods=["POST"])
@admin_required
def admin_add_meal():
    try:
        meal = addMeal(request.get_json() or {})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    logger.info("Admin %s added meal %s", current_admin()["username"], meal["name"])
    return jsonify({"meal": meal}), 201


@app.route("/admin/meals/<path:name>", methods=["PUT"])
@admin_required
def admin_update_meal(name):
    try:
        meal = updateMealRecord(name, request.get_json() or {})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    logger.info("Admin %s updated meal %s", current_admin()["username"], meal["name"])
    return jsonify({"meal": meal})


@app.route("/admin/meals/<path:name>", methods=["DELETE"])
@admin_required
def admin_delete_meal(name):
    try:
        meal = deleteMealRecord(name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    logger.info("Admin %s deleted meal %s", current_admin()["username"], meal["name"])
    return jsonify({"meal": meal})


@app.route("/admin/analytics", methods=["GET"])
@admin_required
def admin_analytics():
    return jsonify(getAdminAnalytics())


@app.route("/admin/orders/<int:order_id>", methods=["PUT"])
@admin_required
def admin_update_order(order_id):
    data = request.get_json() or {}
    try:
        order = updateOrderStatus(order_id, data.get("status"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    logger.info("Admin %s marked order %s as %s", current_admin()["username"], order_id, order["status"])
    return jsonify({"order": order})


@app.route("/orders", methods=["POST"])
def create_order():
    if not app.config.get("TESTING") and rate_limited("orders", 20, 600):
        return jsonify({"error": "Too many order attempts. Please wait a few minutes."}), 429
    if not restaurantAcceptsOrders():
        return jsonify({"error": getOrderingPauseMessage()}), 403
    data = request.get_json() or {}
    try:
        order = addOrder(
            data.get("mealName", ""),
            quantity=data.get("quantity", 1),
            table_number=data.get("tableNumber", ""),
            notes=data.get("notes", ""),
            items=data.get("items"),
            customer_name=data.get("customerName", ""),
            customer_phone=data.get("customerPhone", ""),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    history = session.get("orderHistory", [])
    history.insert(0, order["trackingToken"])
    session["orderHistory"] = history[:10]
    logger.info("Order %s created for %s", order["id"], order["mealName"])
    return jsonify({"order": order}), 201


@app.route("/orders/history", methods=["GET"])
def order_history():
    tokens = session.get("orderHistory", [])
    orders = [order for token in tokens if (order := getOrderByToken(token)) is not None]
    return jsonify({"orders": orders})


@app.route("/admin/orders/<int:order_id>/payment", methods=["PUT"])
@admin_required
def admin_update_order_payment(order_id):
    data = request.get_json() or {}
    try:
        order = updateOrderPaymentStatus(order_id, data.get("paymentStatus"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    logger.info("Admin %s marked order %s payment as %s", current_admin()["username"], order_id, order["paymentStatus"])
    return jsonify({"order": order})


@app.route("/admin/orders/search", methods=["GET"])
@admin_required
def admin_order_search():
    try:
        orders = searchOrders(request.args.get("q", ""), status=request.args.get("status") or None, payment_status=request.args.get("paymentStatus") or None)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"orders": orders})


@app.route("/admin/inventory", methods=["GET"])
@admin_required
def admin_inventory():
    return jsonify(getInventorySummary())


@app.route("/admin/qr-codes", methods=["GET"])
@admin_required
def admin_qr_codes():
    count = max(1, min(100, int(request.args.get("tables", 12))))
    codes = [{"table": table, "url": url_for("qr_table", table=table, _external=False)} for table in range(1, count + 1)]
    return jsonify({"codes": codes})


@app.route("/admin/export/orders.csv", methods=["GET"])
@admin_required
def admin_export_orders():
    return csv_response("swipeeat-orders.csv", exportOrdersCsv())


@app.route("/admin/export/meals.csv", methods=["GET"])
@admin_required
def admin_export_meals():
    return csv_response("swipeeat-meals.csv", exportMealsCsv())


@app.route("/admin/system", methods=["GET"])
@admin_required
def admin_system_status():
    status = getProductionStatus()
    status["migrations"] = getSchemaMigrations()
    status["admins"] = getAdminUsers()
    status["warnings"] = production_warnings()
    return jsonify(status)


@app.route("/admin/settings", methods=["GET"])
@admin_required
def admin_settings():
    return jsonify({"settings": getRestaurantSettings()})


@app.route("/admin/settings", methods=["PUT"])
@admin_required
def admin_update_settings():
    try:
        settings = updateRestaurantSettings(request.get_json() or {})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    logger.info("Admin %s updated restaurant settings", current_admin()["username"])
    return jsonify({"settings": settings})


@app.route("/dietary-filters", methods=["POST"])
def dietary_filters():
    filters = setDietaryFilters(request.get_json() or {})
    return jsonify({"filters": filters, "meals": filteredMeals(filters)})


@app.route("/order-confirmation/<token>")
def order_confirmation(token):
    order = getOrderByToken(token)
    if order is None:
        return render_template("error.html", status_code=404, title="Order Not Found", message="This confirmation link does not match an order."), 404
    return render_template("order_confirmation.html", order=order)


@app.route("/order/<token>")
def order_tracking(token):
    order = getOrderByToken(token)
    if order is None:
        return render_template("order_tracking.html", order=None), 404
    return render_template("order_tracking.html", order=order)


@app.route("/receipt/<token>")
def receipt(token):
    order = getOrderByToken(token)
    if order is None:
        return render_template("error.html", status_code=404, title="Receipt Not Found", message="This receipt link does not match an order."), 404
    return render_template("receipt.html", order=order)


@app.route("/orders/<token>", methods=["GET"])
def order_status(token):
    order = getOrderByToken(token)
    if order is None:
        return jsonify({"error": "Order not found"}), 404
    return jsonify({"order": order})


@app.route("/qr/<table>")
def qr_table(table):
    return redirect(url_for("menu", table=table))


@app.route("/kitchen")
@admin_required
def kitchen():
    return render_template("kitchen.html")


@app.route("/admin/orders", methods=["GET"])
@admin_required
def admin_orders():
    status = request.args.get("status") or None
    try:
        orders = getOrders(status=status, payment_status=request.args.get("paymentStatus") or None)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"orders": orders})


@app.route("/restart", methods=["POST"])
def restart():
    resetState()
    return redirect(url_for("welcome"))


@app.errorhandler(404)
def not_found(error):
    if wants_json_response():
        return jsonify({"error": "Not found"}), 404
    return render_template("error.html", status_code=404, title="Page Not Found", message="That page does not exist."), 404


@app.errorhandler(500)
def server_error(error):
    logger.exception("Unhandled server error")
    try:
        recordAppEvent("error", "server", str(error), request.path)
    except Exception:
        logger.exception("Could not record app event")
    if wants_json_response():
        return jsonify({"error": "Server error"}), 500
    return render_template("error.html", status_code=500, title="Something Went Wrong", message="Please try again in a moment."), 500


if __name__ == "__main__":
    app.run(debug=True)