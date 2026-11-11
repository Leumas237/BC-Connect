if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/static/sw.js"));
}

const form = document.querySelector("#auth-form");
const nameInput = document.querySelector("#name");
const emailInput = document.querySelector("#email");
const passwordInput = document.querySelector("#password");
const moderatorCodeInput = document.querySelector("#moderator-code");
const privacyInput = document.querySelector("#privacy-accepted");
const title = document.querySelector("#auth-title");
const message = document.querySelector("#auth-message");
const toggle = document.querySelector("#toggle-auth");
const account = document.querySelector("#account");
const installButton = document.querySelector("#install-app");
const sectionMenu = document.querySelector("#section-menu");

let signupMode = true;
let deferredInstallPrompt;
let discoverProfiles = [];
let socket;

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
  privacyInput.closest("label").hidden = !signupMode;
  privacyInput.required = signupMode;
  moderatorCodeInput.closest("label").hidden = !signupMode;
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
        <div class="account-tabs" role="tablist" aria-label="Espace communautaire">
          <button class="account-tab active" data-account-tab="wall" type="button">Mon mur</button>
          <button class="account-tab" data-account-tab="swipe" type="button">Swipe</button>
          ${user.is_admin ? '<button class="account-tab" data-account-tab="moderation" type="button">Modération</button>' : ""}
        </div>
        <section class="account-view active" data-account-view="wall">
          <form id="wall-form" class="kyi-form">
            <h3>Partager sur mon mur</h3>
            <textarea name="body" maxlength="2000" rows="4" placeholder="Une idée, une question ou une actualité du campus..."></textarea>
            <input name="media" type="file" accept="image/jpeg,image/png,image/webp">
            <button class="button primary" type="submit">Publier</button>
          </form>
          <div id="wall-list"><p class="muted">Chargement du mur...</p></div>
        </section>
        <section class="account-view" data-account-view="swipe" hidden>
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
        <form id="photo-form" class="kyi-form">
          <h3>Mes photos</h3>
          <input name="photo" type="file" accept="image/jpeg,image/png,image/webp" required>
          <button class="button secondary" type="submit">Ajouter une photo</button>
          <div id="photo-list" class="photo-list"></div>
        </form>
        <button id="enable-push" class="text-button" type="button">Activer les notifications de match</button>
        <section class="discovery">
          <h3>Découvrir la communauté</h3>
          <div id="discover-list"><p class="muted">Chargement des profils...</p></div>
        </section>
        <section class="matches">
          <h3>Mes matchs</h3>
          <div id="matches-list"><p class="muted">Chargement des matchs...</p></div>
        </section>
        </section>
        ${user.is_admin ? `
          <section class="account-view admin-panel" data-account-view="moderation" hidden>
            <h3>Dashboard administrateur</h3>
            <form id="moderator-code-form" class="moderator-code-form">
              <label>Réinitialiser le code d’invitation modérateur<input name="code" type="password" minlength="8" required></label>
              <button class="button secondary" type="submit">Enregistrer le code</button>
            </form>
            <div class="admin-tabs" role="tablist" aria-label="Sections administrateur">
              <button class="admin-tab active" data-admin-tab="moderation" type="button">Modération</button>
              <button class="admin-tab" data-admin-tab="stats" type="button">Stats</button>
              <button class="admin-tab" data-admin-tab="activity" type="button">Activité</button>
            </div>
            <div class="admin-view active" data-admin-view="moderation">
              <div id="admin-kyi-list"><p class="muted">Chargement des dossiers KYI...</p></div>
              <div id="admin-report-list"><p class="muted">Chargement des signalements...</p></div>
            </div>
            <div class="admin-view" data-admin-view="stats" hidden>
              <div id="admin-stats" class="stats-grid"><p class="muted">Chargement des statistiques...</p></div>
            </div>
            <div class="admin-view" data-admin-view="activity" hidden>
              <div class="activity-actions">
                <button id="export-activity" class="button secondary" type="button">Exporter le journal CSV</button>
              </div>
              <div id="admin-activity"><p class="muted">Chargement du journal...</p></div>
            </div>
          </section>
        ` : ""}
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
  account.querySelector("#photo-form")?.addEventListener("submit", submitPhoto);
  account.querySelector("#wall-form")?.addEventListener("submit", submitWallPost);
  account.querySelector("#moderator-code-form")?.addEventListener("submit", saveModeratorCode);
  if (user.approved) {
    account.querySelectorAll(".account-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        account.querySelectorAll(".account-tab").forEach((item) => item.classList.toggle("active", item === tab));
        account.querySelectorAll(".account-view").forEach((view) => {
          view.hidden = view.dataset.accountView !== tab.dataset.accountTab;
          view.classList.toggle("active", !view.hidden);
        });
      });
    });
    loadWall();
    loadProfile();
    loadDiscover();
    loadMatches();
    connectRealtime();
    document.querySelector("#enable-push")?.addEventListener("click", setupPush);
  }
  if (user.is_admin) loadAdmin();
}

