# file: backend.py
import json
from flask import session

ORIGINAL_MEALS = []
# Load the original meals once
def load_original_meals():
    global ORIGINAL_MEALS
    with open("meals_data.json", "r", encoding="utf-8") as f:
        ORIGINAL_MEALS = json.load(f)
load_original_meals()

def initialize_session():
    """
    Initialize user-specific state in the session if not already present.
    """
    if "meals" not in session:
        # Store a copy of the original meals in session (each user gets their own copy)
        session["meals"] = ORIGINAL_MEALS.copy()
    if "currentMealIndex" not in session:
        session["currentMealIndex"] = 0
    if "userPreferences" not in session:
        session["userPreferences"] = {
            "origin": {},
            "meatKind": {},
            "taste": {},
            "spicy": {},
            "emotion": {}
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

def recommendMeals():
    """
    Filters out disliked meals from session["meals"],
    sorts the acceptable meals by computed score, and returns the best one.
    """
    meals = session.get("meals", [])
    acceptable_meals = [m for m in meals if not m.get("disliked", False)]
    if not acceptable_meals:
        acceptable_meals = meals  # fallback if all are disliked
    acceptable_meals.sort(key=lambda m: compute_score(m), reverse=True)
    # Update the session's meals list to be only acceptable meals.
    session["meals"] = acceptable_meals
    return acceptable_meals[0]

def updateMeal():
    """
    Return (meal, isMealOfTheDay) from session.
    """
    initialize_session()
    meals = session["meals"]
    current_index = session["currentMealIndex"]
    if current_index < len(meals):
        return meals[current_index], False
    else:
        final_meal = recommendMeals()
        return final_meal, True

def nextMeal(liked):
    """
    Process the current meal swipe, update preferences, record swipe,
    mark meal as disliked if needed, and increment the index.
    """
    initialize_session()
    meals = session["meals"]
    current_index = session["currentMealIndex"]
    if current_index >= len(meals):
        # Already at end; return final recommendation.
        final_meal = recommendMeals()
        return final_meal, True

    meal = meals[current_index]
    swipeHistory = session["swipeHistory"]
    swipeHistory.append({"mealIndex": current_index, "liked": liked})
    session["swipeHistory"] = swipeHistory

    updatePreferences(meal, liked)
    if not liked:
        meal["disliked"] = True
    current_index += 1
    session["currentMealIndex"] = current_index

    if current_index >= len(meals):
        final_meal = recommendMeals()
        return final_meal, True
    else:
        return meals[current_index], False

def resetState():
    """
    Fully reset session state.
    """
    session.pop("meals", None)
    session.pop("currentMealIndex", None)
    session.pop("userPreferences", None)
    session.pop("swipeHistory", None)
    initialize_session()

def goBackOneMeal():
    """
    Revert the last swipe.
    """
    initialize_session()
    swipeHistory = session["swipeHistory"]
    if not swipeHistory:
        return None, False
    last_swipe = swipeHistory.pop()
    session["swipeHistory"] = swipeHistory
    old_index = last_swipe["mealIndex"]
    # Here, you might want to revert preferences. For simplicity, we only change the index.
    session["currentMealIndex"] = old_index
    meals = session["meals"]
    return meals[old_index], False
