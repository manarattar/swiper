import tempfile
import unittest
from pathlib import Path

import backend
from server import app


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, SECRET_KEY="test-secret", ADMIN_PASSWORD="test-admin")
        self.client = app.test_client()
        self.original_db_path = backend.DB_PATH
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "swipeeat-test.db"
        backend.init_database(self.db_path, reset=True)

    def tearDown(self):
        backend.DB_PATH = self.original_db_path
        self.tempdir.cleanup()


class SwipeEatTestCase(DatabaseTestCase):
    def test_current_meal_starts_at_first_meal_with_progress(self):
        response = self.client.get("/get_current_meal")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertFalse(data["isMealOfTheDay"])
        self.assertEqual(data["meal"]["name"], "Currywurst")
        self.assertEqual(data["progress"], {
            "current": 0,
            "total": 10,
            "remaining": 10,
            "percent": 0,
        })

    def test_like_updates_preferences_progress_and_go_back_reverses_them(self):
        response = self.client.post("/handle_swipe", json={"liked": True})
        data = response.get_json()

        self.assertEqual(data["progress"]["current"], 1)
        self.assertEqual(data["progress"]["remaining"], 9)
        with self.client.session_transaction() as session:
            self.assertEqual(session["currentMealIndex"], 1)
            self.assertEqual(session["userPreferences"]["origin"]["German"], 2)
            self.assertEqual(session["userPreferences"]["meatKind"]["Pork"], 3)

        response = self.client.post("/go_back")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["meal"]["name"], "Currywurst")
        self.assertEqual(response.get_json()["progress"]["current"], 0)
        with self.client.session_transaction() as session:
            self.assertEqual(session["currentMealIndex"], 0)
            self.assertEqual(session["userPreferences"]["origin"]["German"], 0)
            self.assertEqual(session["userPreferences"]["meatKind"]["Pork"], 0)

    def test_dislike_marks_meal_and_go_back_removes_disliked_flag(self):
        self.client.post("/handle_swipe", json={"liked": False})

        with self.client.session_transaction() as session:
            self.assertTrue(session["meals"][0]["disliked"])

        self.client.post("/go_back")

        with self.client.session_transaction() as session:
            self.assertNotIn("disliked", session["meals"][0])

    def test_finishing_swipes_builds_top_three_recommendations(self):
        for _ in range(10):
            response = self.client.post("/handle_swipe", json={"liked": True})

        data = response.get_json()
        self.assertTrue(data["isMealOfTheDay"])
        self.assertEqual(data["progress"]["percent"], 100)

        with self.client.session_transaction() as session:
            recommendations = session["topRecommendations"]
            self.assertEqual(len(recommendations), 3)
            self.assertEqual([item["rank"] for item in recommendations], [1, 2, 3])
            self.assertIn("reasons", recommendations[0])

        result_page = self.client.get("/meal-of-the-day").get_data(as_text=True)
        self.assertIn("Your Top Matches", result_page)
        self.assertIn("Best match", result_page)
        self.assertIn("data-order-meal", result_page)
        self.assertIn("Order This Match", result_page)

    def test_menu_renders_shared_meal_data(self):
        response = self.client.get("/menu")
        html = response.get_data(as_text=True)
        template = Path("templates/menu.html").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Currywurst", html)
        self.assertIn("Fettuccine Alfredo", html)
        self.assertIn("{{ meals|tojson }}", template)

    def test_restart_resets_session(self):
        self.client.post("/handle_swipe", json={"liked": True})
        self.client.post("/restart")

        with self.client.session_transaction() as session:
            self.assertEqual(session["currentMealIndex"], 0)
            self.assertEqual(session["swipeHistory"], [])
            self.assertEqual(session["userPreferences"]["origin"], {})
            self.assertNotIn("topRecommendations", session)

    def test_order_endpoint_records_order_details(self):
        response = self.client.post("/orders", json={
            "mealName": "Currywurst",
            "quantity": 2,
            "tableNumber": "7",
            "notes": "extra ketchup",
        })

        self.assertEqual(response.status_code, 201)
        order = response.get_json()["order"]
        self.assertEqual(order["mealName"], "Currywurst")
        self.assertEqual(order["quantity"], 2)
        self.assertEqual(order["tableNumber"], "7")
        self.assertEqual(order["notes"], "extra ketchup")
        self.assertEqual(order["status"], "new")
        self.assertEqual(backend.getOrders()[0]["mealName"], "Currywurst")

    def test_order_endpoint_rejects_invalid_quantity(self):
        response = self.client.post("/orders", json={"mealName": "Currywurst", "quantity": 0})

        self.assertEqual(response.status_code, 400)
        self.assertIn("Quantity", response.get_json()["error"])

    def test_swipes_are_recorded_for_admin_analytics(self):
        self.client.post("/handle_swipe", json={"liked": True})
        self.client.post("/handle_swipe", json={"liked": False})

        analytics = backend.getAdminAnalytics()
        self.assertEqual(analytics["totals"]["swipes"], 2)
        self.assertEqual(analytics["totals"]["likes"], 1)
        self.assertEqual(analytics["totals"]["dislikes"], 1)
        self.assertTrue(analytics["swipeStats"])


