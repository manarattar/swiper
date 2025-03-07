import React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function SwipeCard({ meal, onSwipe }) {
  if (!meal) return <p>Loading...</p>;

  return (
    <Card className="w-80 p-4 text-center">
      <img
        src={`/static/meal_images/${meal.name.replace(/ /g, "_")}.png`}
        alt={meal.name}
        className="w-full h-48 object-cover rounded-lg"
      />
      <CardContent>
        <h2 className="text-xl font-bold">{meal.name}</h2>
        <p>{meal.description}</p>
        <p className="text-sm text-gray-500">Emotion: {meal.emotion}</p>
        <div className="flex justify-around mt-4">
          <Button className="bg-red-500" onClick={() => onSwipe(false)}>❌ Dislike</Button>
          <Button className="bg-green-500" onClick={() => onSwipe(true)}>❤️ Like</Button>
        </div>
      </CardContent>
    </Card>
  );
}