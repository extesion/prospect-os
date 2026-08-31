/**
 * YouTube Prospector - Service Worker (Background)
 * Configura Side Panel prioritário e gerencia eventos de ciclo de vida.
 */

chrome.runtime.onInstalled.addListener(() => {
  console.log("[YouTube Prospector] Extensão instalada com sucesso.");
  
  // Configura Side Panel para abrir ao clicar no ícone da extensão
  if (chrome.sidePanel && chrome.sidePanel.setPanelBehavior) {
    chrome.sidePanel
      .setPanelBehavior({ openPanelOnActionClick: true })
      .catch((error) => console.error("[SidePanel] Erro ao definir comportamento:", error));
  }

  // Define URL padrão se ainda não existir
  chrome.storage.local.get(["apiUrl"], (result) => {
    if (!result.apiUrl) {
      chrome.storage.local.set({ apiUrl: "http://localhost:8000/api" });
    }
  });
});

// Listener para mensagens de controle
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "AUTH_EXPIRED") {
    chrome.storage.local.remove(["authToken", "currentUser"]);
  }
});
