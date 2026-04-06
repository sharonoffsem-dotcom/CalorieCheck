const refs = {
  authForm: document.querySelector("#auth-form"),
  authEmail: document.querySelector("#auth-email"),
  authPassword: document.querySelector("#auth-password"),
  toast: document.querySelector("#toast"),
};

bootstrap();

async function bootstrap() {
  refs.authForm.addEventListener("submit", handleLogin);

  try {
    await api("/api/auth/me");
    window.location.replace("/");
  } catch {
    // User is not authenticated yet.
  }
}

async function handleLogin(event) {
  event.preventDefault();

  try {
    await api("/api/auth/login", {
      method: "POST",
      body: {
        email: refs.authEmail.value.trim(),
        password: refs.authPassword.value,
      },
    });
    window.location.replace("/");
  } catch (error) {
    showToast(error.message || "Ошибка входа.");
  }
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

function showToast(message) {
  refs.toast.textContent = message;
  refs.toast.classList.add("is-visible");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => {
    refs.toast.classList.remove("is-visible");
  }, 2200);
}
