# file: backend.py
import json

meals = []
userPreferences = {
    "origin": {},
    "meatKind": {},
    "taste": {},
    "spicy": {}
}
currentMealIndex = 0

# NEW: Keep a history of user swipes so we can revert if needed.
# Each entry can be a dict: {"mealIndex": ..., "liked": ...}
swipeHistory = []

def load_meals():
    global meals
    with open("meals_data.json", "r", encoding="utf-8") as file:
        meals = json.load(file)

# Call load_meals on module import (optional)
load_meals()

def updatePreferences(meal, liked):
    """Apply the user's like/dislike to userPreferences."""
    weight = 1 if liked else -1

    cat = meal.get("category", "Unknown")
    userPreferences["origin"][cat] = userPreferences["origin"].get(cat, 0) + (weight * 2)

    mk = meal.get("meatKind", "None")
    userPreferences["meatKind"][mk] = userPreferences["meatKind"].get(mk, 0) + (weight * 3)

    spiciness_key = "Spicy" if meal.get("spicy") else "Not Spicy"
    userPreferences["spicy"][spiciness_key] = userPreferences["spicy"].get(spiciness_key, 0) + weight

    taste = meal.get("taste", "None")
    userPreferences["taste"][taste] = userPreferences["taste"].get(taste, 0) + (weight * 2)

def revertPreferences(meal, liked):
    """
    If the user is "going back," undo the last preference change.
    This is the inverse of updatePreferences.
    """
    weight = -1 if liked else 1  # reverse of update
    cat = meal.get("category", "Unknown")
    userPreferences["origin"][cat] = userPreferences["origin"].get(cat, 0) + (weight * 2)

    mk = meal.get("meatKind", "None")
    userPreferences["meatKind"][mk] = userPreferences["meatKind"].get(mk, 0) + (weight * 3)

    spiciness_key = "Spicy" if meal.get("spicy") else "Not Spicy"
    userPreferences["spicy"][spiciness_key] = userPreferences["spicy"].get(spiciness_key, 0) + weight

    taste = meal.get("taste", "None")
    userPreferences["taste"][taste] = userPreferences["taste"].get(taste, 0) + (weight * 2)

def recommendMeals():
    """Sort the meals based on userPreferences, once user has viewed them all."""
    def meal_score(m):
        score = 0
        cat = m.get("category", "Unknown")
        mk = m.get("meatKind", "None")
        spicy_key = "Spicy" if m.get("spicy") else "Not Spicy"
        taste = m.get("taste", "None")

        score += userPreferences["origin"].get(cat, 0) * 2
        score += userPreferences["meatKind"].get(mk, 0) * 3
        score += userPreferences["spicy"].get(spicy_key, 0)
        score += userPreferences["taste"].get(taste, 0) * 2
        return score

    meals.sort(key=meal_score, reverse=True)

def updateMeal():
    """Return (meal, isMealOfTheDay). If out of meals, show best match."""
    if not meals:
        return (None, False)

    if currentMealIndex >= len(meals):
        recommendMeals()
        return (meals[0], True)
    else:
        return (meals[currentMealIndex], False)

def nextMeal(liked):
    """
    Move forward one meal:
      1) Record the last swipe in swipeHistory
      2) Update preferences
      3) Increment currentMealIndex
      4) Return the new meal
    """
    global currentMealIndex
    meal = meals[currentMealIndex]
    
    # 1) Record the swipe
    swipeHistory.append({"mealIndex": currentMealIndex, "liked": liked})

    # 2) Update user preferences
    updatePreferences(meal, liked)

    # 3) Move to next
    currentMealIndex += 1

    # 4) Return next meal or best match
    if currentMealIndex >= len(meals):
        recommendMeals()
        return (meals[0], True)
    else:
        return (meals[currentMealIndex], False)
    
def resetState():
    """
    Reset global preferences, currentMealIndex, reload the original meals,
    and clear the swipeHistory so we start completely fresh.
    """
    global userPreferences, currentMealIndex, meals, swipeHistory
    
    # Reload meals to restore original ordering
    load_meals()

    # Reset index and preferences
    currentMealIndex = 0
    userPreferences = {
        "origin": {},
        "meatKind": {},
        "taste": {},
        "spicy": {}
    }

    # IMPORTANT: Clear the swipe history, so no 'undo' is possible after a full reset
    swipeHistory.clear()

def goBackOneMeal():
    """
    Revert the last swipe and move currentMealIndex back by 1.
    Return (meal, isMealOfTheDay) for the newly revealed previous meal.
    If there's no swipe history, do nothing special.
    """
    global currentMealIndex

    if not swipeHistory:
        # No previous swipe to revert
        return (None, False)

    # Pop the last swipe
    last_swipe = swipeHistory.pop()
    old_index = last_swipe["mealIndex"]
    liked = last_swipe["liked"]
    meal = meals[old_index]

    # Undo the preference changes
    revertPreferences(meal, liked)

    # Set currentMealIndex back to the old index
    currentMealIndex = old_index

    # Now return (that meal, false) since we obviously haven't finished all swipes
    return (meals[currentMealIndex], False)
