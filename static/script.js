// script.js

// DOM references in index.html
const mainContainer = document.getElementById("main-container");
const card = document.getElementById("card");

const mealImg = document.getElementById("meal-img");
const mealName = document.getElementById("meal-name");
const mealDescription = document.getElementById("meal-description");

const likeButton = document.getElementById("like-button");
const dislikeButton = document.getElementById("dislike-button");
const goBackButton = document.getElementById("go-back-button");

const mealEmotion = document.getElementById("meal-emotion");


// Called when the swiping page (index.html) loads
window.onload = () => {
  console.log("Swiping page loaded. Requesting current meal...");
  fetchCurrentMeal();
};

/**
 * Fetch the current meal from the backend. 
 * If it's already the best match, redirect to the Meal of the Day page.
 */
function fetchCurrentMeal() {
  fetch("/get_current_meal")
    .then((response) => response.json())
    .then((data) => {
      const { meal, isMealOfTheDay } = data;

      if (!meal) {
        console.warn("No meal was returned from the server.");
        return;
      }

      if (isMealOfTheDay) {
        // If the backend says we're already at the final match, go to Meal of the Day
        console.log("Best match reached; redirecting to Meal of the Day.");
        window.location.href = "/meal-of-the-day";
      } else {
        // Otherwise, display the current meal
        displayMeal(meal);
      }
    })
    .catch((err) => console.error("Error fetching current meal:", err));
}

/**
 * Update the UI to show the meal in the main container.
 */
function displayMeal(meal) {
    console.log("Displaying meal:", meal.name);
  
    // Fade out current image
    mealImg.style.opacity = 0;
  
    // Preload the new image
    const preloadImg = new Image();
    preloadImg.onload = function() {
      // Once the image is preloaded, update the image src
      mealImg.src = meal.img;
      // Fade it in
      mealImg.style.opacity = 1;
    };
    preloadImg.src = meal.img;
    
    // Update the text fields immediately
    mealName.textContent = meal.name;
    mealDescription.textContent = meal.description;
    
    // If you're displaying emotion info, update that as well:
    const mealEmotion = document.getElementById("meal-emotion");
    if (mealEmotion) {
      mealEmotion.textContent = meal.emotion ? `Emotion: ${meal.emotion} ${meal.emoji}` : "";
    }
    
    // Ensure the main container is visible and reset any swipe animation classes.
    mainContainer.classList.remove("hidden");
    card.classList.remove("swipe-left", "swipe-right");
  }
  
/**
 * Handle a swipe action: "left" (dislike) or "right" (like).
 */
function handleSwipe(direction) {
  console.log(`Swiped: ${direction}`);

  // Animate the card
  card.classList.add(direction === "right" ? "swipe-right" : "swipe-left");

  // After animation, post the swipe to the backend
  setTimeout(() => {
    const liked = (direction === "right");

    fetch("/handle_swipe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ liked })
    })
      .then((response) => response.json())
      .then((data) => {
        const { meal, isMealOfTheDay } = data;

        if (!meal) {
          console.warn("No meal data after swipe.");
          return;
        }

        if (isMealOfTheDay) {
          console.log("Best match found; going to Meal of the Day.");
          window.location.href = "/meal-of-the-day";
        } else {
          displayMeal(meal);
        }
      })
      .catch((err) => console.error("Error handling swipe:", err));
  }, 500); // 0.5s delay to let animation finish
}

// Keyboard arrow events
document.addEventListener("keydown", (e) => {
  if (e.key === "ArrowRight") {
    handleSwipe("right");
  } else if (e.key === "ArrowLeft") {
    handleSwipe("left");
  }
});

// Touch events for mobile swiping
let touchstartX = 0;
let touchendX = 0;

document.addEventListener("touchstart", (e) => {
  touchstartX = e.changedTouches[0].screenX;
});
document.addEventListener("touchend", (e) => {
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

// Buttons
likeButton.addEventListener("click", () => handleSwipe("right"));
dislikeButton.addEventListener("click", () => handleSwipe("left"));

goBackButton.addEventListener("click", handleGoBack);

function handleGoBack() {
  // POST to /go_back
  fetch("/go_back", { method: "POST" })
    .then((res) => res.json())
    .then((data) => {
      const { meal, isMealOfTheDay } = data;
      if (!meal) {
        console.log("No previous meal to revert to.");
        return;
      }
      if (isMealOfTheDay) {
        // Theoretically shouldn't happen if we're going back, but handle it anyway
        window.location.href = "/meal-of-the-day";
      } else {
        displayMeal(meal);
      }
    })
    .catch((err) => console.error("Error going back:", err));
}