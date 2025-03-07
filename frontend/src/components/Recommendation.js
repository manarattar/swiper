import React from "react";

export default function Recommendation({ meal }) {
  if (!meal) return <p>Loading recommendation...</p>;

  return (
    <div className="text-center p-4">
      <h2 className="text-2xl font-bold">Best Meal for You:</h2>
      <p className="text-lg font-semibold">{meal.name}</p>
      <p className="text-md">{meal.description}</p>
      <p className="text-sm text-gray-500">Emotion: {meal.emotion}</p>
    </div>
  );
}