from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from collections import Counter
import random

app = FastAPI()

# Sample meal dataset
meals = [
    {
        "name": "Currywurst",
        "img": "static/meal_images/Currywurst.png",
        "description": "German sausage served with a tangy curry ketchup sauce.",
        "category": "German",
        "meatKind": "Pork",
        "taste": "Savory",
        "spicy": False,
        "emotion": "Exciting"
    },
    {
        "name": "Fettuccine Alfredo",
        "img": "static/meal_images/Fettuccine_Alfredo.png",
        "description": "Creamy pasta dish made with butter, cream, and Parmesan cheese.",
        "category": "Italian",
        "meatKind": "Vegetarian",
        "taste": "Savory",
        "spicy": False,
        "emotion": "Comforting"
    },
    {
        "name": "Samosas",
        "img": "static/meal_images/Samosas.png",
        "description": "Deep-fried pastries filled with spiced potatoes, peas, or meat.",
        "category": "Indian",
        "meatKind": "Vegetarian",
        "taste": "Savory",
        "spicy": True,
        "emotion": "Exciting"
    },
    {
        "name": "Pho Ga",
        "img": "static/meal_images/Pho_Ga.png",
        "description": "Vietnamese chicken noodle soup with aromatic herbs.",
        "category": "Vietnamese",
        "meatKind": "Chicken",
        "taste": "Savory",
        "spicy": False,
        "emotion": "Refreshing"
    },
    {
        "name": "Carbonara",
        "img": "static/meal_images/Carbonara.png",
        "description": "Italian pasta with eggs, cheese, pancetta, and black pepper.",
        "category": "Italian",
        "meatKind": "Pork",
        "taste": "Savory",
        "spicy": False,
        "emotion": "Comforting"
    },
    {
        "name": "Gyros",
        "img": "static/meal_images/Gyros.png",
        "description": "Greek meat wrap with lamb or chicken, vegetables, and tzatziki.",
        "category": "Greek",
        "meatKind": "Lamb",
        "taste": "Savory",
        "spicy": False,
        "emotion": "Exciting"
    },
    {
        "name": "Couscous",
        "img": "static/meal_images/Couscous.png",
        "description": "North African steamed semolina grains served with vegetables or meat.",
        "category": "North African",
        "meatKind": "Varies",
        "taste": "Savory",
        "spicy": False,
        "emotion": "Nostalgic"
    },
    {
        "name": "Shrimp Tempura",
        "img": "static/meal_images/Shrimp_Tempura.png",
        "description": "Lightly battered and fried shrimp served with dipping sauce.",
        "category": "Japanese",
        "meatKind": "Shrimp",
        "taste": "Savory",
        "spicy": False,
        "emotion": "Luxurious"
    },
    {
        "name": "Dolma",
        "img": "static/meal_images/Dolma.png",
        "description": "Grape leaves stuffed with rice and spices, sometimes with meat.",
        "category": "Middle Eastern",
        "meatKind": "Vegetarian",
        "taste": "Savory",
        "spicy": False,
        "emotion": "Nostalgic"
    },
    {
        "name": "Crab Cakes",
        "img": "static/meal_images/Crab_Cakes.png",
        "description": "Pan-fried patties made with lump crab meat and breadcrumbs.",
        "category": "American",
        "meatKind": "Seafood",
        "taste": "Savory",
        "spicy": False,
        "emotion": "Luxurious"
    },
    {
        "name": "Bulgur Pilaf",
        "img": "static/meal_images/Bulgur_Pilaf.png",
        "description": "Turkish bulgur wheat cooked with tomatoes, onions, and spices.",
        "category": "Turkish",
        "meatKind": "Vegetarian",
        "taste": "Savory",
        "spicy": False,
        "emotion": "Nostalgic"
    },
    {
        "name": "Tonkatsu",
        "img": "static/meal_images/Tonkatsu.png",
        "description": "Japanese breaded and deep-fried pork cutlet served with cabbage.",
        "category": "Japanese",
        "meatKind": "Pork",
        "taste": "Savory",
        "spicy": False,
        "emotion": "Comforting"
    },
    {
        "name": "Polenta",
        "img": "static/meal_images/Polenta.png",
        "description": "Italian cornmeal porridge often served with cheese or sauces.",
        "category": "Italian",
        "meatKind": "Vegetarian",
        "taste": "Savory",
        "spicy": False,
        "emotion": "Nostalgic"
    },
    {
        "name": "Eton Mess",
        "img": "static/meal_images/Eton_Mess.png",
        "description": "British dessert made with meringue, cream, and strawberries.",
        "category": "British",
        "meatKind": "Vegetarian",
        "taste": "Sweet",
        "spicy": False,
        "emotion": "Refreshing"
    },
    {
        "name": "Paneer Butter Masala",
        "img": "static/meal_images/Paneer_Butter_Masala.png",
        "description": "Creamy Indian curry made with paneer and a tomato-based sauce.",
        "category": "Indian",
        "meatKind": "Vegetarian",
        "taste": "Savory",
        "spicy": True,
        "emotion": "Exciting"
    },
    {
        "name": "Tuna Poke Bowl",
        "img": "static/meal_images/Tuna_Poke_Bowl.png",
        "description": "Hawaiian dish with raw tuna, rice, and fresh vegetables.",
        "category": "Hawaiian",
        "meatKind": "Fish",
        "taste": "Fresh",
        "spicy": False,
        "emotion": "Refreshing"
    },
    {
        "name": "Crepes",
        "img": "static/meal_images/Crepes.png",
        "description": "Thin French pancakes served with sweet or savory fillings.",
        "category": "French",
        "meatKind": "Vegetarian",
        "taste": "Varies",
        "spicy": False,
        "emotion": "Comforting"
    },
    {
        "name": "Zucchini Fritters",
        "img": "static/meal_images/Zucchini_Fritters.png",
        "description": "Crispy pan-fried patties made with grated zucchini and herbs.",
        "category": "Mediterranean",
        "meatKind": "Vegetarian",
        "taste": "Savory",
        "spicy": False,
        "emotion": "Refreshing"
    },
    {
        "name": "Meatloaf",
        "img": "static/meal_images/Meatloaf.png",
        "description": "American baked ground meat dish, often served with gravy.",
        "category": "American",
        "meatKind": "Beef",
        "taste": "Savory",
        "spicy": False,
        "emotion": "Nostalgic"
    },
    {
        "name": "Lobster Bisque",
        "img": "static/meal_images/Lobster_Bisque.png",
        "description": "Rich and creamy seafood soup made with lobster stock.",
        "category": "French",
        "meatKind": "Seafood",
        "taste": "Savory",
        "spicy": False,
        "emotion": "Luxurious"
    }
]

