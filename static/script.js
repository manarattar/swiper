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
const state = document.getElementById("swipe-state");
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
try { const items = JSON.parse(localStorage.getItem("swipeeatCart") || "[]"); document.getElementById("swipe-cart").textContent = `Cart (${items.reduce((sum, item) => sum + Number(item.quantity || 0), 0)})`; } catch (error) {}
function showState(message, retry = false) { state.replaceChildren(document.createTextNode(message)); state.classList.remove("hidden"); card.classList.add("hidden"); if (retry) { const button = document.createElement("button"); button.type = "button"; button.className = "button"; button.textContent = "Retry"; button.onclick = fetchCurrentMeal; state.append(button); } }
function showCard() { state.classList.add("hidden"); card.classList.remove("hidden"); }

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
  showState("Loading dishes...");
  fetch("/get_current_meal")
    .then(response => { if (!response.ok) throw Error("Could not load dishes"); return response.json(); })
    .then(data => {
      const { meal, isMealOfTheDay, progress } = data;
      updateProgress(progress);
      if (!meal) { showState("No dishes available right now. Browse the menu to choose a meal."); return; }
      if (isMealOfTheDay) {
        window.location.href = "/meal-of-the-day" + window.location.search;
        return;
      }
      displayMeal(meal, progress);
    })
    .catch(() => showState("Dishes could not be loaded. Please try again.", true));
}

function displayMeal(meal, progress) {
  updateProgress(progress);
  showCard();
  mealName.textContent = meal.name;
  mealDescription.textContent = meal.description;
  mealImg.alt = meal.name;
  mealEmotion.textContent = "";

  const preloadImg = new Image();
  preloadImg.onload = function() {
    mealImg.src = meal.img;
    mealName.textContent = meal.name;
    mealDescription.textContent = meal.description;
    mealEmotion.textContent = "";
    resetCardPosition();
    void mainContainer.offsetWidth;
    mainContainer.classList.remove("invisible");
  };

  preloadImg.onerror = function() {
    mealName.textContent = meal.name;
    mealDescription.textContent = meal.description;
    mealImg.src = "/static/wordmark.svg";
    mealEmotion.textContent = "Image unavailable";
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
      .catch(() => { resetCardPosition(); showState("Could not save that choice. Please retry.", true); })
      .finally(() => {
        isSwiping = false;
      });
  }, reducedMotion.matches ? 0 : 180);
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

mainContainer.addEventListener("keydown", e => {
  if (e.target.closest("button,a,input,textarea,select")) return;
  if (e.key === "ArrowRight") {
    handleSwipe("right");
  } else if (e.key === "ArrowLeft") {
    handleSwipe("left");
  }
});

card.addEventListener("pointerdown", e => {
  if (isSwiping || e.target.closest("button,a,input,textarea,select")) return;
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
    .catch(() => showState("Could not undo the last choice. Please retry.", true));
}