class AdminMealManagementTestCase(DatabaseTestCase):
    def login_admin(self):
        return self.client.post("/admin/login", data={"password": "test-admin"})

    def test_admin_requires_login(self):
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.headers["Location"])

        api_response = self.client.get("/admin/meals")
        self.assertEqual(api_response.status_code, 401)
        self.assertEqual(api_response.get_json()["error"], "Admin login required")

        analytics_response = self.client.get("/admin/analytics")
        self.assertEqual(analytics_response.status_code, 401)
        self.assertEqual(analytics_response.get_json()["error"], "Admin login required")

        order_response = self.client.put("/admin/orders/1", json={"status": "preparing"})
        self.assertEqual(order_response.status_code, 401)
        self.assertEqual(order_response.get_json()["error"], "Admin login required")

    def test_admin_login_and_logout(self):
        bad_response = self.client.post("/admin/login", data={"password": "wrong"})
        self.assertEqual(bad_response.status_code, 200)
        self.assertIn("Invalid admin credentials", bad_response.get_data(as_text=True))

        good_response = self.login_admin()
        self.assertEqual(good_response.status_code, 302)
        self.assertEqual(self.client.get("/admin").status_code, 200)

        logout_response = self.client.post("/admin/logout")
        self.assertEqual(logout_response.status_code, 302)
        self.assertEqual(self.client.get("/admin/meals").status_code, 401)

    def test_admin_page_renders_after_login(self):
        self.login_admin()
        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Menu Admin", html)
        self.assertIn("Latest Orders", html)
        self.assertIn("Swipe Performance", html)
        self.assertIn("status-select", html)
        self.assertIn("payment-select", html)
        self.assertIn("detail-button", html)
        self.assertIn("metric-today-orders", html)
        self.assertIn("data-payment-filter=", html)
        self.assertIn("updatePaymentStatus", html)
        self.assertIn("live-refresh-state", html)
        self.assertIn("setInterval(() => refreshAnalytics(), 5000)", html)

    def test_admin_can_add_update_and_delete_meal(self):
        new_meal = {
            "name": "Falafel Bowl",
            "img": "static/meal_images/sample_meal.png",
            "description": "Crisp falafel with rice and salad.",
            "category": "Middle Eastern",
            "meatKind": "Vegetarian",
            "taste": "Savory",
            "spicy": False,
            "emotion": "Comforting",
            "emoji": "B",
            "price": "$10.00",
            "allergens": "sesame, gluten",
            "available": True,
        }

        self.login_admin()
        add_response = self.client.post("/admin/meals", json=new_meal)
        self.assertEqual(add_response.status_code, 201)
        self.assertEqual(add_response.get_json()["meal"]["allergens"], ["sesame", "gluten"])
        self.assertIsNotNone(backend.findMealIndex("Falafel Bowl"))

        update_response = self.client.put("/admin/meals/Falafel%20Bowl", json={"price": "$11.00", "available": False})
        self.assertEqual(update_response.status_code, 200)
        self.assertFalse(update_response.get_json()["meal"]["available"])

        public_menu = self.client.get("/menu").get_data(as_text=True)
        self.assertNotIn("Falafel Bowl", public_menu)

        delete_response = self.client.delete("/admin/meals/Falafel%20Bowl")
        self.assertEqual(delete_response.status_code, 200)
        self.assertIsNone(backend.findMealIndex("Falafel Bowl"))

    def test_sqlite_persists_admin_changes(self):
        self.login_admin()
        self.client.post("/admin/meals", json={
            "name": "Rice Bowl",
            "img": "static/meal_images/sample_meal.png",
            "description": "Rice with vegetables.",
            "category": "Fusion",
            "meatKind": "Vegetarian",
            "taste": "Savory",
            "spicy": False,
            "emotion": "Comforting",
            "emoji": "R",
            "available": True,
        })

        backend.init_database(self.db_path)
        names = [meal["name"] for meal in backend.getAllMeals()]
        self.assertIn("Rice Bowl", names)

    def test_admin_analytics_includes_orders_and_swipes(self):
        self.client.post("/orders", json={"mealName": "Currywurst", "quantity": 3})
        self.client.post("/handle_swipe", json={"liked": True})
        self.login_admin()

        response = self.client.get("/admin/analytics")

        self.assertEqual(response.status_code, 200)
        analytics = response.get_json()
        self.assertEqual(analytics["totals"]["orders"], 1)
        self.assertEqual(analytics["totals"]["activeOrders"], 1)
        self.assertEqual(analytics["totals"]["todayOrders"], 1)
        self.assertIn("todayRevenue", analytics["totals"])
        self.assertEqual(analytics["latestOrders"][0]["mealName"], "Currywurst")
        self.assertEqual(analytics["latestOrders"][0]["status"], "new")
        self.assertEqual(analytics["ordersByMeal"][0]["orders"], 3)
        self.assertEqual(analytics["ordersByMeal"][0]["mealName"], "Currywurst")
        self.assertEqual(analytics["totals"]["swipes"], 1)

    def test_admin_can_update_order_status(self):
        order_response = self.client.post("/orders", json={"mealName": "Currywurst"})
        order_id = order_response.get_json()["order"]["id"]
        self.login_admin()

        response = self.client.put(f"/admin/orders/{order_id}", json={"status": "preparing"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["order"]["status"], "preparing")
        self.assertEqual(backend.getOrders()[0]["status"], "preparing")

        bad_response = self.client.put(f"/admin/orders/{order_id}", json={"status": "ready"})
        self.assertEqual(bad_response.status_code, 400)


class NextLevelWorkflowTestCase(DatabaseTestCase):
    def login_admin(self):
        return self.client.post("/admin/login", data={"password": "test-admin"})

    def test_order_returns_tracking_total_and_tracking_page_updates(self):
        response = self.client.post("/orders", json={"mealName": "Currywurst", "quantity": 2, "tableNumber": "4"})
        self.assertEqual(response.status_code, 201)
        order = response.get_json()["order"]
        self.assertIn("trackingToken", order)
        self.assertIn("trackingUrl", order)
        self.assertIn("totalPrice", order)
        tracking_response = self.client.get(order["trackingUrl"])
        self.assertEqual(tracking_response.status_code, 200)
        self.assertIn(f"Order #{order['id']}", tracking_response.get_data(as_text=True))
        status_response = self.client.get(f"/orders/{order['trackingToken']}")
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.get_json()["order"]["id"], order["id"])

    def test_qr_table_prefills_menu(self):
        response = self.client.get("/qr/12")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/menu?table=12", response.headers["Location"])
        menu = self.client.get("/menu?table=12").get_data(as_text=True)
        self.assertIn('value="12"', menu)

    def test_dietary_filters_reduce_available_meals(self):
        response = self.client.post("/dietary-filters", json={"halal": True})
        self.assertEqual(response.status_code, 200)
        names = [meal["name"] for meal in response.get_json()["meals"]]
        self.assertNotIn("Currywurst", names)

    def test_kitchen_requires_admin_and_lists_active_orders(self):
        self.client.post("/orders", json={"mealName": "Currywurst"})
        self.assertEqual(self.client.get("/kitchen").status_code, 401)
        self.login_admin()
        kitchen = self.client.get("/kitchen")
        self.assertEqual(kitchen.status_code, 200)
        self.assertIn("Start Preparing", kitchen.get_data(as_text=True))
        self.assertIn("badge-paid", kitchen.get_data(as_text=True))
        active = self.client.get("/admin/orders?status=active")
        self.assertEqual(active.status_code, 200)
        self.assertEqual(active.get_json()["orders"][0]["status"], "new")

    def test_stock_decrements_and_sold_out_meals_hide(self):
        self.login_admin()
        self.client.put("/admin/meals/Currywurst", json={"stock": 1, "lowStockThreshold": 1})
        response = self.client.post("/orders", json={"mealName": "Currywurst", "quantity": 1})
        self.assertEqual(response.status_code, 201)
        meal = backend.getMealByName("Currywurst")
        self.assertEqual(meal["stock"], 0)
        self.assertFalse(meal["available"])
        self.assertNotIn("Currywurst", self.client.get("/menu").get_data(as_text=True))

