# file: backend.py
import json

# --------------------------------------------------------
# GLOBAL STATE
# --------------------------------------------------------
meals = []
userPreferences = {
    "origin": {},
    "meatKind": {},
    "taste": {},
    "spicy": {}
}
currentMealIndex = 0

# --------------------------------------------------------
# LOAD MEALS (INITIALIZE)
# --------------------------------------------------------
def load_meals_from_json():
    """
    Read the 'meals_data.json' file and store the data in the global 'meals' list.
    """
    global meals
    with open("meals_data.json", "r", encoding="utf-8") as file:
        meals = json.load(file)

# Initially load meals when the module is first imported
load_meals_from_json()

# --------------------------------------------------------
# CORE LOGIC FUNCTIONS
# --------------------------------------------------------
def updatePreferences(meal, liked):
    """
    Update user preference scores based on whether the user liked/disliked 'meal'.
    """
    weight = 1 if liked else -1

    # For meal origin
    category = meal.get("category", "Unknown")
    userPreferences["origin"][category] = userPreferences["origin"].get(category, 0) + (weight * 2)

    # For meat kind
    meatKind = meal.get("meatKind", "None")
    userPreferences["meatKind"][meatKind] = userPreferences["meatKind"].get(meatKind, 0) + (weight * 3)

    # Spiciness
    spiciness_key = "Spicy" if meal.get("spicy") else "Not Spicy"
    userPreferences["spicy"][spiciness_key] = userPreferences["spicy"].get(spiciness_key, 0) + weight

    # Taste
    taste = meal.get("taste", "None")
    userPreferences["taste"][taste] = userPreferences["taste"].get(taste, 0) + (weight * 2)


def recommendMeals():
    """
    Sort the 'meals' list by descending alignment with user preferences.
    Called once we've swiped all meals, to find the best match at meals[0].
    """
    def meal_score(m):
        score = 0
        cat = m.get("category", "Unknown")
        kind = m.get("meatKind", "None")
        spicy_key = "Spicy" if m.get("spicy") else "Not Spicy"
        taste = m.get("taste", "None")

        # Weighted scoring (same logic as updatePreferences)
        score += userPreferences["origin"].get(cat, 0) * 2
        score += userPreferences["meatKind"].get(kind, 0) * 3
        score += userPreferences["spicy"].get(spicy_key, 0)
        score += userPreferences["taste"].get(taste, 0) * 2
        return score

    meals.sort(key=meal_score, reverse=True)

def updateMeal():
    """
    Return (meal, isMealOfTheDay).
    If currentMealIndex >= len(meals), we've reached the end and should show the best match.
    """
    if not meals:
        return (None, False)

    if currentMealIndex >= len(meals):
        # All meals have been seen; show best match
        recommendMeals()
        return (meals[0], True)
    else:
        return (meals[currentMealIndex], False)

def nextMeal():
    """
    Move to the next meal in the list. If we're at the end, show the best match.
    Returns (meal, isMealOfTheDay).
    """
    global currentMealIndex
    currentMealIndex += 1

    if currentMealIndex < len(meals):
        return (meals[currentMealIndex], False)
    else:
        recommendMeals()
        return (meals[0], True)

def resetState():
    """
    Reset global preferences, currentMealIndex, and reload meals to their original order.
    This is called when the user clicks "Restart."
    """
    global userPreferences, currentMealIndex, meals

    # Reload meals from the JSON file to restore original ordering
    load_meals_from_json()

    # Reset index and preferences
    currentMealIndex = 0
    userPreferences = {
        "origin": {},
        "meatKind": {},
        "taste": {},
        "spicy": {}
    }
