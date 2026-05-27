import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml_recommender import DEFAULT_MODEL_PATH, save_model, train_from_recipe_csv


def main():
    parser = argparse.ArgumentParser(description="Train SwipeEat's food recommendation TF-IDF model from a recipe CSV.")
    parser.add_argument("csv_path", help="Path to a Food.com/recipe CSV such as RAW_recipes.csv.")
    parser.add_argument("--output", default=DEFAULT_MODEL_PATH, help="Output model JSON path.")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional row limit for quick experiments.")
    parser.add_argument("--max-features", type=int, default=4000, help="Maximum vocabulary size.")
    parser.add_argument("--min-df", type=int, default=2, help="Minimum document frequency for a token.")
    args = parser.parse_args()

    model = train_from_recipe_csv(
        args.csv_path,
        max_rows=args.max_rows,
        max_features=args.max_features,
        min_df=args.min_df,
    )
    save_model(model, args.output)
    print(f"Saved {model['version']} model with {len(model.get('idf', {}))} features from {model.get('totalDocs', 0)} documents to {args.output}")


if __name__ == "__main__":
    main()