class FinalUpgradeTestCase(DatabaseTestCase):
    def login_admin(self):
        return self.client.post("/admin/login", data={"password": "test-admin"})

    def test_order_history_tracks_current_session_orders(self):
        self.client.post("/orders", json={"mealName": "Currywurst"})
        response = self.client.get("/orders/history")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["orders"][0]["mealName"], "Currywurst")
        self.assertIn("estimatedMinutes", response.get_json()["orders"][0])

    def test_admin_can_update_payment_status(self):
        order = self.client.post("/orders", json={"mealName": "Currywurst"}).get_json()["order"]
        self.login_admin()
        response = self.client.put(f"/admin/orders/{order['id']}/payment", json={"paymentStatus": "paid"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["order"]["paymentStatus"], "paid")

    def test_admin_search_inventory_and_qr_generator(self):
        self.client.post("/orders", json={"mealName": "Currywurst", "tableNumber": "9"})
        self.login_admin()
        search = self.client.get("/admin/orders/search?q=9")
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.get_json()["orders"][0]["tableNumber"], "9")

        paid_order = backend.updateOrderPaymentStatus(search.get_json()["orders"][0]["id"], "paid")
        payment_filter = self.client.get("/admin/orders?paymentStatus=paid")
        self.assertEqual(payment_filter.status_code, 200)
        self.assertEqual(payment_filter.get_json()["orders"][0]["id"], paid_order["id"])
        search_paid = self.client.get("/admin/orders/search?paymentStatus=paid")
        self.assertEqual(search_paid.status_code, 200)
        self.assertEqual(search_paid.get_json()["orders"][0]["paymentStatus"], "paid")

        inventory = self.client.get("/admin/inventory")
        self.assertEqual(inventory.status_code, 200)
        self.assertIn("lowStock", inventory.get_json())
        self.assertIn("soldOut", inventory.get_json())

        qr = self.client.get("/admin/qr-codes?tables=3")
        self.assertEqual(qr.status_code, 200)
        self.assertEqual(len(qr.get_json()["codes"]), 3)
        self.assertEqual(qr.get_json()["codes"][0]["url"], "/qr/1")

    def test_login_rate_limit_blocks_after_failures(self):
        for _ in range(5):
            self.client.post("/admin/login", data={"password": "wrong"})
        response = self.client.post("/admin/login", data={"password": "test-admin"})
        self.assertIn("Too many login attempts", response.get_data(as_text=True))


