# SwipeEat ML Recommender

SwipeEat now supports a trainable food embedding recommender. The app loads `ml_food_model.json` by default, or the path in `FOOD_ML_MODEL_PATH`. If no trained model exists, it builds a small fallback model from the current menu so local development still works.

## Training Data

The recommended first dataset is Food.com Recipes and User Interactions:

https://www.kaggle.com/datasets/shuyangli94/food-com-recipes-and-user-interactions

Download the dataset and use the recipe CSV, usually named `RAW_recipes.csv`.

## Train

```powershell
python scripts\train_food_model.py path\to\RAW_recipes.csv --output ml_food_model.json --max-features 4000 --min-df 2
```

For a quick local experiment:

```powershell
python scripts\train_food_model.py path\to\RAW_recipes.csv --output ml_food_model.json --max-rows 15000
```

## How It Works

- The training script learns TF-IDF food vocabulary weights from recipe names, descriptions, ingredients, tags, and nutrition fields.
- During swiping, liked meals add to the user's taste vector and disliked meals subtract from it.
- Recommendations combine the existing structured preference score with the ML similarity score.
- Dietary filters, stock, and availability still remain business rules outside the model.

## Next Upgrade

Once SwipeEat has enough local swipe/order data, train a ranking model where:

- Swipe right is a weak positive signal.
- Add to cart is a stronger positive signal.
- Completed order is the strongest positive signal.
- Swipe left is a negative signal.

