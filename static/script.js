const mainContainer = document.getElementById("main-container");
const card = document.getElementById("card");
const swipeChoice = document.getElementById("swipe-choice");

const mealImg = document.getElementById("meal-img");
const mealName = document.getElementById("meal-name");
const mealDescription = document.getElementById("meal-description");
const mealEmotion = document.getElementById("meal-emotion");
const progressLabel = document.getElementById("progress-label");
const progressRemaining = document.getElementById("progress-remaining");
const progressBar = document.getElementById("progress-bar");

const likeButton = document.getElementById("like-button");
const dislikeButton = document.getElementById("dislike-button");
const goBackButton = document.getElementById("go-back-button");

let isSwiping = false;
let isDragging = false;
let dragStartX = 0;
let dragOffsetX = 0;

window.onload = () => {
  fetchCurrentMeal();
};

function updateProgress(progress) {
  if (!progress) return;
  const shownCurrent = Math.min(progress.current + 1, progress.total);
  progressLabel.textContent = `Meal ${shownCurrent} of ${progress.total}`;
  progressRemaining.textContent = `${progress.remaining} left`;
  progressBar.style.width = `${progress.percent}%`;
}

function fetchCurrentMeal() {
  fetch("/get_current_meal")
    .then(response => response.json())
    .then(data => {
      const { meal, isMealOfTheDay, progress } = data;
      updateProgress(progress);
      if (!meal) return;
      if (isMealOfTheDay) {
        window.location.href = "/meal-of-the-day";
        return;
      }
      displayMeal(meal, progress);
    })
    .catch(err => console.error("Error fetching current meal:", err));
}

function displayMeal(meal, progress) {
  updateProgress(progress);
  mainContainer.classList.remove("hidden");
  mainContainer.classList.add("invisible");

  const preloadImg = new Image();
  preloadImg.onload = function() {
    mealImg.src = meal.img;
    mealName.textContent = meal.name;
    mealDescription.textContent = meal.description;
    mealEmotion.textContent = meal.emotion ? `Emotion: ${meal.emotion} ${meal.emoji}` : "";
    resetCardPosition();
    void mainContainer.offsetWidth;
    mainContainer.classList.remove("invisible");
  };

  preloadImg.onerror = function() {
    mealName.textContent = meal.name;
    mealDescription.textContent = meal.description;
    mealEmotion.textContent = meal.emotion ? `Emotion: ${meal.emotion} ${meal.emoji}` : "";
    resetCardPosition();
    mainContainer.classList.remove("invisible");
  };

  preloadImg.src = meal.img;
}

function handleSwipe(direction) {
  if (isSwiping) return;
  isSwiping = true;
  card.classList.add(direction === "right" ? "swipe-right" : "swipe-left");

  setTimeout(() => {
    const liked = direction === "right";
    fetch("/handle_swipe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ liked })
    })
      .then(response => response.json())
      .then(data => {
        const { meal, isMealOfTheDay, progress } = data;
        updateProgress(progress);
        if (!meal) return;
        if (isMealOfTheDay) {
          window.location.href = "/meal-of-the-day";
          return;
        }
        displayMeal(meal, progress);
      })
      .catch(err => console.error("Error handling swipe:", err))
      .finally(() => {
        isSwiping = false;
      });
  }, 350);
}

function resetCardPosition() {
  dragOffsetX = 0;
  card.classList.remove("swipe-left", "swipe-right", "dragging");
  card.style.transform = "";
  card.style.opacity = "";
  swipeChoice.textContent = "";
  swipeChoice.className = "swipe-choice";
}

function updateDragState(offsetX) {
  const rotation = Math.max(Math.min(offsetX / 18, 12), -12);
  const opacity = Math.max(1 - Math.abs(offsetX) / 520, 0.45);
  card.style.transform = `translateX(${offsetX}px) rotate(${rotation}deg)`;
  card.style.opacity = opacity;

  if (Math.abs(offsetX) < 35) {
    swipeChoice.textContent = "";
    swipeChoice.className = "swipe-choice";
    return;
  }

  const liking = offsetX > 0;
  swipeChoice.textContent = liking ? "Like" : "Skip";
  swipeChoice.className = `swipe-choice ${liking ? "choice-like" : "choice-skip"}`;
}

document.addEventListener("keydown", e => {
  if (e.key === "ArrowRight") {
    handleSwipe("right");
  } else if (e.key === "ArrowLeft") {
    handleSwipe("left");
  }
});

card.addEventListener("pointerdown", e => {
  if (isSwiping) return;
  isDragging = true;
  dragStartX = e.clientX;
  card.classList.add("dragging");
  card.setPointerCapture(e.pointerId);
});

card.addEventListener("pointermove", e => {
  if (!isDragging) return;
  dragOffsetX = e.clientX - dragStartX;
  updateDragState(dragOffsetX);
});

card.addEventListener("pointerup", e => {
  if (!isDragging) return;
  isDragging = false;
  card.releasePointerCapture(e.pointerId);
  card.classList.remove("dragging");

  if (dragOffsetX > 110) {
    handleSwipe("right");
  } else if (dragOffsetX < -110) {
    handleSwipe("left");
  } else {
    resetCardPosition();
  }
});

card.addEventListener("pointercancel", () => {
  isDragging = false;
  resetCardPosition();
});

likeButton.addEventListener("click", () => handleSwipe("right"));
dislikeButton.addEventListener("click", () => handleSwipe("left"));
goBackButton.addEventListener("click", handleGoBack);

function handleGoBack() {
  if (isSwiping) return;
  fetch("/go_back", { method: "POST" })
    .then(res => res.json())
    .then(data => {
      const { meal, isMealOfTheDay, progress } = data;
      updateProgress(progress);
      if (!meal) return;
      if (isMealOfTheDay) {
        window.location.href = "/meal-of-the-day";
        return;
      }
      displayMeal(meal, progress);
    })
    .catch(err => console.error("Error going back:", err));
}
