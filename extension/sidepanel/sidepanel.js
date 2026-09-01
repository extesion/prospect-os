/**
 * YouTube Prospector - Side Panel Controller
 * Gerencia autenticação, cronômetro de trabalho, detecção de canais na aba ativa e atalhos ADMIN.
 */

document.addEventListener("DOMContentLoaded", async () => {
  // Elements
  const viewLogin = document.getElementById("view-login");
  const viewWorkspace = document.getElementById("view-workspace");
  const formLogin = document.getElementById("form-login");
  const loginEmail = document.getElementById("login-email");
  const loginPassword = document.getElementById("login-password");
  const loginError = document.getElementById("login-error");
  const btnLogin = document.getElementById("btn-login");

  const userDisplayName = document.getElementById("user-display-name");
  const userAvatarInitial = document.getElementById("user-avatar-initial");
  const userRoleBadge = document.getElementById("user-role-badge");
  const btnLogout = document.getElementById("btn-logout");

  const sessionStatusBadge = document.getElementById("session-status-badge");
  const sessionTimer = document.getElementById("session-timer");
  const sessionPace = document.getElementById("session-pace");
  const sessionCollected = document.getElementById("session-collected");
  const sessionTarget = document.getElementById("session-target");
  const sessionProgressFill = document.getElementById("session-progress-fill");

  const btnTogglePause = document.getElementById("btn-toggle-pause");
  const btnPauseText = document.getElementById("btn-pause-text");
  const btnFinishSession = document.getElementById("btn-finish-session");
  const btnStartSession = document.getElementById("btn-start-session");

  const pageNewCount = document.getElementById("page-new-count");
  const pageExistsCount = document.getElementById("page-exists-count");
  const btnRefreshPage = document.getElementById("btn-refresh-page");
  const btnCollectAllNew = document.getElementById("btn-collect-all-new");

  const adminShortcuts = document.getElementById("admin-shortcuts-container");
  const btnOpenDashboard = document.getElementById("btn-open-dashboard");
  const btnOpenQualifier = document.getElementById("btn-open-qualifier");
  const btnOpenUsers = document.getElementById("btn-open-users");
  const btnOpenApis = document.getElementById("btn-open-apis");

  // State
  let currentUser = null;
  let currentSession = null;
  let timerInterval = null;
  let pollInterval = null;

  // Initialize
  await checkAuth();

  // --------------------------------------------------------------------------
  // AUTHENTICATION
  // --------------------------------------------------------------------------

  async function checkAuth() {
    try {
      const user = await window.prospectorAPI.getMe();
      if (user) {
        currentUser = user;
        showWorkspaceView();
      } else {
        showLoginView();
      }
    } catch {
      showLoginView();
    }
  }

  function showLoginView() {
    clearInterval(timerInterval);
    clearInterval(pollInterval);
    viewLogin.classList.remove("hidden");
    viewWorkspace.classList.add("hidden");
  }

  function showWorkspaceView() {
    viewLogin.classList.add("hidden");
    viewWorkspace.classList.remove("hidden");

    // Populate user info
    if (currentUser) {
      userDisplayName.textContent = currentUser.name || "Operador";
      userAvatarInitial.textContent = (currentUser.name || "U").charAt(0).toUpperCase();
      
      const role = currentUser.role || "USER";
      userRoleBadge.textContent = role;

      // Show Admin Shortcuts only for ADMIN
      if (role === "ADMIN") {
        adminShortcuts.classList.remove("hidden");
        userRoleBadge.style.backgroundColor = "#312e81";
        userRoleBadge.style.color = "#c7d2fe";
      } else {
        adminShortcuts.classList.add("hidden");
      }
    }

    loadCurrentSession();
    updatePageChannelsStats();

    // Start intervals
    clearInterval(pollInterval);
    pollInterval = setInterval(() => {
      updatePageChannelsStats();
    }, 2500);
  }

  formLogin.addEventListener("submit", async (e) => {
    e.preventDefault();
    loginError.classList.add("hidden");
    btnLogin.disabled = true;
    btnLogin.textContent = "AUTENTICANDO...";

    try {
      const email = loginEmail.value.trim();
      const password = loginPassword.value;
      const res = await window.prospectorAPI.login(email, password);
      currentUser = res.user;
      showToast("Login realizado com sucesso!");
      showWorkspaceView();
    } catch (err) {
      loginError.textContent = err.message || "Erro ao conectar.";
      loginError.classList.remove("hidden");
    } finally {
      btnLogin.disabled = false;
      btnLogin.textContent = "ENTRAR NA PLATAFORMA";
    }
  });

  btnLogout.addEventListener("click", async () => {
    if (!confirm("Deseja realmente sair?")) return;
    await window.prospectorAPI.logout();
    currentUser = null;
    currentSession = null;
    showLoginView();
  });

  // --------------------------------------------------------------------------
  // WORK SESSION MANAGEMENT
  // --------------------------------------------------------------------------

  async function loadCurrentSession() {
    try {
      const session = await window.prospectorAPI.getCurrentSession();
      renderSession(session);
    } catch (err) {
      console.error("[SidePanel] Error loading session:", err);
    }
  }

  function renderSession(session) {
    currentSession = session;
    clearInterval(timerInterval);

    const sessionActions = document.querySelector(".sp-session-actions");

    if (!session || session.status === "FINISHED") {
      sessionStatusBadge.textContent = "● SEM SESSÃO";
      sessionStatusBadge.className = "sp-badge sp-badge-paused";
      sessionTimer.textContent = "00:00:00";
      sessionPace.textContent = "0,0/h";
      sessionCollected.textContent = "0";
      sessionTarget.textContent = "160";
      sessionProgressFill.style.width = "0%";

      if (sessionActions) sessionActions.classList.add("hidden");
      btnStartSession.classList.remove("hidden");
      return;
    }

    if (sessionActions) sessionActions.classList.remove("hidden");
    btnStartSession.classList.add("hidden");

    const isActive = session.status === "ACTIVE";
    sessionStatusBadge.textContent = isActive ? "● ATIVA" : "● PAUSADA";
    sessionStatusBadge.className = isActive ? "sp-badge sp-badge-active" : "sp-badge sp-badge-paused";
    btnPauseText.textContent = isActive ? "⏸️ Pausar" : "▶️ Continuar";

    sessionCollected.textContent = session.collected_count;
    sessionTarget.textContent = session.daily_target;
    sessionPace.textContent = `${session.current_pace_per_hour.toFixed(1).replace(".", ",")}/h`;

    const pct = Math.min(100, (session.collected_count / session.daily_target) * 100);
    sessionProgressFill.style.width = `${pct}%`;

    // Local live timer
    let activeSecs = session.active_seconds;
    sessionTimer.textContent = formatSeconds(activeSecs);

    if (isActive) {
      timerInterval = setInterval(() => {
        activeSecs++;
        sessionTimer.textContent = formatSeconds(activeSecs);
      }, 1000);
    }
  }

  function formatSeconds(secs) {
    const h = String(Math.floor(secs / 3600)).padStart(2, "0");
    const m = String(Math.floor((secs % 3600) / 60)).padStart(2, "0");
    const s = String(secs % 60).padStart(2, "0");
    return `${h}:${m}:${s}`;
  }

  btnStartSession.addEventListener("click", async () => {
    try {
      const session = await window.prospectorAPI.startSession({ cycle_type: "8H" });
      renderSession(session);
      showToast("Turno de 8h iniciado com sucesso!");
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  btnTogglePause.addEventListener("click", async () => {
    if (!currentSession) return;
    try {
      let updated;
      if (currentSession.status === "ACTIVE") {
        updated = await window.prospectorAPI.pauseSession();
        showToast("Sessão pausada.");
      } else {
        updated = await window.prospectorAPI.resumeSession();
        showToast("Sessão retomada!");
      }
      renderSession(updated);
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  btnFinishSession.addEventListener("click", async () => {
    if (!confirm("Deseja realmente finalizar a sessão de trabalho atual?")) return;
    try {
      await window.prospectorAPI.finishSession();
      renderSession(null);
      showToast("Sessão finalizada!");
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  // --------------------------------------------------------------------------
  // CURRENT YOUTUBE PAGE DETECTED CHANNELS
  // --------------------------------------------------------------------------

  async function updatePageChannelsStats() {
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab || !tab.id) return;

      chrome.tabs.sendMessage(tab.id, { action: "GET_PAGE_STATS" }, (response) => {
        if (chrome.runtime.lastError || !response) {
          pageNewCount.textContent = "0";
          pageExistsCount.textContent = "0";
          btnCollectAllNew.disabled = true;
          btnCollectAllNew.textContent = "⚡ COLETAR NOVOS";
          return;
        }

        const newCount = response.newCount || 0;
        const existsCount = response.existsCount || 0;

        pageNewCount.textContent = newCount;
        pageExistsCount.textContent = existsCount;

        btnCollectAllNew.disabled = newCount === 0;
        btnCollectAllNew.textContent = newCount > 0 ? `⚡ COLETAR ${newCount} NOVOS` : "⚡ COLETAR NOVOS";
      });
    } catch {
      // Tab not ready
    }
  }

  btnRefreshPage.addEventListener("click", () => {
    updatePageChannelsStats();
    loadCurrentSession();
    showToast("Dados atualizados!");
  });

  btnCollectAllNew.addEventListener("click", async () => {
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab || !tab.id) return;

      btnCollectAllNew.disabled = true;
      btnCollectAllNew.textContent = "COLETANDO...";

      chrome.tabs.sendMessage(tab.id, { action: "TRIGGER_COLLECT_ALL_NEW" }, (res) => {
        setTimeout(() => {
          updatePageChannelsStats();
          loadCurrentSession();
        }, 1500);
      });
    } catch (err) {
      showToast("Erro ao disparar coleta.", "error");
    }
  });

  // --------------------------------------------------------------------------
  // ADMIN SHORTCUTS
  // --------------------------------------------------------------------------

  const BASE_WEB_URL = "https://prospect-os-seven.vercel.app";

  if (btnOpenDashboard) {
    btnOpenDashboard.addEventListener("click", () => {
      chrome.tabs.create({ url: `${BASE_WEB_URL}/dashboard` });
    });
  }

  if (btnOpenQualifier) {
    btnOpenQualifier.addEventListener("click", () => {
      chrome.tabs.create({ url: `${BASE_WEB_URL}/qualifier` });
    });
  }

  if (btnOpenUsers) {
    btnOpenUsers.addEventListener("click", () => {
      chrome.tabs.create({ url: `${BASE_WEB_URL}/users` });
    });
  }

  if (btnOpenApis) {
    btnOpenApis.addEventListener("click", () => {
      chrome.tabs.create({ url: `${BASE_WEB_URL}/youtube-apis` });
    });
  }

  // --------------------------------------------------------------------------
  // UTILITIES
  // --------------------------------------------------------------------------

  function showToast(msg, type = "info") {
    const toast = document.getElementById("sp-toast");
    toast.textContent = msg;
    toast.style.borderColor = type === "error" ? "#f43f5e" : "#475569";
    toast.classList.remove("hidden");
    setTimeout(() => {
      toast.classList.add("hidden");
    }, 2800);
  }
});
