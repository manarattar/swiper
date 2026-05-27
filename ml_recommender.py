import csv
import json
import math
import os
import re
from collections import Counter, defaultdict


MODEL_VERSION = "tfidf-food-v1"
DEFAULT_MODEL_PATH = os.environ.get("FOOD_ML_MODEL_PATH", "ml_food_model.json")
TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_+-]*")


def tokenize(text):
    return [token.lower() for token in TOKEN_RE.findall(str(text or ""))]


def meal_document(meal):
    fields = [
        meal.get("name", ""),
        meal.get("description", ""),
        meal.get("category", ""),
        meal.get("meatKind", ""),
        meal.get("taste", ""),
        meal.get("emotion", ""),
        "spicy" if meal.get("spicy") else "not spicy",
        " ".join(meal.get("allergens", []) or []),
        " ".join(meal.get("ingredients", []) or []),
        " ".join(meal.get("tags", []) or []),
    ]
    return " ".join(str(field) for field in fields if field)


def recipe_document(row):
    fields = []
    for key in (
        "name",
        "title",
        "description",
        "ingredients",
        "ingredient",
        "tags",
        "nutrition",
        "markdown",
        "category",
        "cuisine",
    ):
        value = row.get(key)
        if value:
            fields.append(value)
    return " ".join(fields)


def build_model(documents, max_features=4000, min_df=1):
    doc_tokens = []
    document_frequency = Counter()
    for document in documents:
        tokens = tokenize(document)
        if not tokens:
            continue
        doc_tokens.append(tokens)
        document_frequency.update(set(tokens))

    total_docs = len(doc_tokens)
    if not total_docs:
        return {"version": MODEL_VERSION, "totalDocs": 0, "idf": {}, "maxFeatures": max_features}

    candidates = [
        (token, freq)
        for token, freq in document_frequency.items()
        if freq >= min_df and len(token) > 1
    ]
    candidates.sort(key=lambda item: (-item[1], item[0]))
    vocabulary = {token for token, _ in candidates[:max_features]}

    idf = {
        token: math.log((1 + total_docs) / (1 + document_frequency[token])) + 1
        for token in vocabulary
    }
    return {
        "version": MODEL_VERSION,
        "totalDocs": total_docs,
        "idf": idf,
        "maxFeatures": max_features,
        "minDf": min_df,
    }


def vectorize(document, model):
    idf = model.get("idf", {})
    if not idf:
        return {}
    counts = Counter(token for token in tokenize(document) if token in idf)
    if not counts:
        return {}
    max_count = max(counts.values())
    vector = {}
    for token, count in counts.items():
        tf = 0.5 + (0.5 * count / max_count)
        vector[token] = tf * idf[token]
    norm = math.sqrt(sum(value * value for value in vector.values()))
    if not norm:
        return {}
    return {token: value / norm for token, value in vector.items()}


def cosine_similarity(left, right):
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(token, 0.0) for token, value in left.items())


def load_model(path=DEFAULT_MODEL_PATH):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        model = json.load(handle)
    if model.get("version") != MODEL_VERSION:
        return None
    return model


def save_model(model, path=DEFAULT_MODEL_PATH):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(model, handle, indent=2, sort_keys=True)


def train_from_recipe_csv(path, max_rows=None, max_features=4000, min_df=2):
    documents = []
    with open(path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader):
            if max_rows is not None and index >= max_rows:
                break
            document = recipe_document(row)
            if document.strip():
                documents.append(document)
    return build_model(documents, max_features=max_features, min_df=min_df)


def train_from_meals(meals, max_features=1000):
    return build_model([meal_document(meal) for meal in meals], max_features=max_features, min_df=1)


def taste_profile_vector(meals, swipe_history, model):
    liked_vectors = []
    disliked_vectors = []
    for swipe in swipe_history:
        index = swipe.get("mealIndex")
        if index is None or index < 0 or index >= len(meals):
            continue
        vector = vectorize(meal_document(meals[index]), model)
        if swipe.get("liked"):
            liked_vectors.append(vector)
        else:
            disliked_vectors.append(vector)

    profile = defaultdict(float)
    for vector in liked_vectors:
        for token, value in vector.items():
            profile[token] += value
    for vector in disliked_vectors:
        for token, value in vector.items():
            profile[token] -= value * 0.8

    norm = math.sqrt(sum(value * value for value in profile.values()))
    if not norm:
        return {}
    return {token: value / norm for token, value in profile.items() if value > 0}


def ml_scores(meals, swipe_history, model):
    profile = taste_profile_vector(meals, swipe_history, model)
    if not profile:
        return {}
    scores = {}
    for meal in meals:
        scores[meal.get("name", "")] = cosine_similarity(profile, vectorize(meal_document(meal), model))
    return scores
