/**
 * YouTube Prospector - Side Panel Controller
 * Gerencia autenticação, cronômetro de trabalho, ciclos de produção, detecção de canais e atalhos ADMIN.
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
  const userStatusText = document.getElementById("user-status-text");
  const btnLogout = document.getElementById("btn-logout");

  const sessionStatusBadge = document.getElementById("session-status-badge");
  const sessionCycleName = document.getElementById("session-cycle-name");
  const sessionTimer = document.getElementById("session-timer");
  const sessionPace = document.getElementById("session-pace");
  const sessionCollected = document.getElementById("session-collected");
  const sessionTarget = document.getElementById("session-target");
  const sessionProgressFill = document.getElementById("session-progress-fill");

  const sessionActionsContainer = document.getElementById("session-actions-container");
  const sessionStartContainer = document.getElementById("session-start-container");
  const btnTogglePause = document.getElementById("btn-toggle-pause");
  const btnPauseText = document.getElementById("btn-pause-text");
  const btnFinishSession = document.getElementById("btn-finish-session");
  const btnStartSession = document.getElementById("btn-start-session");

  const customTargetContainer = document.getElementById("custom-target-container");
  const inputDailyTarget = document.getElementById("input-daily-target");
  const inputTargetHours = document.getElementById("input-target-hours");

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
  let heartbeatInterval = null;
  let selectedCycleType = "8H";
  let selectedTargetHours = 8.0;
  let selectedDailyTarget = 160;

  // Initialize
  await checkAuth();

  // --------------------------------------------------------------------------
  // AUTHENTICATION
  // --------------------------------------------------------------------------

  async function checkAuth() {
    try {
      const user = await window.prospectorAPI.getMe();
      if (user && user.id) {
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
    clearInterval(heartbeatInterval);
    viewLogin.classList.remove("hidden");
    viewWorkspace.classList.add("hidden");
  }

  async function showWorkspaceView() {
    viewLogin.classList.add("hidden");
    viewWorkspace.classList.remove("hidden");

    // Populate user info
    if (currentUser) {
      userDisplayName.textContent = currentUser.name || "Operador";
      userAvatarInitial.textContent = (currentUser.name || "U").charAt(0).toUpperCase();
      userAvatarInitial.style.backgroundImage = 'none';

      // Load avatar from profile
      try {
        const prof = await window.prospectorAPI.getMyProfile();
        if (prof && prof.avatar_url) {
          userAvatarInitial.style.backgroundImage = `url('${prof.avatar_url}')`;
          userAvatarInitial.textContent = '';
        }
      } catch (e) {
        // Fallback to initial
      }
      
      const role = currentUser.role || "USER";
      userRoleBadge.textContent = role;

      if (userStatusText) {
        userStatusText.textContent = "● Operador Ativo";
      }

      // Style role badge
      if (role === "ADMIN") {
        userRoleBadge.style.backgroundColor = "#27272a";
        userRoleBadge.style.color = "#ffffff";
        userRoleBadge.style.border = "1px solid #52525b";
      } else {
        userRoleBadge.style.backgroundColor = "#18181b";
        userRoleBadge.style.color = "#a1a1aa";
        userRoleBadge.style.border = "1px solid #27272a";
      }
    }

    await loadCurrentSession();
    updatePageChannelsStats();
    updateLiveMusic();

    // Start economical intervals (relaxed polling to save Vercel bandwidth)
    clearInterval(pollInterval);
    clearInterval(heartbeatInterval);

    window.prospectorAPI.heartbeat().catch(() => {});
    heartbeatInterval = setInterval(() => {
      window.prospectorAPI.heartbeat().catch(() => {});
    }, 60000); // 60s economical heartbeat

    pollInterval = setInterval(() => {
      updateLiveMusic();
    }, 60000); // 60s relaxed music poll
  }

  async function updateLiveMusic() {
    try {
      const musicStatus = await window.prospectorAPI.getMusicStatus();
      const artEl = document.getElementById("sp-music-art");
      const titleEl = document.getElementById("sp-music-title");
      const artistEl = document.getElementById("sp-music-artist");
      const badgeEl = document.getElementById("music-provider-badge");

      if (!musicStatus) return;

      const spNow = musicStatus.spotify && musicStatus.spotify.now_playing;
      if (spNow && spNow.track_name) {
        titleEl.textContent = spNow.track_name;
        artistEl.textContent = spNow.artist || "Spotify";
        badgeEl.textContent = "SPOTIFY";
        badgeEl.style.color = "#10b981";
        badgeEl.style.background = "rgba(16, 185, 129, 0.15)";
        if (spNow.album_art) {
          artEl.style.backgroundImage = `url('${spNow.album_art}')`;
          artEl.textContent = "";
        } else {
          artEl.style.backgroundImage = "none";
          artEl.textContent = "🎵";
        }
      } else {
        titleEl.textContent = "Nenhuma música detectada";
        artistEl.textContent = "Conecte ou toque no Spotify / YouTube Music";
        badgeEl.textContent = "MUSIC";
        badgeEl.style.color = "#94a3b8";
        badgeEl.style.background = "rgba(148, 163, 184, 0.1)";
        artEl.style.backgroundImage = "none";
        artEl.textContent = "🎵";
      }
    } catch (e) {}
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
  // CYCLE SELECTION
  // --------------------------------------------------------------------------

  document.querySelectorAll(".cycle-selector-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".cycle-selector-btn").forEach((b) => {
        b.style.backgroundColor = "#1e293b";
        b.style.color = "#e2e8f0";
      });
      btn.style.backgroundColor = "#f59e0b";
      btn.style.color = "#0b0f17";

      selectedCycleType = btn.dataset.cycle;
      selectedTargetHours = parseFloat(btn.dataset.hours) || 8.0;
      selectedDailyTarget = parseInt(btn.dataset.target, 10) || 160;

      if (selectedCycleType === "CUSTOM") {
        customTargetContainer.classList.remove("hidden");
      } else {
        customTargetContainer.classList.add("hidden");
        inputDailyTarget.value = selectedDailyTarget;
        inputTargetHours.value = selectedTargetHours;
      }
    });
  });

  // --------------------------------------------------------------------------
  // WORK SESSION MANAGEMENT (LOCAL-FIRST)
  // --------------------------------------------------------------------------

  async function loadCurrentSession() {
    try {
      // 1. Prioridade para sessão local
      let session = await window.prospectorAPI.getLocalSession();
      if (!session) {
        session = await window.prospectorAPI.getCurrentSession();
      }

      // Sincroniza quantidade de pendentes locais se houver
      if (session) {
        const pending = await window.prospectorAPI.getPendingChannels();
        if (pending.length > 0 && (session.collected_count == null || session.collected_count < pending.length)) {
          session.collected_count = pending.length;
        }
      }

      renderSession(session);
    } catch (err) {
      console.error("[SidePanel] Error loading session:", err);
    }
  }

  function renderSession(session) {
    currentSession = session;
    clearInterval(timerInterval);

    if (!session || session.status === "FINISHED") {
      sessionStatusBadge.textContent = "● SEM SESSÃO";
      sessionStatusBadge.className = "sp-badge sp-badge-paused";
      sessionCycleName.textContent = "Nenhum ciclo ativo";
      sessionTimer.textContent = "00:00:00";
      sessionPace.textContent = "0,0/h";
      sessionCollected.textContent = "0";
      sessionTarget.textContent = "160";
      sessionProgressFill.style.width = "0%";

      if (userStatusText) userStatusText.textContent = "● Conectado (Parado)";
      if (sessionActionsContainer) sessionActionsContainer.classList.add("hidden");
      if (sessionStartContainer) sessionStartContainer.classList.remove("hidden");
      return;
    }

    if (sessionActionsContainer) sessionActionsContainer.classList.remove("hidden");
    if (sessionStartContainer) sessionStartContainer.classList.add("hidden");

    const isActive = session.status === "ACTIVE";
    sessionStatusBadge.textContent = isActive ? "● ATIVA" : "● PAUSADA";
    sessionStatusBadge.className = isActive ? "sp-badge sp-badge-active" : "sp-badge sp-badge-paused";
    btnPauseText.textContent = isActive ? "⏸️ Pausar" : "▶️ Continuar";

    if (userStatusText) {
      userStatusText.textContent = isActive ? "● Coletando no YouTube" : "● Sessão Pausada";
    }

    // Cycle name
    let cycleTitle = "Ciclo 8h";
    if (session.cycle_type === "6H") cycleTitle = "Ciclo 6h";
    else if (session.cycle_type === "CUSTOM") cycleTitle = `Ciclo Personalizado (${session.target_hours}h)`;
    sessionCycleName.textContent = `${cycleTitle} (Meta: ${session.daily_target})`;

    const collected = session.collected_count || 0;
    const target = session.daily_target || 160;
    sessionCollected.textContent = collected;
    sessionTarget.textContent = target;

    let activeSecs = session.current_active_seconds != null ? session.current_active_seconds : (session.active_seconds || 0);
    const activeHours = activeSecs / 3600.0;
    const currentRate = activeHours > 0.001 ? (collected / activeHours) : 0.0;
    sessionPace.textContent = `${currentRate.toFixed(1).replace(".", ",")}/h`;

    const pct = target > 0 ? Math.min(100, Math.round((collected / target) * 100)) : 0;
    sessionProgressFill.style.width = `${pct}%`;

    sessionTimer.textContent = formatSeconds(activeSecs);

    if (isActive) {
      const startTime = Date.now();
      timerInterval = setInterval(() => {
        const elapsedSinceRender = Math.floor((Date.now() - startTime) / 1000);
        const liveSecs = activeSecs + elapsedSinceRender;
        sessionTimer.textContent = formatSeconds(liveSecs);
        
        const liveHours = liveSecs / 3600.0;
        const liveRate = liveHours > 0.001 ? (session.collected_count / liveHours) : 0.0;
        sessionPace.textContent = `${liveRate.toFixed(1).replace(".", ",")}/h`;
      }, 1000);
    }
  }

  function formatSeconds(secs) {
    if (!secs || secs < 0) secs = 0;
    const h = String(Math.floor(secs / 3600)).padStart(2, "0");
    const m = String(Math.floor((secs % 3600) / 60)).padStart(2, "0");
    const s = String(secs % 60).padStart(2, "0");
    return `${h}:${m}:${s}`;
  }

  btnStartSession.addEventListener("click", async () => {
    let target = selectedDailyTarget;
    let hours = selectedTargetHours;
    if (selectedCycleType === "CUSTOM") {
      target = parseInt(inputDailyTarget.value, 10) || 160;
      hours = parseFloat(inputTargetHours.value) || 8.0;
    }
    btnStartSession.disabled = true;
    btnStartSession.textContent = "INICIANDO...";
    try {
      const session = await window.prospectorAPI.startSession({
        daily_target: target,
        target_hours: hours,
        cycle_type: selectedCycleType
      });
      renderSession(session);
      showToast(`Turno de ${hours}h iniciado com sucesso!`);
    } catch (err) {
      showToast(err.message || "Erro ao iniciar turno.", "error");
    } finally {
      btnStartSession.disabled = false;
      btnStartSession.innerHTML = "<span>▶️ INICIAR TURNO DE TRABALHO</span>";
    }
  });

  btnTogglePause.addEventListener("click", async () => {
    if (!currentSession) return;
    btnTogglePause.disabled = true;
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
    } finally {
      btnTogglePause.disabled = false;
    }
  });

  btnFinishSession.addEventListener("click", async () => {
    if (!confirm("Deseja realmente finalizar a sessão de trabalho atual?")) return;
    btnFinishSession.disabled = true;
    btnFinishSession.textContent = "CONSOLIDANDO...";
    try {
      let activeSecs = currentSession.active_seconds || 0;
      if (currentSession.status === "ACTIVE") {
        const lastResumed = currentSession.last_resumed_at ? new Date(currentSession.last_resumed_at).getTime() : Date.now();
        const elapsed = Math.max(0, Math.floor((Date.now() - lastResumed) / 1000));
        activeSecs += elapsed;
      }
      const pendingChannels = await window.prospectorAPI.getPendingChannels();
      const finishPayload = {
        session_id: currentSession.id,
        active_seconds: activeSecs,
        ended_at: new Date().toISOString(),
        channels: pendingChannels
      };
      const result = await window.prospectorAPI.finishSession(finishPayload);
      renderSession(null);
      const insertedCount = result.inserted_count != null ? result.inserted_count : pendingChannels.length;
      showToast(`Sessão finalizada com sucesso! ${insertedCount} novos canais consolidados.`);
    } catch (err) {
      showToast(err.message || "Falha ao finalizar. Seus dados estão preservados localmente!", "error");
    } finally {
      btnFinishSession.disabled = false;
      btnFinishSession.innerHTML = "<span>⏹️ Finalizar</span>";
    }
  });

  // Escuta atualizações locais disparadas pelo content script
  chrome.runtime.onMessage.addListener((request) => {
    if (request.action === "LOCAL_CHANNELS_UPDATED" && currentSession && currentSession.status === "ACTIVE") {
      window.prospectorAPI.getLocalSession().then((localSession) => {
        if (localSession) {
          currentSession.collected_count = localSession.collected_count;
          sessionCollected.textContent = localSession.collected_count;
          const target = localSession.daily_target || 160;
          const pct = target > 0 ? Math.min(100, Math.round((localSession.collected_count / target) * 100)) : 0;
          sessionProgressFill.style.width = `${pct}%`;
        }
      });
    }
  });

  // --------------------------------------------------------------------------
  // CURRENT YOUTUBE PAGE DETECTED CHANNELS
  // --------------------------------------------------------------------------

  async function updatePageChannelsStats() {
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      console.log('[SidePanel] Active tab query result:', tab);
      if (!tab || !tab.id) return;
      console.log('[SidePanel] Active tab URL:', tab.url);
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
    if (!toast) return;
    toast.textContent = msg;
    toast.style.borderColor = type === "error" ? "#f43f5e" : "#475569";
    toast.classList.remove("hidden");
    setTimeout(() => {
      toast.classList.add("hidden");
    }, 2800);
  }
});
