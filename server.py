# file: server.py
from flask import Flask, render_template, request, jsonify, redirect, url_for
from backend import (
    updateMeal,
    nextMeal,
    resetState,
    goBackOneMeal,
    meals  # Global meals list for sanity checking
)

app = Flask(__name__)

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
    We assume that the final recommendation (after all swipes) is computed
    by filtering out meals marked as disliked.
    """
    # Ensure that there is at least one meal
    if not meals:
        return redirect(url_for("food_swipe"))
    best_meal = updateMeal()[0]  # updateMeal() returns (meal, isMealOfTheDay)
    return render_template("meal_of_the_day.html", meal=best_meal)


# -------------------------------------------
# AJAX ENDPOINTS
# -------------------------------------------
@app.route("/get_current_meal", methods=["GET"])
def get_current_meal():
    """
    Returns JSON with the current meal and a flag indicating if it's the Meal of the Day.
    Example JSON:
       { "meal": { ... }, "isMealOfTheDay": true/false }
    """
    meal, isMealOfTheDay = updateMeal()
    if not meal:
        return jsonify({"meal": None, "isMealOfTheDay": False})
    return jsonify({"meal": meal, "isMealOfTheDay": isMealOfTheDay})


@app.route("/handle_swipe", methods=["POST"])
def handle_swipe():
    """
    Processes a user swipe (like/dislike) by calling nextMeal(liked) and returns
    JSON with the new meal and a flag if it's the final recommendation.
    """
    data = request.get_json()
    liked = data.get("liked", False)
    
    # Process the swipe and get the next meal.
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
    Resets all global state (preferences, current index, swipe history, and reloads meals)
    and redirects the user to the welcome page.
    """
    resetState()
    return redirect(url_for("welcome"))


# -------------------------------------------
# MAIN
# -------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
