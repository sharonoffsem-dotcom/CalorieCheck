const state = {
  user: null,
  foods: [],
  goals: { calories: 2200, protein: 160, fat: 70, carbs: 220 },
  selectedDate: today(),
  entries: [],
  analytics: [],
  editingFoodId: null,
  loading: false,
};

const refs = {
  currentUser: document.querySelector("#current-user"),
  logoutButton: document.querySelector("#logout-button"),
  heroDate: document.querySelector("#hero-date"),
  heroEntryCount: document.querySelector("#hero-entry-count"),
  heroFoodCount: document.querySelector("#hero-food-count"),
  selectedDate: document.querySelector("#selected-date"),
  mealForm: document.querySelector("#meal-form"),
  mealSearch: document.querySelector("#meal-search"),
  mealGrams: document.querySelector("#meal-grams"),
  foodOptions: document.querySelector("#food-options"),
  foodForm: document.querySelector("#food-form"),
  foodName: document.querySelector("#food-name"),
  foodManufacturer: document.querySelector("#food-manufacturer"),
  foodCalories: document.querySelector("#food-calories"),
  foodProtein: document.querySelector("#food-protein"),
  foodFat: document.querySelector("#food-fat"),
  foodCarbs: document.querySelector("#food-carbs"),
  foodSubmitButton: document.querySelector("#food-submit-button"),
  foodCancelEdit: document.querySelector("#food-cancel-edit"),
  foodsCountPill: document.querySelector("#foods-count-pill"),
  foodsEmpty: document.querySelector("#foods-empty"),
  foodsList: document.querySelector("#foods-list"),
  goalsForm: document.querySelector("#goals-form"),
  goalCalories: document.querySelector("#goal-calories"),
  goalProtein: document.querySelector("#goal-protein"),
  goalFat: document.querySelector("#goal-fat"),
  goalCarbs: document.querySelector("#goal-carbs"),
  goalSummary: document.querySelector("#goal-summary"),
  progressGrid: document.querySelector("#progress-grid"),
  dayStatus: document.querySelector("#day-status"),
  entriesEmpty: document.querySelector("#entries-empty"),
  entriesList: document.querySelector("#entries-list"),
  analyticsSummary: document.querySelector("#analytics-summary"),
  analyticsList: document.querySelector("#analytics-list"),
  toast: document.querySelector("#toast"),
};

bootstrap();

async function bootstrap() {
  refs.selectedDate.value = state.selectedDate;
  bindEvents();
  await loadSession();
}

function bindEvents() {
  refs.logoutButton.addEventListener("click", logout);

  refs.selectedDate.addEventListener("change", async (event) => {
    state.selectedDate = event.target.value || today();
    await refreshDashboard();
  });

  refs.foodForm.addEventListener("submit", saveFood);
  refs.foodCancelEdit.addEventListener("click", () => {
    resetFoodForm();
    render();
    showToast("Редактирование отменено.");
  });

  refs.mealForm.addEventListener("submit", saveMealEntry);
  refs.goalsForm.addEventListener("submit", saveGoals);
}

async function loadSession() {
  try {
    const response = await api("/api/auth/me");
    state.user = response.user;
    refs.currentUser.textContent = `${response.user.name} · ${response.user.email}`;
    await refreshDashboard();
  } catch {
    window.location.replace("/login");
  }
}

async function refreshDashboard() {
  if (!state.user) {
    window.location.replace("/login");
    return;
  }

  setLoading(true);

  try {
    const [foods, goals, entries, analytics] = await Promise.all([
      api("/api/foods"),
      api("/api/goals"),
      api(`/api/entries?date=${encodeURIComponent(state.selectedDate)}`),
      api("/api/analytics?days=14"),
    ]);

    state.foods = foods.foods;
    state.goals = goals.goals;
    state.entries = entries.entries;
    state.analytics = analytics.days;
    hydrateGoalsForm();
    render();
  } catch (error) {
    if (error.status === 401) {
      window.location.replace("/login");
      return;
    }
    showToast(error.message || "Не удалось загрузить данные.");
  } finally {
    setLoading(false);
  }
}

async function logout() {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch {
    // Intentionally ignore logout network errors.
  }

  state.user = null;
  state.entries = [];
  window.location.replace("/login");
}

