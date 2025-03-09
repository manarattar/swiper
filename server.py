# file: server.py
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from backend import (
    updateMeal,
    nextMeal,
    resetState,
    goBackOneMeal
)

app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # Replace with a secure random key in production

# -------------------------------------------
# PAGE ROUTES
# -------------------------------------------
@app.route("/landingpage")
def landing():
    """Render the landing page."""
    return render_template("landingpage.html")

@app.route("/")
def welcome():
    """Render the welcome page."""
    return render_template("welcome.html")

@app.route("/food-swipe")
def food_swipe():
    """Render the main swiping interface."""
    return render_template("index.html")

@app.route("/meal-of-the-day")
def meal_of_the_day():
    """
    Render the final recommendation page (Meal of the Day).
    Assumes the final recommendation (after all swipes) is computed
    using the session-managed state.
    """
    meal, _ = updateMeal()
    if not meal:
        return redirect(url_for("food_swipe"))
    return render_template("meal_of_the_day.html", meal=meal)

# -------------------------------------------
# AJAX ENDPOINTS
# -------------------------------------------
@app.route("/get_current_meal", methods=["GET"])
def get_current_meal():
    """
    Returns JSON with the current meal and a flag indicating if it's the Meal of the Day.
    Expected JSON format:
       { "meal": { ... }, "isMealOfTheDay": true/false }
    """
    meal, isMealOfTheDay = updateMeal()
    if not meal:
        return jsonify({"meal": None, "isMealOfTheDay": False})
    return jsonify({"meal": meal, "isMealOfTheDay": isMealOfTheDay})

@app.route("/handle_swipe", methods=["POST"])
def handle_swipe():
    """
    Processes a user swipe (like/dislike) by calling nextMeal(liked)
    and returns JSON with the new meal and a flag if it's the final recommendation.
    """
    data = request.get_json()
    liked = data.get("liked", False)
    newMeal, isMealOfTheDay = nextMeal(liked)
    return jsonify({"meal": newMeal, "isMealOfTheDay": isMealOfTheDay})

@app.route("/go_back", methods=["POST"])
def go_back():
    """
    Reverts the last swipe and returns the previous meal.
    """
    meal, isMealOfTheDay = goBackOneMeal()
    return jsonify({"meal": meal, "isMealOfTheDay": isMealOfTheDay})

@app.route("/restart", methods=["POST"])
def restart():
    """
    Resets all user-specific state (preferences, current index, swipe history, and meal list)
    and redirects the user to the welcome page.
    """
    resetState()
    return redirect(url_for("welcome"))

# -------------------------------------------
# MAIN
# -------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
