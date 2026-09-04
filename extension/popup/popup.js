/**
 * YouTube Prospector - Popup Logic (com Gestão de Sessões & Produtividade)
 */

document.addEventListener("DOMContentLoaded", async () => {
  // Elementos do DOM - Autenticação & Geral
  const connectionPill = document.getElementById("connectionPill");
  const errorBanner = document.getElementById("errorBanner");
  const loginView = document.getElementById("loginView");
  const mainView = document.getElementById("mainView");

  const loginForm = document.getElementById("loginForm");
  const loginEmail = document.getElementById("loginEmail");
  const loginPassword = document.getElementById("loginPassword");
  const btnLogin = document.getElementById("btnLogin");
  const toggleApiUrl = document.getElementById("toggleApiUrl");
  const apiUrlContainer = document.getElementById("apiUrlContainer");
  const customApiUrl = document.getElementById("customApiUrl");

  const userName = document.getElementById("userName");
  const btnLogout = document.getElementById("btnLogout");

  // Elementos da Sessão de Trabalho
  const sessionIdleView = document.getElementById("sessionIdleView");
  const sessionActiveView = document.getElementById("sessionActiveView");
  const btnOpenStartModal = document.getElementById("btnOpenStartModal");
  const sessionCycleName = document.getElementById("sessionCycleName");
  const sessionStatusTag = document.getElementById("sessionStatusTag");
  const sessionTimer = document.getElementById("sessionTimer");
  const sessionProdCount = document.getElementById("sessionProdCount");
  const sessionProdPct = document.getElementById("sessionProdPct");
  const sessionProdBar = document.getElementById("sessionProdBar");
  const sessionCurrentRate = document.getElementById("sessionCurrentRate");
  const sessionTargetRate = document.getElementById("sessionTargetRate");
  const sessionRequiredRate = document.getElementById("sessionRequiredRate");
  const sessionSituationPill = document.getElementById("sessionSituationPill");
  const sessionProjText = document.getElementById("sessionProjText");
  const btnPauseResume = document.getElementById("btnPauseResume");
  const btnOpenFinishModal = document.getElementById("btnOpenFinishModal");

  // Modais
  const startModal = document.getElementById("startModal");
  const btnCloseStartModal = document.getElementById("btnCloseStartModal");
  const startTargetInput = document.getElementById("startTargetInput");
  const customHoursContainer = document.getElementById("customHoursContainer");
  const startCustomHours = document.getElementById("startCustomHours");
  const startPacePreview = document.getElementById("startPacePreview");
  const btnConfirmStart = document.getElementById("btnConfirmStart");

  const finishModal = document.getElementById("finishModal");
  const btnCloseFinishModal = document.getElementById("btnCloseFinishModal");
  const btnCancelFinish = document.getElementById("btnCancelFinish");
  const btnConfirmFinish = document.getElementById("btnConfirmFinish");
  const finishTimeSummary = document.getElementById("finishTimeSummary");
  const finishCountSummary = document.getElementById("finishCountSummary");

  // Elementos de Coleta da Página
  const pageFoundCount = document.getElementById("pageFoundCount");
  const pageNewCount = document.getElementById("pageNewCount");
  const pageExistsCount = document.getElementById("pageExistsCount");
  const btnBulkCollect = document.getElementById("btnBulkCollect");

  const userTodayCount = document.getElementById("userTodayCount");
  const teamTodayCount = document.getElementById("teamTodayCount");
  const btnOpenDashboard = document.getElementById("btnOpenDashboard");

  let dashboardUrl = "https://prospect-os-seven.vercel.app/dashboard";
  let currentSession = null;
  let timerInterval = null;
  let selectedCycleType = "8H";
  let selectedCycleHours = 8.0;

  function showError(msg) {
    if (!msg) {
      errorBanner.style.display = "none";
      return;
    }
    errorBanner.textContent = msg;
    errorBanner.style.display = "block";
  }

  function setStatus(online, text) {
    connectionPill.className = `status-pill ${online ? "status-online" : "status-offline"}`;
    connectionPill.querySelector(".status-text").textContent = text || (online ? "API conectada" : "Sistema offline");
  }

  function formatSeconds(sec) {
    if (sec < 0) sec = 0;
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }

  // Toggle API URL config
  toggleApiUrl.addEventListener("click", () => {
    const isHidden = apiUrlContainer.style.display === "none";
    apiUrlContainer.style.display = isHidden ? "block" : "none";
  });

  chrome.storage.local.get(["apiUrl"], (result) => {
    let url = result.apiUrl || "https://prospect-os-seven.vercel.app/api";
    if (url.includes("localhost:8000")) {
      url = "https://prospect-os-seven.vercel.app/api";
      chrome.storage.local.set({ apiUrl: url });
    }
    customApiUrl.value = url;
  });

  customApiUrl.addEventListener("change", () => {
    const val = customApiUrl.value.trim();
    if (val) {
      chrome.storage.local.set({ apiUrl: val }, () => {
        checkSystem();
      });
    }
  });

  // Verifica saúde e autenticação
  async function checkSystem() {
    showError(null);
    const health = await window.prospectorAPI.checkHealth();
    const isOnline = health.status === "online" || health.status === "degraded";

    if (health.dashboard_url) {
      dashboardUrl = health.dashboard_url;
    }

    setStatus(isOnline, isOnline ? "API conectada" : "Sistema offline");

    if (!isOnline) {
      showError("Não foi possível conectar ao servidor.");
    }

    const { token } = await window.prospectorAuth.init();

    if (token && isOnline) {
      try {
        const me = await window.prospectorAPI.getMe();
        userName.textContent = me.name;
        showMainView();
        loadSessionData();
        loadStats();
        loadPageStats();
      } catch (err) {
        showLoginView();
      }
    } else {
      showLoginView();
    }
  }

  function showLoginView() {
    loginView.style.display = "block";
    mainView.style.display = "none";
    stopTimer();
  }

  function showMainView() {
    loginView.style.display = "none";
    mainView.style.display = "block";
  }

  // Login
  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    showError(null);
    btnLogin.disabled = true;
    btnLogin.textContent = "ENTRANDO...";

    try {
      const email = loginEmail.value.trim();
      const password = loginPassword.value;
      const data = await window.prospectorAPI.login(email, password);

      userName.textContent = data.user.name;
      showMainView();
      loadSessionData();
      loadStats();
      loadPageStats();
    } catch (err) {
      showError(err.message || "Falha na autenticação.");
    } finally {
      btnLogin.disabled = false;
      btnLogin.textContent = "ENTRAR";
    }
  });

  // Logout
  btnLogout.addEventListener("click", async () => {
    await window.prospectorAuth.logout();
    showLoginView();
  });

  // --- GESTÃO DA SESSÃO DE TRABALHO ---

  async function loadSessionData() {
    try {
      let session = await window.prospectorAPI.getLocalSession();
      if (!session) {
        session = await window.prospectorAPI.getCurrentWorkSession();
      }
      if (session) {
        const pending = await window.prospectorAPI.getPendingChannels();
        if (pending.length > 0 && (session.collected_count == null || session.collected_count < pending.length)) {
          session.collected_count = pending.length;
        }
      }
      currentSession = session;
      renderSessionState();
    } catch (err) {
      console.warn("Erro ao carregar sessão:", err);
    }
  }

  function renderSessionState() {
    stopTimer();

    if (!currentSession || currentSession.status === "FINISHED") {
      sessionIdleView.style.display = "block";
      sessionActiveView.style.display = "none";
      return;
    }

    sessionIdleView.style.display = "none";
    sessionActiveView.style.display = "block";

    const isPaused = currentSession.status === "PAUSED";
    sessionStatusTag.className = `session-tag ${isPaused ? "paused" : "active"}`;
    sessionStatusTag.textContent = isPaused ? "⏸ PAUSADO" : "● ATIVO";
    btnPauseResume.textContent = isPaused ? "▶ RETOMAR" : "⏸ PAUSAR";
    btnPauseResume.style.background = isPaused ? "#2563eb" : "#272a38";

    // Informações do Ciclo
    let cycleLabel = "Ciclo 8 Horas";
    if (currentSession.cycle_type === "6H") cycleLabel = "Ciclo 6 Horas";
    else if (currentSession.cycle_type === "CUSTOM") cycleLabel = `Personalizado (${currentSession.target_hours}h)`;
    sessionCycleName.textContent = cycleLabel;

    // Produção
    sessionProdCount.textContent = `${currentSession.collected_count} / ${currentSession.daily_target} canais`;
    sessionProdPct.textContent = `${currentSession.progress_percentage.toFixed(1)}%`;
    sessionProdBar.style.width = `${Math.min(100, currentSession.progress_percentage)}%`;

    // Ritmos
    sessionCurrentRate.textContent = `${currentSession.current_rate.toFixed(1)}/h`;
    sessionTargetRate.textContent = `${currentSession.target_per_hour_display.toFixed(1)}/h`;
    sessionRequiredRate.textContent = `${currentSession.required_rate.toFixed(1)}/h`;

    // Situação
    if (currentSession.status_indicator === "ABOVE_TARGET") {
      sessionSituationPill.className = "situation-pill above-target";
      sessionSituationPill.textContent = "▲ Acima da meta";
    } else if (currentSession.status_indicator === "IN_TARGET") {
      sessionSituationPill.className = "situation-pill in-target";
      sessionSituationPill.textContent = "✓ Dentro da meta";
    } else {
      sessionSituationPill.className = "situation-pill below-target";
      sessionSituationPill.textContent = "⚠ Abaixo da meta";
    }

    sessionProjText.textContent = currentSession.projected_finish_display ? `Prev: ${currentSession.projected_finish_display}` : "";

    // Timer
    let baseSeconds = currentSession.current_active_seconds || currentSession.active_seconds;
    sessionTimer.textContent = formatSeconds(baseSeconds);

    if (!isPaused) {
      // Inicia contagem dinâmica a cada segundo
      const startTime = Date.now();
      timerInterval = setInterval(() => {
        const elapsedSinceRender = Math.floor((Date.now() - startTime) / 1000);
        const liveSeconds = baseSeconds + elapsedSinceRender;
        sessionTimer.textContent = formatSeconds(liveSeconds);
      }, 1000);
    }
  }

  function stopTimer() {
    if (timerInterval) {
      clearInterval(timerInterval);
      timerInterval = null;
    }
  }

  // Abrir Modal de Início
  btnOpenStartModal.addEventListener("click", () => {
    updateStartPacePreview();
    startModal.style.display = "flex";
  });

  btnCloseStartModal.addEventListener("click", () => {
    startModal.style.display = "none";
  });

  // Seleção de Ciclo no Modal
  document.querySelectorAll(".cycle-opt-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".cycle-opt-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      selectedCycleType = btn.dataset.cycle;

      if (selectedCycleType === "CUSTOM") {
        customHoursContainer.style.display = "block";
        selectedCycleHours = parseFloat(startCustomHours.value) || 7.0;
      } else {
        customHoursContainer.style.display = "none";
        selectedCycleHours = parseFloat(btn.dataset.hours);
      }
      updateStartPacePreview();
    });
  });

  startTargetInput.addEventListener("input", updateStartPacePreview);
  startCustomHours.addEventListener("input", () => {
    if (selectedCycleType === "CUSTOM") {
      selectedCycleHours = parseFloat(startCustomHours.value) || 7.0;
      updateStartPacePreview();
    }
  });

  function updateStartPacePreview() {
    const target = parseInt(startTargetInput.value, 10) || 160;
    const hours = selectedCycleHours || 8.0;
    const pace = (target / hours).toFixed(1);
    startPacePreview.textContent = `${pace} canais/h`;
  }

  // Confirmar Início de Sessão
  btnConfirmStart.addEventListener("click", async () => {
    const target = parseInt(startTargetInput.value, 10) || 160;
    const hours = selectedCycleHours || 8.0;

    btnConfirmStart.disabled = true;
    btnConfirmStart.textContent = "INICIANDO...";

    try {
      currentSession = await window.prospectorAPI.startWorkSession(target, hours, selectedCycleType);
      startModal.style.display = "none";
      renderSessionState();
      loadStats();
    } catch (err) {
      alert("Erro ao iniciar sessão: " + err.message);
    } finally {
      btnConfirmStart.disabled = false;
      btnConfirmStart.textContent = "COMEÇAR";
    }
  });

  // Pausar / Retomar Sessão
  btnPauseResume.addEventListener("click", async () => {
    if (!currentSession) return;
    btnPauseResume.disabled = true;

    try {
      if (currentSession.status === "ACTIVE") {
        currentSession = await window.prospectorAPI.pauseWorkSession();
      } else {
        currentSession = await window.prospectorAPI.resumeWorkSession();
      }
      renderSessionState();
    } catch (err) {
      alert("Erro ao pausar/retomar: " + err.message);
    } finally {
      btnPauseResume.disabled = false;
    }
  });

  // Modal Finalizar
  btnOpenFinishModal.addEventListener("click", () => {
    if (!currentSession) return;
    const sec = currentSession.current_active_seconds || currentSession.active_seconds;
    finishTimeSummary.textContent = formatSeconds(sec);
    finishCountSummary.textContent = `${currentSession.collected_count} canais`;
    finishModal.style.display = "flex";
  });

  btnCloseFinishModal.addEventListener("click", () => {
    finishModal.style.display = "none";
  });

  btnCancelFinish.addEventListener("click", () => {
    finishModal.style.display = "none";
  });

  btnConfirmFinish.addEventListener("click", async () => {
    btnConfirmFinish.disabled = true;
    btnConfirmFinish.textContent = "FINALIZANDO...";

    try {
      let activeSecs = currentSession ? (currentSession.current_active_seconds || currentSession.active_seconds || 0) : 0;
      const pendingChannels = await window.prospectorAPI.getPendingChannels();

      const finishPayload = {
        session_id: currentSession ? currentSession.id : null,
        active_seconds: activeSecs,
        ended_at: new Date().toISOString(),
        channels: pendingChannels
      };

      await window.prospectorAPI.finishWorkSession(finishPayload);
      finishModal.style.display = "none";
      currentSession = null;
      renderSessionState();
      loadStats();
    } catch (err) {
      alert("Erro ao finalizar sessão: " + err.message);
    } finally {
      btnConfirmFinish.disabled = false;
      btnConfirmFinish.textContent = "FINALIZAR";
    }
  });

  // --- ESTATÍSTICAS GERAIS & PÁGINA ---

  async function loadStats() {
    try {
      const [myStats, teamStats] = await Promise.all([
        window.prospectorAPI.getMyStats().catch(() => ({ today_count: 0 })),
        window.prospectorAPI.getTeamStats().catch(() => ({ today_count: 0 }))
      ]);

      userTodayCount.textContent = `${myStats.today_count} canais`;
      teamTodayCount.textContent = `${teamStats.today_count} canais`;
    } catch (err) {
      console.warn("Erro stats:", err);
    }
  }

  async function loadPageStats() {
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab || !tab.id || !tab.url || !tab.url.includes("youtube.com")) {
        pageFoundCount.textContent = "-";
        pageNewCount.textContent = "-";
        pageExistsCount.textContent = "-";
        btnBulkCollect.disabled = true;
        btnBulkCollect.textContent = "ABRA O YOUTUBE";
        return;
      }

      chrome.tabs.sendMessage(tab.id, { action: "GET_PAGE_STATS" }, (response) => {
        if (chrome.runtime.lastError || !response) {
          pageFoundCount.textContent = "0";
          pageNewCount.textContent = "0";
          pageExistsCount.textContent = "0";
          btnBulkCollect.disabled = true;
          return;
        }

        pageFoundCount.textContent = response.total;
        pageNewCount.textContent = response.newCount;
        pageExistsCount.textContent = response.existsCount;

        if (response.newCount > 0) {
          btnBulkCollect.disabled = false;
          btnBulkCollect.textContent = `⚡ COLETAR ${response.newCount} NOVOS`;
        } else {
          btnBulkCollect.disabled = true;
          btnBulkCollect.textContent = "NENHUM CANAL NOVO";
        }
      });
    } catch (e) {
      console.warn("Erro aba ativa:", e);
    }
  }

  // Coletar em Massa da Página
  btnBulkCollect.addEventListener("click", async () => {
    btnBulkCollect.disabled = true;
    btnBulkCollect.textContent = "COLETANDO...";

    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.id) {
      chrome.tabs.sendMessage(tab.id, { action: "COLLECT_ALL_NEW_PAGE" }, () => {
        setTimeout(() => {
          loadPageStats();
          loadStats();
          loadSessionData();
        }, 1000);
      });
    }
  });

  // Abrir Dashboard & Ranking
  btnOpenDashboard.addEventListener("click", () => {
    chrome.tabs.create({ url: dashboardUrl });
  });

  // Inicialização
  checkSystem();
});
