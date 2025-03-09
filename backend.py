# file: backend.py
import json

# Global variables
meals = []
userPreferences = {
    "origin": {},
    "meatKind": {},
    "taste": {},
    "spicy": {},
    "emotion": {}
}
currentMealIndex = 0
swipeHistory = []  # Each entry: {"mealIndex": ..., "liked": ...}

def load_meals():
    global meals
    with open("meals_data.json", "r", encoding="utf-8") as f:
        meals = json.load(f)

# Initially load meals from JSON
load_meals()

def updatePreferences(meal, liked):
    """Update user preferences based on the meal and swipe result."""
    weight = 1 if liked else -1
    cat = meal.get("category", "Unknown")
    userPreferences["origin"][cat] = userPreferences["origin"].get(cat, 0) + (weight * 2)
    
    mk = meal.get("meatKind", "None")
    userPreferences["meatKind"][mk] = userPreferences["meatKind"].get(mk, 0) + (weight * 3)
    
    spicy_key = "Spicy" if meal.get("spicy") else "Not Spicy"
    userPreferences["spicy"][spicy_key] = userPreferences["spicy"].get(spicy_key, 0) + weight
    
    taste = meal.get("taste", "None")
    userPreferences["taste"][taste] = userPreferences["taste"].get(taste, 0) + (weight * 2)
    
    em = meal.get("emotion", "None")
    userPreferences["emotion"][em] = userPreferences["emotion"].get(em, 0) + (weight * 0.5)

def compute_score(m):
    """
    Compute a weighted score for a meal based on the user's preferences.
    The higher the score, the better the meal fits the user's likes.
    """
    score = 0
    cat = m.get("category", "Unknown")
    mk = m.get("meatKind", "None")
    spicy_key = "Spicy" if m.get("spicy") else "Not Spicy"
    taste = m.get("taste", "None")
    em = m.get("emotion", "None")
    
    score += userPreferences["origin"].get(cat, 0) * 2
    score += userPreferences["meatKind"].get(mk, 0) * 3
    score += userPreferences["spicy"].get(spicy_key, 0)
    score += userPreferences["taste"].get(taste, 0) * 2
    score += userPreferences["emotion"].get(em, 0) * 0.5
    return score

def recommendMeals():
    """
    Filter out meals that were swiped left (disliked),
    then sort the acceptable meals by their computed score in descending order.
    Return the top meal as the final recommendation.
    """
    acceptable_meals = [m for m in meals if not m.get("disliked", False)]
    # If all meals are disliked, fallback to the full list.
    if not acceptable_meals:
        acceptable_meals = meals
    acceptable_meals.sort(key=lambda m: compute_score(m), reverse=True)
    return acceptable_meals[0]

def updateMeal():
    """
    Return (meal, isMealOfTheDay) without processing a new swipe.
    If there are still meals left, return the current meal.
    Otherwise, compute and return the final recommendation.
    """
    if currentMealIndex < len(meals):
        return meals[currentMealIndex], False
    else:
        final_meal = recommendMeals()
        return final_meal, True

def nextMeal(liked):
    """
    Process the current meal based on the swipe result, update preferences,
    mark the meal as disliked if necessary, record the swipe, and increment the index.
    If the user has swiped through all meals, filter out disliked meals,
    sort the remaining meals by score, and return the top meal as the final recommendation.
    """
    global currentMealIndex, meals
    if currentMealIndex >= len(meals):
        # Safety check; should normally not occur here.
        return updateMeal()
    
    meal = meals[currentMealIndex]
    swipeHistory.append({"mealIndex": currentMealIndex, "liked": liked})
    updatePreferences(meal, liked)
    
    if not liked:
        meal["disliked"] = True

    currentMealIndex += 1

    if currentMealIndex >= len(meals):
        final_meal = recommendMeals()
        return final_meal, True
    else:
        return meals[currentMealIndex], False

def resetState():
    """
    Fully reset the application state:
      - Reload the original meals from JSON.
      - Reset the current meal index to 0.
      - Clear all user preferences.
      - Clear the swipe history.
    """
    global userPreferences, currentMealIndex, meals, swipeHistory
    load_meals()  # Reload original unsorted meals
    currentMealIndex = 0
    userPreferences = {
        "origin": {},
        "meatKind": {},
        "taste": {},
        "spicy": {},
        "emotion": {}
    }
    swipeHistory.clear()

def goBackOneMeal():
    """
    Revert the last swipe by removing it from swipeHistory,
    undoing its preference update, and decrementing currentMealIndex.
    Return the meal now at that index.
    """
    global currentMealIndex
    if not swipeHistory:
        return None, False
    last_swipe = swipeHistory.pop()
    old_index = last_swipe["mealIndex"]
    liked = last_swipe["liked"]
    # Optionally, you can implement a full revert of the preference update here.
    # For now, we assume that going back simply moves the index back.
    currentMealIndex = old_index
    return meals[currentMealIndex], False