async function saveFood(event) {
  event.preventDefault();
  const isEditing = Boolean(state.editingFoodId);

  const payload = {
    name: refs.foodName.value.trim(),
    manufacturer: refs.foodManufacturer.value.trim(),
    calories: toNumber(refs.foodCalories.value),
    protein: toNumber(refs.foodProtein.value),
    fat: toNumber(refs.foodFat.value),
    carbs: toNumber(refs.foodCarbs.value),
  };

  if (!payload.name || !payload.manufacturer) {
    showToast("Укажите название блюда и изготовителя.");
    return;
  }

  try {
    const url = state.editingFoodId ? `/api/foods/${state.editingFoodId}` : "/api/foods";
    const method = state.editingFoodId ? "PATCH" : "POST";
    await api(url, { method, body: payload });
    resetFoodForm();
    await refreshDashboard();
    showToast(isEditing ? "Блюдо обновлено." : "Блюдо добавлено в общий справочник.");
  } catch (error) {
    showToast(error.message || "Не удалось сохранить блюдо.");
  }
}

async function saveMealEntry(event) {
  event.preventDefault();

  const foodChoice = parseFoodChoice(refs.mealSearch.value);
  const food = state.foods.find((item) => item.id === foodChoice.id);
  const grams = toNumber(refs.mealGrams.value);

  if (!food) {
    showToast("Выберите блюдо из справочника.");
    return;
  }

  if (!grams || grams <= 0) {
    showToast("Введите корректный вес.");
    return;
  }

  try {
    await api("/api/entries", {
      method: "POST",
      body: {
        food_id: food.id,
        date: state.selectedDate,
        grams,
      },
    });
    refs.mealForm.reset();
    await refreshDashboard();
    showToast("Прием пищи добавлен.");
  } catch (error) {
    showToast(error.message || "Не удалось добавить запись.");
  }
}

async function saveGoals(event) {
  event.preventDefault();

  try {
    const response = await api("/api/goals", {
      method: "PUT",
      body: {
        calories: toNumber(refs.goalCalories.value),
        protein: toNumber(refs.goalProtein.value),
        fat: toNumber(refs.goalFat.value),
        carbs: toNumber(refs.goalCarbs.value),
      },
    });
    state.goals = response.goals;
    render();
    showToast("Цели по КБЖУ сохранены.");
  } catch (error) {
    showToast(error.message || "Не удалось сохранить цели.");
  }
}

async function deleteFood(foodId) {
  try {
    await api(`/api/foods/${foodId}`, { method: "DELETE" });
    if (state.editingFoodId === foodId) {
      resetFoodForm();
    }
    await refreshDashboard();
    showToast("Блюдо удалено из справочника.");
  } catch (error) {
    showToast(error.message || "Не удалось удалить блюдо.");
  }
}

async function deleteEntry(entryId) {
  try {
    await api(`/api/entries/${entryId}`, { method: "DELETE" });
    await refreshDashboard();
    showToast("Запись удалена.");
  } catch (error) {
    showToast(error.message || "Не удалось удалить запись.");
  }
}

function startFoodEdit(foodId) {
  const food = state.foods.find((item) => item.id === foodId);
  if (!food) return;

  state.editingFoodId = foodId;
  refs.foodName.value = food.name;
  refs.foodManufacturer.value = food.manufacturer;
  refs.foodCalories.value = food.calories;
  refs.foodProtein.value = food.protein;
  refs.foodFat.value = food.fat;
  refs.foodCarbs.value = food.carbs;
  render();
  refs.foodName.focus();
}

