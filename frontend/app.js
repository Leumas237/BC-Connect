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
let discoverProfiles = [];

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
    ${user.approved
      ? `
        <form id="profile-form" class="kyi-form">
          <h3>Mon profil étudiant</h3>
          <label>Bio<textarea name="bio" maxlength="1000" rows="4"></textarea></label>
          <label>Cycle
            <select name="cycle">
              <option value="">Choisir un cycle</option>
              <option>DUT</option><option>BTS</option><option>Licence</option><option>Master</option>
            </select>
          </label>
          <label>Filière<input name="filiere" maxlength="160"></label>
          <label>Classe<input name="classe" maxlength="120"></label>
          <label>Centres d’intérêt<input name="interests" placeholder="sport, musique, entrepreneuriat"></label>
          <label>Âge<input name="age" type="number" min="15" max="80"></label>
          <label>Instagram<input name="instagram" maxlength="160" placeholder="https://instagram.com/..."></label>
          <label>Snapchat<input name="snapchat" maxlength="160" placeholder="Ton identifiant ou lien"></label>
          <label>WhatsApp<input name="whatsapp" maxlength="160" placeholder="https://wa.me/..."></label>
          <label>Intention
            <select name="intent">
              <option value="les_deux">Amis et couple</option>
              <option value="amis">Amitié</option>
              <option value="couple">Relation</option>
            </select>
          </label>
          <label class="checkbox"><input name="invisible" type="checkbox"> Masquer mon profil</label>
          <button class="button primary" type="submit">Enregistrer mon profil</button>
        </form>
        <section class="discovery">
          <h3>Découvrir la communauté</h3>
          <div id="discover-list"><p class="muted">Chargement des profils...</p></div>
        </section>
        <section class="matches">
          <h3>Mes matchs</h3>
          <div id="matches-list"><p class="muted">Chargement des matchs...</p></div>
        </section>
      `
      : user.kyi_submitted
      ? `<p class="muted">Dossier étudiant soumis. Il est en attente de validation.</p>`
      : `
        <form id="kyi-form" class="kyi-form">
          <h3>Vérifier mon identité étudiante</h3>
          <p class="muted">Ta carte est stockée hors des fichiers publics et consultable uniquement par un administrateur.</p>
          <label>Nom complet officiel<input name="full_name" required maxlength="160"></label>
          <label>Date de naissance<input name="birthdate" type="date" required></label>
          <label>Classe<input name="classe" required maxlength="120"></label>
          <label>Carte étudiante (5 Mo maximum)<input name="card" type="file" accept="image/jpeg,image/png,image/webp" required></label>
          <button class="button primary" type="submit">Envoyer mon dossier</button>
        </form>
      `}
    <button id="logout" class="button secondary" type="button">Se déconnecter</button>
  `;
  account.querySelector("#logout").addEventListener("click", logout);
  account.querySelector("#kyi-form")?.addEventListener("submit", submitKyi);
  account.querySelector("#profile-form")?.addEventListener("submit", submitProfile);
  if (user.approved) {
    loadProfile();
    loadDiscover();
    loadMatches();
  }
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

  async function submitKyi(event) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const token = localStorage.getItem("bc_connect_token");
    const button = event.currentTarget.querySelector("button");
    button.disabled = true;
    try {
      const response = await fetch("/api/kyi", {
        method: "POST",
        headers: {Authorization: `Bearer ${token}`},
        body: formData,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Impossible d'envoyer le dossier.");
      setMessage("Dossier étudiant envoyé. Il est maintenant en attente de validation.");
      const user = await request("/api/me", {headers: {Authorization: `Bearer ${token}`}});
      showAccount(user);
    } catch (error) {
      setMessage(error.message, true);
      button.disabled = false;
    }

    async function loadProfile() {
      const token = localStorage.getItem("bc_connect_token");
      try {
        const profile = await request("/api/profile", {
          headers: {Authorization: `Bearer ${token}`},
        });
        const profileForm = document.querySelector("#profile-form");
        if (!profileForm) return;
        for (const field of ["bio", "cycle", "filiere", "classe", "intent", "instagram", "snapchat", "whatsapp"]) {
          profileForm.elements[field].value = profile[field] || "";
        }
        profileForm.elements.interests.value = profile.interests.join(", ");
        profileForm.elements.age.value = profile.age || "";
        profileForm.elements.invisible.checked = profile.invisible;
      } catch (error) {
        setMessage(error.message, true);
      }
    }

    async function submitProfile(event) {
      event.preventDefault();
      const profileForm = event.currentTarget;
      const token = localStorage.getItem("bc_connect_token");
      const payload = {
        bio: profileForm.elements.bio.value,
        cycle: profileForm.elements.cycle.value,
        filiere: profileForm.elements.filiere.value,
        classe: profileForm.elements.classe.value,
        interests: profileForm.elements.interests.value.split(",").map((item) => item.trim()).filter(Boolean),
        intent: profileForm.elements.intent.value,
        age: profileForm.elements.age.value ? Number(profileForm.elements.age.value) : null,
        invisible: profileForm.elements.invisible.checked,
        instagram: profileForm.elements.instagram.value,
        snapchat: profileForm.elements.snapchat.value,
        whatsapp: profileForm.elements.whatsapp.value,
      };
      const button = profileForm.querySelector("button");
      button.disabled = true;
      try {
        await request("/api/profile", {
          method: "PUT",
          headers: {Authorization: `Bearer ${token}`},
          body: JSON.stringify(payload),
        });
        setMessage("Profil enregistré.");
      } catch (error) {
        setMessage(error.message, true);
      } finally {
        button.disabled = false;
      }

      function socialLink(label, value) {
        if (!value) return "";
        const url = value.startsWith("http://") || value.startsWith("https://") ? value : "";
        return url
          ? `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${label}</a>`
          : `<span>${label}: ${escapeHtml(value)}</span>`;
      }

      async function loadMatches() {
        const list = document.querySelector("#matches-list");
        if (!list) return;
        const token = localStorage.getItem("bc_connect_token");
        try {
          const matches = await request("/api/matches", {
            headers: {Authorization: `Bearer ${token}`},
          });
          if (!matches.length) {
            list.innerHTML = '<p class="muted">Tes matchs apparaîtront ici.</p>';
            return;
          }
          list.innerHTML = matches.map((match) => `
            <article class="match-card">
              <strong>${escapeHtml(match.name)}</strong>
              <span>${escapeHtml([match.cycle, match.filiere, match.classe].filter(Boolean).join(" · "))}</span>
              <p>${escapeHtml(match.bio || "Aucune bio.")}</p>
              <div class="social-links">
                ${socialLink("Instagram", match.instagram)}
                ${socialLink("Snapchat", match.snapchat)}
                ${socialLink("WhatsApp", match.whatsapp)}
              </div>
            </article>
          `).join("");
        } catch (error) {
          list.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`;
        }
      }

      async function loadDiscover() {
        const list = document.querySelector("#discover-list");
        if (!list) return;
        const token = localStorage.getItem("bc_connect_token");
        try {
          const profiles = await request("/api/discover", {
            headers: {Authorization: `Bearer ${token}`},
          });
          discoverProfiles = profiles;
          renderNextDiscoverCard();
        } catch (error) {
          list.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`;
        }
      }

      function renderNextDiscoverCard() {
        const list = document.querySelector("#discover-list");
        if (!list) return;
        if (!discoverProfiles.length) {
          list.innerHTML = '<p class="muted">Tu as parcouru tous les profils disponibles pour le moment.</p>';
          return;
        }
        const profile = discoverProfiles[0];
        const initials = profile.name.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();
        list.innerHTML = `
          <div class="card-stack">
            <article class="discover-card" data-profile-id="${profile.id}">
              <div class="profile-visual">
                <img src="/static/assets/campus-connect.svg" alt="">
                <span class="profile-initials">${escapeHtml(initials)}</span>
                <div class="profile-caption">
                  <strong>${escapeHtml(profile.name)}${profile.age ? `, ${profile.age}` : ""}</strong>
                  <span>${escapeHtml([profile.cycle, profile.filiere, profile.classe].filter(Boolean).join(" · "))}</span>
                </div>
              </div>
              <div class="profile-details">
                <p>${escapeHtml(profile.bio || "Profil sans bio pour le moment.")}</p>
                <span>${escapeHtml(profile.interests.join(" · ") || "Aucun centre d’intérêt renseigné")}</span>
              </div>
            </article>
            <div class="discover-actions">
              <button class="round-action pass" type="button" aria-label="Passer">×</button>
              <button class="round-action like" type="button" aria-label="J’aime">♥</button>
            </div>
          </div>
        `;
        const card = list.querySelector(".discover-card");
        list.querySelector(".pass").addEventListener("click", () => submitSwipe(card, false));
        list.querySelector(".like").addEventListener("click", () => submitSwipe(card, true));
        attachSwipe(card);
      }

      function attachSwipe(card) {
        let startX = 0;
        let currentX = 0;
        let dragging = false;
        card.addEventListener("pointerdown", (event) => {
          dragging = true;
          startX = event.clientX;
          card.setPointerCapture(event.pointerId);
          card.classList.add("dragging");
        });
        card.addEventListener("pointermove", (event) => {
          if (!dragging) return;
          currentX = event.clientX - startX;
          card.style.transform = `translateX(${currentX}px) rotate(${currentX / 18}deg)`;
        });
        card.addEventListener("pointerup", () => {
          if (!dragging) return;
          dragging = false;
          card.classList.remove("dragging");
          if (Math.abs(currentX) >= 100) {
            submitSwipe(card, currentX > 0);
          } else {
            card.style.transform = "";
          }
          currentX = 0;
        });
      }

      async function submitSwipe(card, liked) {
        const token = localStorage.getItem("bc_connect_token");
        const targetId = Number(card.dataset.profileId);
        card.classList.add(liked ? "swipe-right" : "swipe-left");
        try {
          const result = await request("/api/swipe", {
            method: "POST",
            headers: {Authorization: `Bearer ${token}`},
            body: JSON.stringify({target_id: targetId, liked}),
          });
          discoverProfiles = discoverProfiles.filter((profile) => profile.id !== targetId);
          if (result.matched) {
            document.querySelector("#match-modal").hidden = false;
          }
          setTimeout(renderNextDiscoverCard, 220);
        } catch (error) {
          card.classList.remove("swipe-right", "swipe-left");
          setMessage(error.message, true);
        }
      }

      document.querySelector("#close-match").addEventListener("click", () => {
        document.querySelector("#match-modal").hidden = true;
      });
    }
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
