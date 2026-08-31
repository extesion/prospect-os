/**
 * YouTube Prospector - Service Worker (Background)
 */

chrome.runtime.onInstalled.addListener(() => {
  console.log("[YouTube Prospector] Extensão instalada com sucesso.");
  
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
    // Limpa credenciais locais
    chrome.storage.local.remove(["authToken", "currentUser"]);
  }
});
