/**
 * YouTube Prospector - Content Script
 * Orquestra a detecção de canais, verificação em lote via API Central,
 * injeção de badges visuais, tratamento de concorrência e coleta em massa.
 */

(function () {
  // Evita injeção duplicada
  if (window.__ypProspectorLoaded) return;
  window.__ypProspectorLoaded = true;

  console.log("[YouTube Prospector] Content script inicializado.");

  // Estado da página
  const pageState = {
    detectedChannels: new Map(), // channelId -> Array of { element, data, badgeElement }
    isScanning: false,
    debounceTimer: null,
    toolbarElement: null,
    authenticated: false,
    currentUser: null
  };

  /**
   * Formata data para o padrão visual amigável brasileiro
   */
  function formatDate(isoString) {
    if (!isoString) return "";
    try {
      const date = new Date(isoString);
      const day = String(date.getDate()).padStart(2, "0");
      const month = String(date.getMonth() + 1).padStart(2, "0");
      const year = date.getFullYear();
      const hours = String(date.getHours()).padStart(2, "0");
      const minutes = String(date.getMinutes()).padStart(2, "0");
      return `${day}/${month}/${year} ${hours}:${minutes}`;
    } catch {
      return isoString;
    }
  }

  /**
   * Atualiza ou injeta o badge visual dentro do elemento do canal
   */
  function renderBadge(containerObj, statusData) {
    const { element, data } = containerObj;
    if (!element || !element.isConnected) return;

    // Procura local ideal para inserção
    let targetMount = element.querySelector(
      "#channel-name, .ytd-channel-name, ytd-channel-name, #title-wrapper, #channel-title, #upload-info, #owner-sub-count, yt-page-header-renderer h1"
    );

    if (!targetMount) {
      targetMount = element;
    }

    let badge = element.querySelector(`.yp-badge-container[data-channel-id="${data.channel_id}"]`);
    if (!badge) {
      badge = document.createElement("div");
      badge.className = "yp-badge-container";
      badge.setAttribute("data-channel-id", data.channel_id);
      targetMount.appendChild(badge);
    }

    containerObj.badgeElement = badge;

    // Renderiza o estado correspondente
    if (statusData.state === "VERIFYING") {
      badge.innerHTML = `
        <span class="yp-status-pill yp-verifying">
          ○ Verificando...
        </span>
      `;
    } else if (statusData.state === "AVAILABLE") {
      badge.innerHTML = `
        <span class="yp-status-pill yp-available">
          🟢 Não coletado
        </span>
        <button class="yp-btn-collect" title="Coletar este canal para o banco central">
          + COLETAR
        </button>
      `;

      const btn = badge.querySelector(".yp-btn-collect");
      if (btn) {
        btn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          handleCollectChannel(data.channel_id);
        });
      }
    } else if (statusData.state === "EXISTS") {
      const collectorName = statusData.collected_by?.name || "Outro usuário";
      const formattedTime = formatDate(statusData.collected_at);

      badge.innerHTML = `
        <span class="yp-status-pill yp-exists">
          ✓ Já coletado
          <div class="yp-tooltip">
            <strong>Já coletado</strong><br/>
            Por: ${collectorName}<br/>
            Data: ${formattedTime}
          </div>
        </span>
      `;
    } else if (statusData.state === "SAVING") {
      badge.innerHTML = `
        <span class="yp-status-pill yp-saving">
          ⏳ Salvando...
        </span>
      `;
    } else if (statusData.state === "COLLECTED_NOW") {
      badge.innerHTML = `
        <span class="yp-status-pill yp-available" style="border-color: rgba(46,204,113,0.8);">
          ✓ Coletado por você
        </span>
      `;
    } else if (statusData.state === "ERROR") {
      badge.innerHTML = `
        <span class="yp-status-pill yp-error">
          ⚠ Erro
        </span>
        <button class="yp-btn-retry">Tentar</button>
      `;
      const btn = badge.querySelector(".yp-btn-retry");
      if (btn) {
        btn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          handleCollectChannel(data.channel_id);
        });
      }
    }
  }

  /**
   * Atualiza visualmente todas as ocorrências de um canal na página
   */
  function updateAllBadgesForChannel(channelId, statusData) {
    const list = pageState.detectedChannels.get(channelId) || [];
    list.forEach((item) => renderBadge(item, statusData));
    updateToolbar();
  }

  /**
   * Executa a coleta individual de um canal
   */
  async function handleCollectChannel(channelId) {
    const list = pageState.detectedChannels.get(channelId);
    if (!list || list.length === 0) return;

    const sample = list[0].data;

    // Atualiza para SAVING
    updateAllBadgesForChannel(channelId, { state: "SAVING" });

    try {
      const response = await window.prospectorAPI.collectChannel(sample);

      if (response.success) {
        // Coleta bem sucedida
        const nowIso = new Date().toISOString();
        window.prospectorCache.set(channelId, {
          exists: true,
          collected_by: { id: response.channel?.first_collected_by?.id, name: "Você" },
          collected_at: nowIso
        });

        updateAllBadgesForChannel(channelId, {
          state: "COLLECTED_NOW",
          collected_by: { name: "Você" },
          collected_at: nowIso
        });
      } else if (response.already_exists) {
        // Concorrência: outro usuário acabou de cadastrar
        const collectorName = response.channel?.first_collected_by?.name || "Outro usuário";
        const collectedAt = response.channel?.first_collected_at || new Date().toISOString();

        window.prospectorCache.set(channelId, {
          exists: true,
          collected_by: { name: collectorName },
          collected_at: collectedAt
        });

        updateAllBadgesForChannel(channelId, {
          state: "EXISTS",
          collected_by: { name: collectorName },
          collected_at: collectedAt
        });
      }
    } catch (err) {
      console.error("[YouTube Prospector] Erro ao coletar canal:", err);
      updateAllBadgesForChannel(channelId, { state: "ERROR" });
    }
  }

  /**
   * Coleta em massa todos os canais novos disponíveis na página
   */
  async function handleCollectAllNew() {
    const newChannels = [];
    for (const [channelId, list] of pageState.detectedChannels.entries()) {
      const cached = window.prospectorCache.get(channelId);
      if (cached && !cached.exists) {
        if (list.length > 0) {
          newChannels.push(list[0].data);
        }
      }
    }

    if (newChannels.length === 0) {
      alert("Nenhum canal novo disponível para coleta nesta página.");
      return;
    }

    // Marca todos como Salvando...
    newChannels.forEach((ch) => {
      updateAllBadgesForChannel(ch.channel_id, { state: "SAVING" });
    });

    try {
      const response = await window.prospectorAPI.collectBulk(newChannels);
      const nowIso = new Date().toISOString();

      // Atualiza inseridos
      if (response.inserted) {
        response.inserted.forEach((cid) => {
          window.prospectorCache.set(cid, {
            exists: true,
            collected_by: { name: "Você" },
            collected_at: nowIso
          });
          updateAllBadgesForChannel(cid, {
            state: "COLLECTED_NOW",
            collected_by: { name: "Você" },
            collected_at: nowIso
          });
        });
      }

      // Atualiza já existentes
      if (response.already_exists) {
        response.already_exists.forEach((cid) => {
          window.prospectorCache.set(cid, {
            exists: true,
            collected_by: { name: "Outro membro" },
            collected_at: nowIso
          });
          updateAllBadgesForChannel(cid, {
            state: "EXISTS",
            collected_by: { name: "Outro membro" },
            collected_at: nowIso
          });
        });
      }
    } catch (err) {
      console.error("[YouTube Prospector] Erro no bulk insert:", err);
      newChannels.forEach((ch) => {
        updateAllBadgesForChannel(ch.channel_id, { state: "ERROR" });
      });
    }
  }

  /**
   * Realiza a varredura dos canais no DOM e consulta a API Central em lote
   */
  async function scanPageChannels() {
    if (pageState.isScanning) return;
    pageState.isScanning = true;

    try {
      const containers = window.youtubeParser.findChannelContainers(document);
      const toCheckIds = new Set();

      for (const c of containers) {
        const parsed = window.youtubeParser.extractDataFromContainer(c);
        if (!parsed) continue;

        const cid = parsed.data.channel_id;
        if (!pageState.detectedChannels.has(cid)) {
          pageState.detectedChannels.set(cid, []);
        }

        const existingList = pageState.detectedChannels.get(cid);
        const alreadyTracked = existingList.some((item) => item.element === parsed.element);
        if (!alreadyTracked) {
          existingList.push(parsed);
        }

        // Verifica se já está no cache
        const cached = window.prospectorCache.get(cid);
        if (cached) {
          renderBadge(parsed, {
            state: cached.exists ? "EXISTS" : "AVAILABLE",
            collected_by: cached.collected_by,
            collected_at: cached.collected_at
          });
        } else {
          // Marca como verificando e enfileira para consulta em lote
          renderBadge(parsed, { state: "VERIFYING" });
          toCheckIds.add(cid);
        }
      }

      // Consulta em lote os IDs não cacheados
      if (toCheckIds.size > 0) {
        const idsArray = Array.from(toCheckIds);
        try {
          const res = await window.prospectorAPI.checkChannels(idsArray);
          const channelMap = res.channels || {};

          for (const cid of idsArray) {
            const status = channelMap[cid] || { exists: false };
            window.prospectorCache.set(cid, status);

            updateAllBadgesForChannel(cid, {
              state: status.exists ? "EXISTS" : "AVAILABLE",
              collected_by: status.collected_by,
              collected_at: status.collected_at
            });
          }
        } catch (apiErr) {
          console.warn("[YouTube Prospector] Falha ao consultar lote na API:", apiErr.message);
          // Em caso de erro de conexão, mantém estado de erro
          for (const cid of idsArray) {
            updateAllBadgesForChannel(cid, { state: "ERROR" });
          }
        }
      }

      updateToolbar();
    } finally {
      pageState.isScanning = false;
    }
  }

  /**
   * Debounce para o MutationObserver
   */
  function scheduleScan() {
    clearTimeout(pageState.debounceTimer);
    pageState.debounceTimer = setTimeout(() => {
      scanPageChannels();
    }, 150);
  }

  /**
   * Atualiza a barra flutuante com as métricas da página atual
   */
  function updateToolbar() {
    let total = pageState.detectedChannels.size;
    let newCount = 0;
    let existsCount = 0;

    for (const [cid] of pageState.detectedChannels.entries()) {
      const cached = window.prospectorCache.get(cid);
      if (cached) {
        if (cached.exists) existsCount++;
        else newCount++;
      }
    }

    if (total === 0) {
      if (pageState.toolbarElement) {
        pageState.toolbarElement.style.display = "none";
      }
      return;
    }

    if (!pageState.toolbarElement) {
      const tb = document.createElement("div");
      tb.className = "yp-floating-toolbar";
      document.body.appendChild(tb);
      pageState.toolbarElement = tb;
    }

    pageState.toolbarElement.style.display = "flex";
    pageState.toolbarElement.innerHTML = `
      <div class="yp-toolbar-brand">
        <span>⚡ PROSPECT OS</span>
      </div>
      <div class="yp-toolbar-stats">
        <div class="yp-stat-item">Total: <strong>${total}</strong></div>
        <div class="yp-stat-item yp-stat-new">Novos: <strong>${newCount}</strong></div>
        <div class="yp-stat-item yp-stat-exists">Já coletados: <strong>${existsCount}</strong></div>
      </div>
      <button class="yp-toolbar-bulk-btn" ${newCount === 0 ? "disabled" : ""}>
        ⚡ Coletar ${newCount} Novos
      </button>
    `;

    const bulkBtn = pageState.toolbarElement.querySelector(".yp-toolbar-bulk-btn");
    if (bulkBtn && newCount > 0) {
      bulkBtn.addEventListener("click", () => {
        handleCollectAllNew();
      });
    }
  }

  /**
   * Limpa o estado ao navegar entre páginas no YouTube SPA
   */
  function handlePageNavigation() {
    pageState.detectedChannels.clear();
    if (pageState.toolbarElement) {
      pageState.toolbarElement.style.display = "none";
    }
    scheduleScan();
  }

  /**
   * Inicialização principal
   */
  async function init() {
    // Escuta navegações SPA do YouTube
    window.addEventListener("yt-navigate-finish", handlePageNavigation);
    window.addEventListener("yt-page-data-updated", scheduleScan);
    window.addEventListener("popstate", handlePageNavigation);

    // Observer para scroll infinito e carregamento assíncrono
    const observer = new MutationObserver((mutations) => {
      let shouldScan = false;
      for (const m of mutations) {
        if (m.addedNodes && m.addedNodes.length > 0) {
          shouldScan = true;
          break;
        }
      }
      if (shouldScan) {
        scheduleScan();
      }
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true
    });

    // Comunicação com o Popup
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
      if (request.action === "GET_PAGE_STATS") {
        let total = pageState.detectedChannels.size;
        let newCount = 0;
        let existsCount = 0;

        for (const [cid] of pageState.detectedChannels.entries()) {
          const cached = window.prospectorCache.get(cid);
          if (cached) {
            if (cached.exists) existsCount++;
            else newCount++;
          }
        }

        sendResponse({
          total,
          newCount,
          existsCount
        });
      } else if (request.action === "COLLECT_ALL_NEW_PAGE" || request.action === "TRIGGER_COLLECT_ALL_NEW") {
        handleCollectAllNew().then(() => {
          sendResponse({ success: true });
        });
        return true; // async
      }
    });

    // Primeira varredura
    scheduleScan();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