# Store user session data (in-memory for now, can use DB later)
user_sessions = {}

class SwipeData(BaseModel):
    user_id: str
    meal_name: str
    liked: bool

@app.post("/swipe")
def swipe_meal(data: SwipeData):
    """Store user swipe and update preferences."""
    user_id = data.user_id
    if user_id not in user_sessions:
        user_sessions[user_id] = {"liked": [], "disliked": [], "preferences": {"category": Counter(), "meatKind": Counter(), "taste": Counter(), "emotion": Counter()}}
    
    session = user_sessions[user_id]
    meal = next((m for m in meals if m["name"] == data.meal_name), None)
    
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")
    
    if data.liked:
        session["liked"].append(meal)
        session["preferences"]["category"][meal["category"]] += 1
        session["preferences"]["meatKind"][meal["meatKind"]] += 1
        session["preferences"]["taste"][meal["taste"]] += 1
        session["preferences"]["emotion"][meal["emotion"]] += 1
    else:
        session["disliked"].append(meal)
    
    return {"message": "Swipe recorded"}

@app.get("/recommend/{user_id}")
def recommend_meal(user_id: str):
    """Recommend a meal after 20 swipes."""
    if user_id not in user_sessions or len(user_sessions[user_id]["liked"]) + len(user_sessions[user_id]["disliked"]) < 20:
        raise HTTPException(status_code=400, detail="Not enough swipes yet")
    
    session = user_sessions[user_id]
    scores = []
    
    for meal in meals:
        if meal in session["liked"] or meal in session["disliked"]:
            continue
        
        score = (
            session["preferences"]["category"][meal["category"]] * 3 +
            session["preferences"]["meatKind"][meal["meatKind"]] * 2 +
            session["preferences"]["taste"][meal["taste"]] * 4 +
            session["preferences"]["emotion"][meal["emotion"]] * 5
        )
        scores.append((meal, score))
    
    scores.sort(key=lambda x: x[1], reverse=True)
    best_meal = scores[0][0] if scores else None
    
    if best_meal:
        return {"recommended_meal": best_meal}
    else:
        raise HTTPException(status_code=404, detail="No suitable recommendation found")

@app.get("/next_meal/{user_id}")
def get_next_meal(user_id: str):
    """Fetch a random meal for the user to swipe on."""
    if user_id not in user_sessions:
        user_sessions[user_id] = {"liked": [], "disliked": [], "preferences": {"category": Counter(), "meatKind": Counter(), "taste": Counter(), "emotion": Counter()}}
    
    viewed_meals = set(m["name"] for m in user_sessions[user_id]["liked"] + user_sessions[user_id]["disliked"])
    remaining_meals = [m for m in meals if m["name"] not in viewed_meals]
    
    if not remaining_meals:
        raise HTTPException(status_code=404, detail="No more meals to swipe")
    
    return random.choice(remaining_meals)
