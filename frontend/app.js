if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/static/sw.js"));
}

const form = document.querySelector("#auth-form");
const nameInput = document.querySelector("#name");
const emailInput = document.querySelector("#email");
const passwordInput = document.querySelector("#password");
const title = document.querySelector("#auth-title");
const message = document.querySelector("#auth-message");
const toggle = document.querySelector("#toggle-auth");
const account = document.querySelector("#account");
const installButton = document.querySelector("#install-app");
const sectionMenu = document.querySelector("#section-menu");

let signupMode = true;
let deferredInstallPrompt;

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  deferredInstallPrompt = event;
  installButton.hidden = false;
});

installButton.addEventListener("click", async () => {
  if (!deferredInstallPrompt) return;
  deferredInstallPrompt.prompt();
  await deferredInstallPrompt.userChoice;
  deferredInstallPrompt = null;
  installButton.hidden = true;
});

sectionMenu.addEventListener("change", () => {
  document.querySelector(sectionMenu.value)?.scrollIntoView({behavior: "smooth"});
});

function setMessage(text, isError = false) {
  message.textContent = text;
  message.classList.toggle("error", isError);
}

function setSignupMode(value) {
  signupMode = value;
  title.textContent = signupMode ? "Rejoindre BC Connect" : "Se connecter";
  nameInput.closest("label").hidden = !signupMode;
  nameInput.required = signupMode;
  passwordInput.autocomplete = signupMode ? "new-password" : "current-password";
  form.querySelector("button[type=submit]").textContent = signupMode
    ? "Créer mon compte"
    : "Se connecter";
  toggle.textContent = signupMode ? "J'ai déjà un compte" : "Créer un compte";
  setMessage(signupMode ? "Crée ton compte étudiant pour commencer." : "Retrouve ta communauté.");
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "Une erreur est survenue.");
  return payload;
}

function showAccount(user) {
  form.hidden = true;
  toggle.hidden = true;
  account.hidden = false;
  account.innerHTML = `
    <p>Bienvenue, <strong>${escapeHtml(user.name)}</strong>.</p>
    <p class="muted">${escapeHtml(user.email)}</p>
    <button id="logout" class="button secondary" type="button">Se déconnecter</button>
  `;
  account.querySelector("#logout").addEventListener("click", logout);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  }[character]));
}

async function loadSession() {
  const token = localStorage.getItem("bc_connect_token");
  if (!token) return;
  try {
    const user = await request("/api/me", {headers: {Authorization: `Bearer ${token}`}});
    showAccount(user);
  } catch {
    localStorage.removeItem("bc_connect_token");
  }
}

async function submitAuth(event) {
  event.preventDefault();
  const submitButton = form.querySelector("button[type=submit]");
  submitButton.disabled = true;
  try {
    const payload = {
      email: emailInput.value,
      password: passwordInput.value,
    };
    if (signupMode) payload.name = nameInput.value;
    const result = await request(signupMode ? "/api/register" : "/api/login", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    localStorage.setItem("bc_connect_token", result.token);
    const user = await request("/api/me", {
      headers: {Authorization: `Bearer ${result.token}`},
    });
    showAccount(user);
    setMessage("Connexion réussie.");
  } catch (error) {
    setMessage(error.message, true);
  } finally {
    submitButton.disabled = false;
  }
}

async function logout() {
  const token = localStorage.getItem("bc_connect_token");
  if (token) {
    await request("/api/logout", {method: "POST", headers: {Authorization: `Bearer ${token}`}});
  }
  localStorage.removeItem("bc_connect_token");
  form.hidden = false;
  toggle.hidden = false;
  account.hidden = true;
  form.reset();
  setSignupMode(true);
}

toggle.addEventListener("click", () => setSignupMode(!signupMode));
form.addEventListener("submit", submitAuth);
setSignupMode(true);
loadSession();
