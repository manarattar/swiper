import meals from "./meals_data.js";
let currentMealIndex = 0;
 
let userPreferences = {
     origin: {},
     meatKind: {},
     taste: {},
     spicy: {},
 };
 
 const card = document.getElementById("card");
 const mealImg = document.getElementById("meal-img");
 const mealName = document.getElementById("meal-name");
 const mealDescription = document.getElementById("meal-description");
 
 const mealOfTheDayContainer = document.getElementById("meal-of-the-day");
 const mealOfTheDayImg = document.getElementById("meal-of-the-day-img");
 const mealOfTheDayName = document.getElementById("meal-of-the-day-name");
 const mealOfTheDayDescription = document.getElementById("meal-of-the-day-description");
 
 const popup = document.getElementById("popup");
 const closePopupButton = document.getElementById("close-popup");
 const mainContainer = document.getElementById("main-container");
 
 const likeButton = document.getElementById("like-button");
 const dislikeButton = document.getElementById("dislike-button");
 
 // Updated event listener for closing the popup
 closePopupButton.addEventListener("click", () => {
     console.log("Popup closed");
     popup.style.display = "none";
     mainContainer.style.display = "block";
     updateMeal(); // Ensure the meal is loaded immediately
 });
 
 function updateMeal() {
     if (meals.length === 0) return;
     console.log("Updating meal...");
     if (meals.length === 0) {
         console.error("No meals available to display.");
         return;
     }
     if (currentMealIndex >= meals.length) {
         console.log("Displaying meal of the day...");
         displayMealOfTheDay();
         return;
     }
     const meal = meals[currentMealIndex];
     console.log(`Displaying meal: ${meal.name}`);
     mealImg.src = meal.img;
     mealName.textContent = meal.name;
     mealDescription.textContent = meal.description;
     card.classList.remove("swipe-left", "swipe-right");
     mealOfTheDayContainer.style.display = "none"; // Hide the meal of the day until after all swipes
     card.style.display = "block"; // Ensure the main meal card is displayed
 }
 
 function handleKey(e) {
     if (meals.length === 0 || mealOfTheDayContainer.style.display === "block") return;
     if (e.key === "ArrowRight") {
         handleSwipe("right");
     } else if (e.key === "ArrowLeft") {
         handleSwipe("left");
     }
 }
 
 function handleSwipe(direction) {
     if (meals.length === 0 || mealOfTheDayContainer.style.display === "block") return;
     if (direction === "right") {
         console.log("Swiped right");
         card.classList.add("swipe-right");
         setTimeout(() => {
             updatePreferences(meals[currentMealIndex], true);
         }, 500);
     } else if (direction === "left") {
         console.log("Swiped left");
         card.classList.add("swipe-left");
         setTimeout(() => {
             updatePreferences(meals[currentMealIndex], false);
         }, 500);
     }
 }
 
 function updatePreferences(meal, liked) {
     nextMeal();
     console.log(`Updating preferences for meal: ${meal.name}, liked: ${liked}`);
     const weight = liked ? 1 : -1;
     userPreferences.origin[meal.category] = (userPreferences.origin[meal.category] || 0) + weight * 2;
     userPreferences.meatKind[meal.meatKind] = (userPreferences.meatKind[meal.meatKind] || 0) + weight * 3;
     userPreferences.spicy[meal.spicy ? "Spicy" : "Not Spicy"] = (userPreferences.spicy[meal.spicy ? "Spicy" : "Not Spicy"] || 0) + weight;
     userPreferences.taste[meal.taste] = (userPreferences.taste[meal.taste] || 0) + weight * 2;
 
     
 }
 
 function recommendMeals() {
     console.log("Recommending meals based on user preferences...");
     meals.sort((a, b) => {
         let scoreA = 0;
         let scoreB = 0;
 
         scoreA += (userPreferences.origin[a.category] || 0) * 2;
         scoreA += (userPreferences.meatKind[a.meatKind] || 0) * 3;
         scoreA += (userPreferences.spicy[a.spicy ? "Spicy" : "Not Spicy"] || 0);
         scoreA += (userPreferences.taste[a.taste] || 0) * 2;
 
         scoreB += (userPreferences.origin[b.category] || 0) * 2;
         scoreB += (userPreferences.meatKind[b.meatKind] || 0) * 3;
         scoreB += (userPreferences.spicy[b.spicy ? "Spicy" : "Not Spicy"] || 0);
         scoreB += (userPreferences.taste[b.taste] || 0) * 2;
 
         return scoreB - scoreA;
     });
     console.log("Recommended meals have been updated based on user preferences.");
 }
 
 function nextMeal() {
     currentMealIndex++;
     console.log(`Next meal index: ${currentMealIndex}`);
     if (currentMealIndex < meals.length) {
         updateMeal();
     } else {
         recommendMeals();
         displayMealOfTheDay();
     }
 }
 
 function displayMealOfTheDay() {
     if (meals.length === 0) return;
     console.log("Displaying meal of the day...");
     if (meals.length === 0) {
         console.error("No meals available to display.");
         return;
     }
     const bestMatch = meals[0];
     mealOfTheDayImg.src = bestMatch.img;
     mealOfTheDayName.textContent = bestMatch.name;
     mealOfTheDayDescription.textContent = bestMatch.description;
     mealOfTheDayContainer.style.display = "block";
     mainContainer.style.display = "none"; // Hide the main container when showing the meal of the day
 }
 
 document.addEventListener("keydown", handleKey);
 
 // Add touch event listeners for swipe functionality on mobile
 let touchstartX = 0;
 let touchendX = 0;
 
 function handleGesture() {
     if (touchendX < touchstartX - 50) {
         handleSwipe("left");
     }
     if (touchendX > touchstartX + 50) {
         handleSwipe("right");
     }
 }
 
 document.addEventListener("touchstart", (e) => {
     touchstartX = e.changedTouches[0].screenX;
 });
 
 document.addEventListener("touchend", (e) => {
     touchendX = e.changedTouches[0].screenX;
     handleGesture();
 });
 
 // Add event listeners for Like and Dislike buttons
 likeButton.addEventListener("click", () => handleSwipe("right"));
 dislikeButton.addEventListener("click", () => handleSwipe("left"));
 
 // Show popup when the page loads
 window.onload = () => {
     console.log("Page loaded. Displaying popup...");
     popup.style.display = "flex";
 };