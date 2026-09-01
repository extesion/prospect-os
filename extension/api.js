/**
 * YouTube Prospector - API Client
 * Responsável por toda a comunicação com a API Central FastAPI.
 */
class ProspectorAPI {
  constructor() {
    this.defaultBaseUrl = "https://prospect-os-seven.vercel.app/api";
  }

  async getBaseUrl() {
    return new Promise((resolve) => {
      chrome.storage.local.get(["apiUrl"], (result) => {
        let url = result.apiUrl || this.defaultBaseUrl;
        // Auto-migrate legacy localhost URLs to production Vercel
        if (!url || url.includes("localhost:8000")) {
          url = this.defaultBaseUrl;
          chrome.storage.local.set({ apiUrl: url });
        }
        // Strip trailing slash
        if (url.endsWith("/")) url = url.slice(0, -1);
        // Ensure /api path if not present
        if (!url.endsWith("/api")) {
          url = url + "/api";
        }
        resolve(url);
      });
    });
  }

  async getToken() {
    return new Promise((resolve) => {
      chrome.storage.local.get(["authToken"], (result) => {
        resolve(result.authToken || null);
      });
    });
  }

  async setAuth(token, user) {
    return new Promise((resolve) => {
      chrome.storage.local.set({ authToken: token, currentUser: user }, () => {
        resolve();
      });
    });
  }

  async clearAuth() {
    return new Promise((resolve) => {
      chrome.storage.local.remove(["authToken", "currentUser"], () => {
        resolve();
      });
    });
  }

  async request(endpoint, options = {}) {
    const baseUrl = await this.getBaseUrl();
    const token = await this.getToken();

    const headers = {
      "Content-Type": "application/json",
      ...(options.headers || {})
    };

    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const url = `${baseUrl}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;

    try {
      const response = await fetch(url, {
        ...options,
        headers
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        if (response.status === 401) {
          // Token expired or invalid
          chrome.runtime.sendMessage({ action: "AUTH_EXPIRED" });
        }
        const error = new Error(data.detail || `Erro na requisição (${response.status})`);
        error.status = response.status;
        error.data = data;
        throw error;
      }

      return data;
    } catch (err) {
      if (err.name === "TypeError" && err.message.includes("fetch")) {
        const netErr = new Error("Não foi possível conectar ao servidor.");
        netErr.status = 0;
        throw netErr;
      }
      throw err;
    }
  }

  async checkHealth() {
    const baseUrl = await this.getBaseUrl();
    try {
      // Health is at /health or /api/health
      const healthUrl = baseUrl.replace(/\/api$/, "") + "/health";
      const res = await fetch(healthUrl, { method: "GET" });
      if (!res.ok) return { status: "offline" };
      return await res.json();
    } catch (e) {
      return { status: "offline", error: e.message };
    }
  }

  async login(email, password) {
    const data = await this.request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password })
    });
    if (data.access_token) {
      await this.setAuth(data.access_token, data.user);
    }
    return data;
  }

  async getMe() {
    return await this.request("/auth/me", { method: "GET" });
  }

  async checkChannels(channelIds) {
    if (!channelIds || channelIds.length === 0) return { channels: {} };
    return await this.request("/channels/check", {
      method: "POST",
      body: JSON.stringify({ channel_ids: channelIds })
    });
  }

  async collectChannel(channelData) {
    return await this.request("/channels", {
      method: "POST",
      body: JSON.stringify(channelData)
    });
  }

  async collectBulk(channelsList) {
    return await this.request("/channels/bulk", {
      method: "POST",
      body: JSON.stringify({ channels: channelsList })
    });
  }

  async getMyStats() {
    return await this.request("/stats/me", { method: "GET" });
  }

  async getTeamStats() {
    return await this.request("/stats/team", { method: "GET" });
  }

  // Work Sessions & Productivity
  async startWorkSession(dailyTarget, targetHours, cycleType) {
    return await this.request("/work-sessions/start", {
      method: "POST",
      body: JSON.stringify({
        daily_target: dailyTarget,
        target_hours: targetHours,
        cycle_type: cycleType
      })
    });
  }

  async pauseWorkSession() {
    return await this.request("/work-sessions/pause", { method: "POST" });
  }

  async resumeWorkSession() {
    return await this.request("/work-sessions/resume", { method: "POST" });
  }

  async finishWorkSession() {
    return await this.request("/work-sessions/finish", { method: "POST" });
  }

  async getCurrentWorkSession() {
    return await this.request("/work-sessions/current", { method: "GET" });
  }

  async getWorkSessionSettings() {
    return await this.request("/work-sessions/settings", { method: "GET" });
  }
}

window.prospectorAPI = new ProspectorAPI();

