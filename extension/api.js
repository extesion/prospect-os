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

  async logout() {
    return await this.clearAuth();
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
        // Log status and sanitized detail for debugging
        console.warn(`[ProspectorAPI] ${response.status} ${endpoint}`, {
          body: options.body ? JSON.parse(options.body) : null,
          detail: data.detail
        });
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
    const token = await this.getToken();
    if (!token) return null;
    return await this.request("/auth/me", { method: "GET" });
  }

  async heartbeat() {
    const token = await this.getToken();
    if (!token) return null;
    return await this.request("/auth/heartbeat", { method: "POST" });
  }

  // --- LOCAL-FIRST STORAGE HELPERS ---

  async getLocalSession() {
    return new Promise((resolve) => {
      chrome.storage.local.get(["currentSession"], (result) => {
        resolve(result.currentSession || null);
      });
    });
  }

  async setLocalSession(sessionData) {
    return new Promise((resolve) => {
      chrome.storage.local.set({ currentSession: sessionData }, () => {
        resolve(sessionData);
      });
    });
  }

  async clearLocalSession() {
    return new Promise((resolve) => {
      chrome.storage.local.remove(["currentSession"], () => {
        resolve();
      });
    });
  }

  async getPendingChannels() {
    return new Promise((resolve) => {
      chrome.storage.local.get(["pendingChannels"], (result) => {
        resolve(Array.isArray(result.pendingChannels) ? result.pendingChannels : []);
      });
    });
  }

  async addPendingChannel(channelData) {
    if (!channelData || !channelData.channel_id) {
      throw new Error("Dados do canal inválidos.");
    }

    const cid = channelData.channel_id.trim();
    const list = await this.getPendingChannels();
    const alreadyInQueue = list.some((ch) => ch.channel_id === cid);

    if (!alreadyInQueue) {
      const entry = {
        ...channelData,
        channel_id: cid,
        collected_at: new Date().toISOString()
      };
      list.push(entry);
      await new Promise((resolve) => {
        chrome.storage.local.set({ pendingChannels: list }, resolve);
      });

      // Update local session collected count if active session exists
      const session = await this.getLocalSession();
      if (session && session.status === "ACTIVE") {
        session.collected_count = (session.collected_count || 0) + 1;
        await this.setLocalSession(session);
      }
    }

    return { success: true, alreadyInQueue, totalPending: list.length };
  }

  async addPendingBulk(channelsList) {
    if (!Array.isArray(channelsList) || channelsList.length === 0) {
      return { insertedCount: 0, totalPending: 0 };
    }

    const list = await this.getPendingChannels();
    const existingIds = new Set(list.map((ch) => ch.channel_id));
    let newlyAdded = 0;

    for (const item of channelsList) {
      const cid = item.channel_id ? item.channel_id.trim() : "";
      if (cid && !existingIds.has(cid)) {
        existingIds.add(cid);
        list.push({
          ...item,
          channel_id: cid,
          collected_at: new Date().toISOString()
        });
        newlyAdded++;
      }
    }

    await new Promise((resolve) => {
      chrome.storage.local.set({ pendingChannels: list }, resolve);
    });

    if (newlyAdded > 0) {
      const session = await this.getLocalSession();
      if (session && session.status === "ACTIVE") {
        session.collected_count = (session.collected_count || 0) + newlyAdded;
        await this.setLocalSession(session);
      }
    }

    return { insertedCount: newlyAdded, totalPending: list.length };
  }

  async clearPendingChannels() {
    return new Promise((resolve) => {
      chrome.storage.local.set({ pendingChannels: [] }, () => {
        resolve();
      });
    });
  }

  async checkChannels(channelIds) {
    if (!channelIds || channelIds.length === 0) return { channels: {} };
    return await this.request("/channels/check", {
      method: "POST",
      body: JSON.stringify({ channel_ids: channelIds })
    });
  }

  async requireActiveWorkSession() {
    const session = await this.getLocalSession();
    if (!session || session.status !== "ACTIVE") {
      throw new Error("Inicie seu turno de trabalho para coletar canais.");
    }
  }

  async collectChannel(channelData) {
    await this.requireActiveWorkSession();
    return await this.request("/channels", {
      method: "POST",
      body: JSON.stringify(channelData)
    });
  }

  async collectBulk(channelsList) {
    await this.requireActiveWorkSession();
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
  async startWorkSession(dailyTargetOrObj = 160, targetHours = 8.0, cycleType = "8H") {
    let dailyTarget = 160;
    let hours = 8.0;
    let cycle = "8H";

    if (typeof dailyTargetOrObj === "object" && dailyTargetOrObj !== null) {
      dailyTarget = dailyTargetOrObj.daily_target || 160;
      hours = dailyTargetOrObj.target_hours || (dailyTargetOrObj.cycle_type === "6H" ? 6.0 : 8.0);
      cycle = dailyTargetOrObj.cycle_type || "8H";
    } else {
      dailyTarget = typeof dailyTargetOrObj === "number" ? dailyTargetOrObj : 160;
      hours = typeof targetHours === "number" ? targetHours : 8.0;
      cycle = cycleType || "8H";
    }

    const session = await this.request("/work-sessions/start", {
      method: "POST",
      body: JSON.stringify({
        daily_target: dailyTarget,
        target_hours: hours,
        cycle_type: cycle
      })
    });

    await this.setLocalSession(session);
    await this.clearPendingChannels();
    return session;
  }

  async startSession(dailyTargetOrObj, targetHours, cycleType) {
    return await this.startWorkSession(dailyTargetOrObj, targetHours, cycleType);
  }

  async pauseWorkSession() {
    const session = await this.request("/work-sessions/pause", { method: "POST" });
    await this.setLocalSession(session);
    return session;
  }

  async pauseSession() {
    return await this.pauseWorkSession();
  }

  async resumeWorkSession() {
    const session = await this.request("/work-sessions/resume", { method: "POST" });
    await this.setLocalSession(session);
    return session;
  }

  async resumeSession() {
    return await this.resumeWorkSession();
  }

  async finishWorkSession(finishData = null) {
    const body = finishData ? JSON.stringify(finishData) : "{}";
    const session = await this.request("/work-sessions/finish", {
      method: "POST",
      body
    });
    await this.clearPendingChannels();
    await this.clearLocalSession();
    return session;
  }

  async finishSession(finishData = null) {
    return await this.finishWorkSession(finishData);
  }

  async getCurrentWorkSession() {
    try {
      const session = await this.request("/work-sessions/current", { method: "GET" });
      if (session) {
        await this.setLocalSession(session);
      } else {
        await this.clearLocalSession();
      }
      return session;
    } catch (err) {
      // Fallback to local session on network failure
      return await this.getLocalSession();
    }
  }

  async getCurrentSession() {
    return await this.getCurrentWorkSession();
  }

  async getWorkSessionSettings() {
    return await this.request("/work-sessions/settings", { method: "GET" });
  }

  async getMyProfile() {
    return await this.request("/profiles/me", { method: "GET" });
  }

  async getMemberProfile(userId) {
    return await this.request(`/profiles/${userId}`, { method: "GET" });
  }

  async getMusicStatus() {
    return await this.request("/music/status", { method: "GET" });
  }

  async updateMusicNowPlaying(data) {
    return await this.request("/music/now-playing", {
      method: "POST",
      body: JSON.stringify(data)
    });
  }
}

window.prospectorAPI = new ProspectorAPI();
