from flask import Flask, render_template, request, redirect, url_for
import json
import os

app = Flask(__name__)

# Load meals from JSON file
with open("meals_data.json", "r") as file:
    meals = json.load(file)

# Track swiping progress
current_meal_index = 0
total_swipes = len(meals)

# User preferences storage
user_preferences = {
    "origin": {},
    "meatKind": {},
    "type": {},
    "taste": {},
    "spicy": {},
}

@app.route("/")
def index():
    """Render the meal selection page or 'Meal of the Day' if swiping is complete."""
    global current_meal_index

    # If swiping is complete, show "Meal of the Day"
    if current_meal_index >= total_swipes:
        best_meal = recommend_best_meal()
        return render_template("meal_of_the_day.html", meal=best_meal)

    meal = meals[current_meal_index]
    meal["img"] = url_for("static", filename=f"meal_images/{os.path.basename(meal['img'])}")

    return render_template("index.html", meal=meal)

def recommend_best_meal():
    """Sort meals based on user preferences and return the best recommendation."""
    def meal_score(meal):
        score = 0
        score += user_preferences["origin"].get(meal["category"], 0) * 2
        score += user_preferences["meatKind"].get(meal["meatKind"], 0) * 3
        score += user_preferences["type"].get("Spicy" if meal["spicy"] else "Not Spicy", 0)
        score += user_preferences["taste"].get(meal["taste"], 0) * 2
        return score

    sorted_meals = sorted(meals, key=meal_score, reverse=True)
    return sorted_meals[0] if sorted_meals else None

@app.route("/swipe/<action>", methods=["POST"])
def swipe(action):
    """Handle Like or Dislike button clicks (swipes)."""
    global current_meal_index
    if current_meal_index >= total_swipes:
        return redirect(url_for("index"))  # Stop swiping if all meals are viewed

    meal = meals[current_meal_index]
    liked = (action == "like")

    # Update user preferences
    weight = 1 if liked else -1
    user_preferences["origin"][meal["category"]] = user_preferences["origin"].get(meal["category"], 0) + weight * 2
    user_preferences["meatKind"][meal["meatKind"]] = user_preferences["meatKind"].get(meal["meatKind"], 0) + weight * 3
    user_preferences["type"]["Spicy" if meal["spicy"] else "Not Spicy"] = user_preferences["type"].get(
        "Spicy" if meal["spicy"] else "Not Spicy", 0
    ) + weight
    user_preferences["taste"][meal["taste"]] = user_preferences["taste"].get(meal["taste"], 0) + weight * 2

    # Move to next meal
    current_meal_index += 1
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)