function render() {
  if (!state.user) {
    return;
  }

  refs.heroDate.textContent = formatDate(state.selectedDate, { month: "long", day: "numeric" });
  refs.heroEntryCount.textContent = String(state.entries.length);
  refs.heroFoodCount.textContent = String(state.foods.length);
  refs.selectedDate.value = state.selectedDate;

  refs.foodOptions.innerHTML = state.foods
    .map(
      (food) =>
        `<option value="${escapeHtml(formatFoodOption(food))}" data-food-id="${food.id}"></option>`,
    )
    .join("");

  refs.foodsCountPill.textContent = `${state.foods.length} ${pluralize(state.foods.length, ["блюдо", "блюда", "блюд"])}`;
  refs.foodsEmpty.hidden = state.foods.length > 0;
  refs.foodSubmitButton.textContent = state.editingFoodId ? "Обновить блюдо" : "Сохранить блюдо";
  refs.foodCancelEdit.hidden = !state.editingFoodId;
  refs.foodsList.innerHTML = state.foods
    .map(
      (food) => `
        <article class="food-card">
          <div>
            <p class="food-card__name">${escapeHtml(food.name)}</p>
            <p class="food-card__manufacturer">${escapeHtml(food.manufacturer)}</p>
            <div class="food-card__meta">
              ${macroChip(`${formatNumber(food.calories)} ккал`)}
              ${macroChip(`Б ${formatNumber(food.protein)} г`)}
              ${macroChip(`Ж ${formatNumber(food.fat)} г`)}
              ${macroChip(`У ${formatNumber(food.carbs)} г`)}
            </div>
          </div>
          <div class="food-card__actions">
            <button class="button button--ghost button--small" type="button" data-food-edit="${food.id}">Изменить</button>
            <button class="button button--danger button--small" type="button" data-food-delete="${food.id}">Удалить</button>
          </div>
        </article>
      `,
    )
    .join("");

  const totals = calculateTotals(state.entries);
  const completion = getCompletionStatus(totals, state.goals);

  refs.goalSummary.innerHTML = `
    Ваша дневная цель: <strong>${formatNumber(state.goals.calories)} ккал</strong>,
    белки <strong>${formatNumber(state.goals.protein)} г</strong>,
    жиры <strong>${formatNumber(state.goals.fat)} г</strong>,
    углеводы <strong>${formatNumber(state.goals.carbs)} г</strong>.
  `;

  refs.progressGrid.innerHTML = buildProgressCards(totals, state.goals);
  refs.dayStatus.textContent = completion.label;
  refs.dayStatus.className = `status-badge ${completion.className}`;

  refs.entriesEmpty.hidden = state.entries.length > 0;
  refs.entriesList.innerHTML = state.entries
    .map(
      (entry) => `
        <article class="entry-card">
          <div>
            <p class="entry-card__title">${escapeHtml(entry.food_name)} · ${formatNumber(entry.grams)} г</p>
            <p class="food-card__manufacturer">${escapeHtml(entry.manufacturer)}</p>
            <div class="entry-card__meta">
              ${macroChip(`${formatNumber(entry.calories)} ккал`)}
              ${macroChip(`Б ${formatNumber(entry.protein)} г`)}
              ${macroChip(`Ж ${formatNumber(entry.fat)} г`)}
              ${macroChip(`У ${formatNumber(entry.carbs)} г`)}
            </div>
          </div>
          <div class="entry-card__actions">
            <button class="button button--danger button--small" type="button" data-entry-delete="${entry.id}">Удалить</button>
          </div>
        </article>
      `,
    )
    .join("");

  refs.analyticsSummary.innerHTML = buildAnalyticsSummary(state.analytics);
  refs.analyticsList.innerHTML = state.analytics
    .map(
      (item) => `
        <article class="analytics-card">
          <div>
            <p class="analytics-card__title">${formatDate(item.date, { day: "numeric", month: "long", weekday: "short" })}</p>
            <div class="status-badge ${item.status.className}">${item.status.label}</div>
          </div>
          <div class="analytics-card__metrics">
            ${analyticsMetric("Ккал", `${formatNumber(item.totals.calories)} / ${formatNumber(state.goals.calories)}`)}
            ${analyticsMetric("Белки", `${formatNumber(item.totals.protein)} / ${formatNumber(state.goals.protein)} г`)}
            ${analyticsMetric("Жиры", `${formatNumber(item.totals.fat)} / ${formatNumber(state.goals.fat)} г`)}
            ${analyticsMetric("Углеводы", `${formatNumber(item.totals.carbs)} / ${formatNumber(state.goals.carbs)} г`)}
          </div>
        </article>
      `,
    )
    .join("");

  refs.foodsList.querySelectorAll("[data-food-edit]").forEach((button) => {
    button.addEventListener("click", () => startFoodEdit(button.dataset.foodEdit));
  });
  refs.foodsList.querySelectorAll("[data-food-delete]").forEach((button) => {
    button.addEventListener("click", () => deleteFood(button.dataset.foodDelete));
  });
  refs.entriesList.querySelectorAll("[data-entry-delete]").forEach((button) => {
    button.addEventListener("click", () => deleteEntry(button.dataset.entryDelete));
  });
}

function hydrateGoalsForm() {
  refs.goalCalories.value = state.goals.calories;
  refs.goalProtein.value = state.goals.protein;
  refs.goalFat.value = state.goals.fat;
  refs.goalCarbs.value = state.goals.carbs;
}

function resetFoodForm() {
  state.editingFoodId = null;
  refs.foodForm.reset();
}