async function submitWallPost(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  const token = localStorage.getItem("bc_connect_token");
  try {
    const response = await fetch("/api/wall/posts", {
      method: "POST",
      headers: {Authorization: `Bearer ${token}`},
      body: data,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Publication impossible.");
    form.reset();
    await loadWall();
  } catch (error) {
    setMessage(error.message, true);
  }
}

async function loadWall() {
  const list = document.querySelector("#wall-list");
  if (!list) return;
  const token = localStorage.getItem("bc_connect_token");
  try {
    const posts = await request("/api/wall", {headers: {Authorization: `Bearer ${token}`}});
    list.innerHTML = posts.length ? posts.map((post) => `
      <article class="wall-post" data-post-id="${post.id}">
        <div class="wall-post-header"><strong>${escapeHtml(post.name)}</strong><span>${escapeHtml(post.created_at)}</span></div>
        ${post.body ? `<p>${escapeHtml(post.body)}</p>` : ""}
        ${post.media_filename ? `<img src="/api/wall/media/${encodeURIComponent(post.media_filename)}" alt="Image publiée">` : ""}
        <div class="wall-post-actions">
          <button class="text-button wall-react" data-reaction="like" type="button">${post.my_reaction === "like" ? "❤️" : "♡"} ${post.reactions}</button>
          <button class="text-button wall-comments-toggle" type="button">💬 ${post.comments}</button>
          <button class="text-button wall-comment-add" type="button">Commenter</button>
          ${post.is_mine ? '<button class="text-button wall-delete" type="button">Supprimer</button>' : ""}
        </div>
        <div class="wall-comments" hidden></div>
      </article>
    `).join("") : '<p class="muted">Le mur est encore vide.</p>';
    list.querySelectorAll(".wall-react").forEach((button) => {
      button.addEventListener("click", () => reactToWallPost(button.closest(".wall-post")));
    });
    list.querySelectorAll(".wall-comments-toggle").forEach((button) => {
      button.addEventListener("click", () => toggleWallComments(button.closest(".wall-post")));
    });
    list.querySelectorAll(".wall-comment-add").forEach((button) => {
      button.addEventListener("click", () => addWallComment(button.closest(".wall-post")));
    });
    list.querySelectorAll(".wall-delete").forEach((button) => {
      button.addEventListener("click", () => deleteWallPost(button.closest(".wall-post")));
    });
  } catch (error) {
    list.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`;
  }
}

async function reactToWallPost(post) {
  const token = localStorage.getItem("bc_connect_token");
  await request(`/api/wall/posts/${post.dataset.postId}/reaction`, {
    method: "POST",
    headers: {Authorization: `Bearer ${token}`},
    body: JSON.stringify({reaction: "like"}),
  });
  loadWall();
}

async function toggleWallComments(post) {
  const comments = post.querySelector(".wall-comments");
  if (!comments.hidden) {
    comments.hidden = true;
    return;
  }
  const token = localStorage.getItem("bc_connect_token");
  const items = await request(`/api/wall/posts/${post.dataset.postId}/comments`, {
    headers: {Authorization: `Bearer ${token}`},
  });
  comments.innerHTML = items.length
    ? items.map((item) => `<p><strong>${escapeHtml(item.name)}</strong> ${escapeHtml(item.body)}</p>`).join("")
    : '<p class="muted">Aucun commentaire.</p>';
  comments.hidden = false;
}

async function addWallComment(post) {
  const body = window.prompt("Ton commentaire");
  if (!body?.trim()) return;
  const token = localStorage.getItem("bc_connect_token");
  await request(`/api/wall/posts/${post.dataset.postId}/comments`, {
    method: "POST",
    headers: {Authorization: `Bearer ${token}`},
    body: JSON.stringify({body: body.trim()}),
  });
  loadWall();
}

async function deleteWallPost(post) {
  if (!window.confirm("Supprimer cette publication ?")) return;
  const token = localStorage.getItem("bc_connect_token");
  await request(`/api/wall/posts/${post.dataset.postId}`, {
    method: "DELETE",
    headers: {Authorization: `Bearer ${token}`},
  });
  loadWall();
}

async function saveModeratorCode(event) {
  event.preventDefault();
  const code = new FormData(event.currentTarget).get("code");
  const token = localStorage.getItem("bc_connect_token");
  await request("/api/admin/moderator-code", {
    method: "POST",
    headers: {Authorization: `Bearer ${token}`},
    body: JSON.stringify({code}),
  });
  event.currentTarget.reset();
  setMessage("Code d’invitation modérateur enregistré.");
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
    if (signupMode) {
      payload.name = nameInput.value;
      payload.privacy_accepted = privacyInput.checked;
      payload.moderator_code = moderatorCodeInput.value;
    }
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
  socket?.close();
  socket = null;
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

  function connectRealtime() {
    const token = localStorage.getItem("bc_connect_token");
    if (!token || socket) return;
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${protocol}//${location.host}/ws?token=${encodeURIComponent(token)}`);
    socket.addEventListener("open", () => {
      socket.keepAlive = window.setInterval(() => socket.send("keep-alive"), 25000);
    });
    socket.addEventListener("message", (event) => {
      const payload = JSON.parse(event.data);
      if (payload.type === "match") {
        document.querySelector("#match-modal").hidden = false;
        loadMatches();
      }
    });
    socket.addEventListener("close", () => {
      if (socket?.keepAlive) window.clearInterval(socket.keepAlive);
      socket = null;
    });
  }

  function base64ToBytes(value) {
    const padding = "=".repeat((4 - value.length % 4) % 4);
    const raw = atob((value + padding).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(raw, (character) => character.charCodeAt(0));
  }

  async function setupPush() {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      setMessage("Les notifications push ne sont pas disponibles sur ce navigateur.", true);
      return;
    }
    const key = await request("/api/push/key");
    if (!key.public_key) {
      setMessage("Les notifications push ne sont pas encore configurées sur le serveur.", true);
      return;
    }
    const permission = await Notification.requestPermission();
    if (permission !== "granted") return;
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: base64ToBytes(key.public_key),
    });
    await request("/api/push/subscribe", {
      method: "POST",
      headers: {Authorization: `Bearer ${localStorage.getItem("bc_connect_token")}`},
      body: JSON.stringify(subscription),
    });
    setMessage("Notifications de match activées.");
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
        await loadPhotos(profile.photos || []);
      } catch (error) {
        setMessage(error.message, true);
      }

      async function loadPhotos(photos) {
        const list = document.querySelector("#photo-list");
        if (!list) return;
        const token = localStorage.getItem("bc_connect_token");
        list.innerHTML = "";
        for (const photo of photos) {
          const response = await fetch(`/api/profile/photo/${photo.id}`, {
            headers: {Authorization: `Bearer ${token}`},
          });
          if (!response.ok) continue;
          const imageUrl = URL.createObjectURL(await response.blob());
          const wrapper = document.createElement("div");
          wrapper.className = "photo-item";
          wrapper.innerHTML = `<img src="${imageUrl}" alt="Photo de profil"><button type="button">Supprimer</button>`;
          wrapper.querySelector("button").addEventListener("click", () => deletePhoto(photo.id, wrapper, imageUrl));
          list.appendChild(wrapper);
        }
      }

      async function submitPhoto(event) {
        event.preventDefault();
        const photoForm = event.currentTarget;
        const file = photoForm.elements.photo.files[0];
        if (!file) return;
        const button = photoForm.querySelector("button");
        button.disabled = true;
        const token = localStorage.getItem("bc_connect_token");
        const body = new FormData();
        body.append("photo", file);
        try {
          const response = await fetch("/api/profile/photo", {
            method: "POST",
            headers: {Authorization: `Bearer ${token}`},
            body,
          });
          const payload = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(payload.detail || "Impossible d’ajouter la photo.");
          photoForm.reset();
          const profile = await request("/api/profile", {headers: {Authorization: `Bearer ${token}`}});
          await loadPhotos(profile.photos || []);
          setMessage("Photo ajoutée.");
        } catch (error) {
          setMessage(error.message, true);
        } finally {
          button.disabled = false;
        }
      }

      async function deletePhoto(photoId, wrapper, imageUrl) {
        const token = localStorage.getItem("bc_connect_token");
        const response = await fetch(`/api/profile/photos/${photoId}`, {
          method: "DELETE",
          headers: {Authorization: `Bearer ${token}`},
        });
        if (!response.ok) {
          setMessage("Impossible de supprimer la photo.", true);
          return;
        }
        URL.revokeObjectURL(imageUrl);
        wrapper.remove();
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
              <button class="report-link" data-target-id="${match.id}" type="button">Signaler ce match</button>
            </article>
          `).join("");
          list.querySelectorAll(".report-link").forEach((button) => {
            button.addEventListener("click", () => reportMatch(Number(button.dataset.targetId)));
          });
        } catch (error) {
          list.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`;
        }
  }

        async function reportMatch(targetId) {
          const reason = window.prompt("Pourquoi veux-tu signaler ce match ?");
          if (!reason?.trim()) return;
          const token = localStorage.getItem("bc_connect_token");
          try {
            await request("/api/report", {
              method: "POST",
              headers: {Authorization: `Bearer ${token}`},
              body: JSON.stringify({target_id: targetId, reason: reason.trim()}),
            });
            setMessage("Signalement envoyé. Le match a été fermé.");
            loadMatches();
          } catch (error) {
            setMessage(error.message, true);
          }
  }

          async function loadAdmin() {
            const token = localStorage.getItem("bc_connect_token");
            const kyiList = document.querySelector("#admin-kyi-list");
            const reportList = document.querySelector("#admin-report-list");
            const statsList = document.querySelector("#admin-stats");
            const activityList = document.querySelector("#admin-activity");
            try {
              const [kyi, reports, stats, activity] = await Promise.all([
                request("/api/admin/kyi", {headers: {Authorization: `Bearer ${token}`}}),
                request("/api/admin/reports", {headers: {Authorization: `Bearer ${token}`}}),
                request("/api/admin/stats", {headers: {Authorization: `Bearer ${token}`}}),
                request("/api/admin/activity", {headers: {Authorization: `Bearer ${token}`}}),
              ]);
              kyiList.innerHTML = kyi.length ? kyi.map((item) => `
                <article class="admin-item">
                  <strong>${escapeHtml(item.full_name)}</strong>
                  <span>${escapeHtml(item.email)} · ${escapeHtml(item.classe)}</span>
                  <div>
                    <button class="button secondary admin-kyi-card" data-id="${item.user_id}" type="button">Voir la carte</button>
                    <button class="button primary admin-kyi-action" data-id="${item.user_id}" data-approved="true" type="button">Accepter</button>
                    <button class="button secondary admin-kyi-action" data-id="${item.user_id}" data-approved="false" type="button">Refuser</button>
                  </div>
                </article>
              `).join("") : '<p class="muted">Aucun dossier KYI en attente.</p>';
              reportList.innerHTML = reports.length ? reports.map((item) => `
                <article class="admin-item">
                  <strong>Signalement #${item.id} · ${escapeHtml(item.status)}</strong>
                  <span>${escapeHtml(item.reporter_email)} → ${escapeHtml(item.reported_email)}</span>
                  <p>${escapeHtml(item.reason)}</p>
                  ${item.status === "pending" ? `<button class="button secondary admin-report-action" data-id="${item.id}" data-action="ban" type="button">Bannir</button>
                  <button class="button secondary admin-report-action" data-id="${item.id}" data-action="dismiss" type="button">Classer</button>` : ""}
                </article>
              `).join("") : '<p class="muted">Aucun signalement.</p>';
              statsList.innerHTML = [
                ["Utilisateurs", stats.total_users],
                ["Profils validés", stats.approved_users],
                ["En attente KYI", stats.pending_users],
                ["Comptes bannis", stats.banned_users],
                ["Signalements en attente", stats.pending_reports],
                ["Matchs", stats.total_matches],
                ["Likes aujourd’hui", stats.likes_today],
              ].map(([label, value]) => `
                <article class="stat-card"><strong>${escapeHtml(String(value))}</strong><span>${escapeHtml(label)}</span></article>
              `).join("");
              activityList.innerHTML = activity.length ? `
                <div class="activity-list">
                  ${activity.map((item) => `
                    <article class="activity-item">
                      <strong>${escapeHtml(item.action)}</strong>
                      <span>${escapeHtml(item.actor_email)} · ${escapeHtml(item.created_at)}</span>
                      ${item.details ? `<p>${escapeHtml(item.details)}</p>` : ""}
                    </article>
                  `).join("")}
                </div>
              ` : '<p class="muted">Aucune activité enregistrée.</p>';
              document.querySelectorAll(".admin-tab").forEach((tab) => {
                tab.onclick = () => {
                  document.querySelectorAll(".admin-tab").forEach((item) => item.classList.toggle("active", item === tab));
                  document.querySelectorAll(".admin-view").forEach((view) => {
                    view.hidden = view.dataset.adminView !== tab.dataset.adminTab;
                    view.classList.toggle("active", !view.hidden);
                  });
                };
              });
              document.querySelector("#export-activity").onclick = async () => {
                const response = await fetch("/api/admin/activity.csv", {
                  headers: {Authorization: `Bearer ${token}`},
                });
                if (!response.ok) {
                  setMessage("Impossible d’exporter le journal.", true);
                  return;
                }
                const blob = await response.blob();
                const url = URL.createObjectURL(blob);
                const link = document.createElement("a");
                link.href = url;
                link.download = "bc-connect-activity.csv";
                link.click();
                URL.revokeObjectURL(url);
              };
              document.querySelectorAll(".admin-kyi-action").forEach((button) => {
                button.addEventListener("click", () => decideKyi(Number(button.dataset.id), button.dataset.approved === "true"));
              });
              document.querySelectorAll(".admin-kyi-card").forEach((button) => {
                button.addEventListener("click", () => viewKyiCard(Number(button.dataset.id)));
              });
              document.querySelectorAll(".admin-report-action").forEach((button) => {
                button.addEventListener("click", () => decideReport(Number(button.dataset.id), button.dataset.action));
              });
            } catch (error) {
              setMessage(error.message, true);
            }

            async function viewKyiCard(userId) {
              const token = localStorage.getItem("bc_connect_token");
              const response = await fetch(`/api/admin/kyi-card/${userId}`, {
                headers: {Authorization: `Bearer ${token}`},
              });
              if (!response.ok) {
                setMessage("Impossible de charger la carte KYI.", true);
                return;
              }
              const url = URL.createObjectURL(await response.blob());
              window.open(url, "_blank", "noopener,noreferrer");
            }
          }

          async function decideKyi(userId, approved) {
            const token = localStorage.getItem("bc_connect_token");
            await request(`/api/admin/kyi/${userId}/decision`, {
              method: "POST",
              headers: {Authorization: `Bearer ${token}`},
              body: JSON.stringify({approved}),
            });
            loadAdmin();
          }

          async function decideReport(reportId, action) {
            const token = localStorage.getItem("bc_connect_token");
            await request(`/api/admin/reports/${reportId}`, {
              method: "POST",
              headers: {Authorization: `Bearer ${token}`},
              body: JSON.stringify({action}),
            });
            loadAdmin();
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

toggle.addEventListener("click", () => setSignupMode(!signupMode));
form.addEventListener("submit", submitAuth);
setSignupMode(true);
loadSession();
