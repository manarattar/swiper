# file: server.py
from flask import Flask, render_template, request, jsonify, redirect, url_for
from backend import (
    updateMeal,
    nextMeal,
    updatePreferences,
    resetState,
    meals,
    currentMealIndex
)

app = Flask(__name__)

# -------------------------------------------
# PAGES
# -------------------------------------------
@app.route("/")
def welcome():
    """
    Renders the welcome page (welcome.html).
    """
    return render_template("welcome.html")


@app.route("/food-swipe")
def food_swipe():
    """
    Renders the main swiping interface (index.html).
    """
    return render_template("index.html")


@app.route("/meal-of-the-day")
def meal_of_the_day():
    """
    Shows the final best match on meal_of_the_day.html.
    We'll assume the best match is always at meals[0] after sorting.
    """
    if not meals:
        # If for some reason no meals exist, just go back to swiping
        return redirect(url_for("food_swipe"))

    best_meal = meals[0]
    return render_template("meal_of_the_day.html", meal=best_meal)

# -------------------------------------------
# AJAX ENDPOINTS
# -------------------------------------------
@app.route("/get_current_meal", methods=["GET"])
def get_current_meal():
    """
    Returns JSON:
    {
      "meal": {...},
      "isMealOfTheDay": true/false
    }
    Called from script.js on the swiping page.
    """
    meal, isMealOfTheDay = updateMeal()
    if not meal:
        return jsonify({"meal": None, "isMealOfTheDay": False})
    
    return jsonify({"meal": meal, "isMealOfTheDay": isMealOfTheDay})


@app.route("/handle_swipe", methods=["POST"])
def handle_swipe():
    """
    Updates preferences based on user swipe (like/dislike),
    moves to the next meal, returns JSON for the new meal or the best match.
    """
    data = request.get_json()
    liked = data.get("liked", False)

    # Ensure we have a current meal to reference
    currentMeal, _ = updateMeal()
    if not currentMeal:
        return jsonify({"meal": None, "isMealOfTheDay": False})

    # Update preferences
    updatePreferences(currentMeal, liked)

    # Get the next meal (or best match if we are at the end)
    newMeal, isMealOfTheDay = nextMeal()
    return jsonify({"meal": newMeal, "isMealOfTheDay": isMealOfTheDay})

# -------------------------------------------
# RESTART
# -------------------------------------------
@app.route("/restart", methods=["POST"])
def restart():
    """
    Resets all global state in backend.py and redirects user to the welcome page.
    """
    resetState()
    return redirect(url_for("welcome"))

# -------------------------------------------
# MAIN
# -------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
