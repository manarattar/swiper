// file: static/script.js

// DOM references in index.html
const mainContainer = document.getElementById("main-container");
const card = document.getElementById("card");

const mealImg = document.getElementById("meal-img");
const mealName = document.getElementById("meal-name");
const mealDescription = document.getElementById("meal-description");
const mealEmotion = document.getElementById("meal-emotion");

const likeButton = document.getElementById("like-button");
const dislikeButton = document.getElementById("dislike-button");
const goBackButton = document.getElementById("go-back-button");

// Called when the swiping page (index.html) loads
window.onload = () => {
  console.log("Swiping page loaded. Requesting current meal...");
  fetchCurrentMeal();
};

/**
 * Fetch the current meal from the backend.
 * If it's the final recommendation, redirect to the Meal of the Day page.
 */
function fetchCurrentMeal() {
  fetch("/get_current_meal")
    .then(response => response.json())
    .then(data => {
      const { meal, isMealOfTheDay } = data;
      if (!meal) {
        console.warn("No meal returned from server.");
        return;
      }
      if (isMealOfTheDay) {
        console.log("Best match reached; redirecting to Meal of the Day.");
        window.location.href = "/meal-of-the-day";
      } else {
        displayMeal(meal);
      }
    })
    .catch(err => console.error("Error fetching current meal:", err));
}

/**
 * Update the UI to show the meal in the main container with a full fade-in.
 */
function displayMeal(meal) {
  console.log("Displaying meal:", meal.name);
  
  // Remove 'hidden' so that the container is in the layout,
  // then add 'invisible' to set its opacity to 0 for a smooth fade-in.
  mainContainer.classList.remove("hidden");
  mainContainer.classList.add("invisible");
  
  // Preload the new image
  const preloadImg = new Image();
  
  preloadImg.onload = function() {
    // Once the image is fully loaded, update the DOM:
    mealImg.src = meal.img;
    mealName.textContent = meal.name;
    mealDescription.textContent = meal.description;
    
    if (mealEmotion) {
      mealEmotion.textContent = meal.emotion ? `Emotion: ${meal.emotion} ${meal.emoji}` : "";
    }
    
    // Remove any swipe animation classes from the card
    card.classList.remove("swipe-left", "swipe-right");
    
    // Force reflow (optional, ensures browser applies the style changes)
    void mainContainer.offsetWidth;
    
    // Now remove the 'invisible' class to trigger the fade-in transition
    mainContainer.classList.remove("invisible");
  };
  
  preloadImg.onerror = function() {
    console.error("Error preloading image:", meal.img);
    // If image fails, update text fields anyway and reveal container.
    mealName.textContent = meal.name;
    mealDescription.textContent = meal.description;
    if (mealEmotion) {
      mealEmotion.textContent = meal.emotion ? `Emotion: ${meal.emotion} ${meal.emoji}` : "";
    }
    card.classList.remove("swipe-left", "swipe-right");
    mainContainer.classList.remove("invisible");
  };
  
  // Start preloading the image
  preloadImg.src = meal.img;
}

/**
 * Handle a swipe action: "left" (dislike) or "right" (like).
 */
function handleSwipe(direction) {
  console.log("Swiped:", direction);
  
  // Animate the card with a swipe effect
  card.classList.add(direction === "right" ? "swipe-right" : "swipe-left");
  
  // After a delay for the animation, post the swipe result to the backend
  setTimeout(() => {
    const liked = (direction === "right");
    fetch("/handle_swipe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ liked })
    })
      .then(response => response.json())
      .then(data => {
        const { meal, isMealOfTheDay } = data;
        if (!meal) {
          console.warn("No meal returned after swipe.");
          return;
        }
        if (isMealOfTheDay) {
          console.log("Best match reached; redirecting to Meal of the Day.");
          window.location.href = "/meal-of-the-day";
        } else {
          displayMeal(meal);
        }
      })
      .catch(err => console.error("Error handling swipe:", err));
  }, 500); // Delay to allow swipe animation to finish
}

// Keyboard arrow events
document.addEventListener("keydown", e => {
  if (e.key === "ArrowRight") {
    handleSwipe("right");
  } else if (e.key === "ArrowLeft") {
    handleSwipe("left");
  }
});

// Touch events for mobile swiping
let touchstartX = 0;
let touchendX = 0;

document.addEventListener("touchstart", e => {
  touchstartX = e.changedTouches[0].screenX;
});
document.addEventListener("touchend", e => {
  touchendX = e.changedTouches[0].screenX;
  handleGesture();
});

function handleGesture() {
  if (touchendX < touchstartX - 50) {
    handleSwipe("left");
  } else if (touchendX > touchstartX + 50) {
    handleSwipe("right");
  }
}

// Button click events
likeButton.addEventListener("click", () => handleSwipe("right"));
dislikeButton.addEventListener("click", () => handleSwipe("left"));
goBackButton.addEventListener("click", handleGoBack);

function handleGoBack() {
  // POST to /go_back to revert the last swipe
  fetch("/go_back", { method: "POST" })
    .then(res => res.json())
    .then(data => {
      const { meal, isMealOfTheDay } = data;
      if (!meal) {
        console.log("No previous meal to revert to.");
        return;
      }
      if (isMealOfTheDay) {
        window.location.href = "/meal-of-the-day";
      } else {
        displayMeal(meal);
      }
    })
    .catch(err => console.error("Error going back:", err));
}
