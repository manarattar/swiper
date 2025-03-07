import React, { useState, useEffect } from "react";
import SwipeCard from "./components/SwipeCard";
import Recommendation from "./components/Recommendation";
import axios from "axios";

const API_BASE_URL = "https://swiper-w69e.onrender.com";
const userId = "user_123"; // Placeholder, replace with actual user ID logic

export default function App() {
  const [meal, setMeal] = useState(null);
  const [swipes, setSwipes] = useState(0);
  const [recommendedMeal, setRecommendedMeal] = useState(null);

  useEffect(() => {
    fetchNextMeal();
  }, []);

  const fetchNextMeal = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/next_meal/${userId}`);
      setMeal(response.data);
    } catch (error) {
      console.error("Error fetching meal", error);
    }
  };

  const handleSwipe = async (liked) => {
    if (!meal) return;
    
    try {
      await axios.post(`${API_BASE_URL}/swipe`, {
        user_id: userId,
        meal_name: meal.name,
        liked: liked,
      });
      
      setSwipes(swipes + 1);
      if (swipes + 1 >= 20) {
        fetchRecommendation();
      } else {
        fetchNextMeal();
      }
    } catch (error) {
      console.error("Error swiping meal", error);
    }
  };

  const fetchRecommendation = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/recommend/${userId}`);
      setRecommendedMeal(response.data.recommended_meal);
    } catch (error) {
      console.error("Error fetching recommendation", error);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center h-screen p-4">
      {recommendedMeal ? (
        <Recommendation meal={recommendedMeal} />
      ) : (
        <SwipeCard meal={meal} onSwipe={handleSwipe} />
      )}
    </div>
  );
}