class OfficialReadinessTestCase(DatabaseTestCase):
    def login_admin(self):
        return self.client.post("/admin/login", data={"username": "admin", "password": "test-admin"})

    def test_admin_login_accepts_username_and_sets_admin_session(self):
        response = self.login_admin()
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertTrue(session["admin_authenticated"])
            self.assertEqual(session["admin_user"]["username"], "admin")
            self.assertEqual(session["admin_user"]["role"], "admin")
            self.assertIn("csrf_token", session)

    def test_admin_exports_orders_and_meals_as_csv(self):
        self.client.post("/orders", json={"mealName": "Currywurst", "quantity": 2, "tableNumber": "3"})
        self.login_admin()

        orders = self.client.get("/admin/export/orders.csv")
        self.assertEqual(orders.status_code, 200)
        self.assertIn("text/csv", orders.content_type)
        self.assertIn("Currywurst", orders.get_data(as_text=True))
        self.assertIn("payment_status", orders.get_data(as_text=True))

        meals = self.client.get("/admin/export/meals.csv")
        self.assertEqual(meals.status_code, 200)
        self.assertIn("Currywurst", meals.get_data(as_text=True))
        self.assertIn("stock", meals.get_data(as_text=True))

    def test_receipt_page_renders_for_order_tracking_token(self):
        order = self.client.post("/orders", json={"mealName": "Currywurst"}).get_json()["order"]
        response = self.client.get(f"/receipt/{order['trackingToken']}")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("SwipeEat Receipt", html)
        self.assertIn(f"Order #{order['id']}", html)

    def test_admin_system_status_exposes_migrations_without_password_hashes(self):
        self.login_admin()
        response = self.client.get("/admin/system")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["migrations"])
        self.assertEqual(payload["admins"][0]["username"], "admin")
        self.assertNotIn("password_hash", payload["admins"][0])

    def test_csrf_blocks_admin_mutation_outside_testing_mode(self):
        original_testing = app.config.get("TESTING")
        try:
            app.config["TESTING"] = False
            self.login_admin()
            response = self.client.post("/admin/meals", json={"name": "Blocked"})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.get_json()["error"], "Invalid CSRF token")
        finally:
            app.config["TESTING"] = original_testing
if __name__ == "__main__":
    unittest.main()