function calculateTotals(entries) {
  return entries.reduce(
    (acc, item) => ({
      calories: acc.calories + item.calories,
      protein: acc.protein + item.protein,
      fat: acc.fat + item.fat,
      carbs: acc.carbs + item.carbs,
    }),
    { calories: 0, protein: 0, fat: 0, carbs: 0 },
  );
}

function buildProgressCards(totals, goals) {
  const metrics = [
    { key: "calories", label: "Калории", unit: "ккал" },
    { key: "protein", label: "Белки", unit: "г" },
    { key: "fat", label: "Жиры", unit: "г" },
    { key: "carbs", label: "Углеводы", unit: "г" },
  ];

  return metrics
    .map((metric) => {
      const current = totals[metric.key];
      const goal = goals[metric.key];
      const ratio = goal > 0 ? Math.min((current / goal) * 100, 100) : 0;
      const delta = current - goal;
      const note =
        Math.abs(delta) < 0.05
          ? "Цель выполнена точно"
          : delta < 0
            ? `Осталось ${formatNumber(Math.abs(delta))} ${metric.unit}`
            : `Превышение на ${formatNumber(delta)} ${metric.unit}`;

      return `
        <article class="progress-card">
          <div class="progress-card__top">
            <strong>${metric.label}</strong>
            <span>${formatNumber(current)} / ${formatNumber(goal)} ${metric.unit}</span>
          </div>
          <div class="progress-bar"><span style="width:${ratio}%"></span></div>
          <div class="progress-note">${note}</div>
        </article>
      `;
    })
    .join("");
}

function buildAnalyticsSummary(days) {
  const successCount = days.filter((day) => day.status.kind === "good").length;
  const partialCount = days.filter((day) => day.status.kind === "warn").length;
  const missCount = days.filter((day) => day.status.kind === "bad").length;
  const averageCalories =
    days.reduce((sum, day) => sum + day.totals.calories, 0) / Math.max(days.length, 1);

  return `
    За последние 14 дней: <strong>${successCount}</strong> ${pluralize(successCount, ["день", "дня", "дней"])}
    с попаданием в норму, <strong>${partialCount}</strong> ${pluralize(partialCount, ["день", "дня", "дней"])}
    близко к цели и <strong>${missCount}</strong> ${pluralize(missCount, ["день", "дня", "дней"])}
    с заметным отклонением. Среднее потребление: <strong>${formatNumber(averageCalories)} ккал</strong> в день.
  `;
}

function getCompletionStatus(totals, goals) {
  const ratios = Object.keys(goals).map((key) => (goals[key] > 0 ? totals[key] / goals[key] : 0));

  if (ratios.every((ratio) => ratio >= 0.9 && ratio <= 1.1)) {
    return { kind: "good", label: "Норма выполнена", className: "status-good" };
  }

  if (ratios.every((ratio) => ratio >= 0.75 && ratio <= 1.25)) {
    return { kind: "warn", label: "Близко к цели", className: "status-warn" };
  }

  return { kind: "bad", label: "Норма не выполнена", className: "status-bad" };
}

function parseFoodChoice(value) {
  const match = value.match(/\[#(.+)\]$/);
  return { id: match ? match[1] : null };
}

function formatFoodOption(food) {
  return `${food.name} · ${food.manufacturer} [#${food.id}]`;
}

function macroChip(text) {
  return `<span class="macro-chip">${text}</span>`;
}

function analyticsMetric(label, value) {
  return `<div class="analytics-metric">${label}<strong>${value}</strong></div>`;
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    method: options.method || "GET",
    headers: {
      "Content-Type": "application/json",
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
    credentials: "same-origin",
  });

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : null;

  if (!response.ok) {
    const error = new Error(payload?.error || "Ошибка сервера.");
    error.status = response.status;
    throw error;
  }

  return payload;
}

function setLoading(value) {
  state.loading = value;
  document.body.classList.toggle("is-loading", value);
}

function toNumber(value) {
  return Number.parseFloat(value);
}

function today() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function formatDate(dateString, options) {
  return new Intl.DateTimeFormat("ru-RU", options).format(new Date(`${dateString}T00:00:00`));
}

function formatNumber(value) {
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(value || 0);
}

function pluralize(value, forms) {
  const mod10 = value % 10;
  const mod100 = value % 100;

  if (mod10 === 1 && mod100 !== 11) return forms[0];
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return forms[1];
  return forms[2];
}

function showToast(message) {
  refs.toast.textContent = message;
  refs.toast.classList.add("is-visible");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => {
    refs.toast.classList.remove("is-visible");
  }, 2200);
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
