/**
 * YouTube Prospector - Auth Manager
 */
class ProspectorAuth {
  constructor() {
    this.currentUser = null;
    this.token = null;
  }

  async init() {
    return new Promise((resolve) => {
      chrome.storage.local.get(["authToken", "currentUser"], (result) => {
        this.token = result.authToken || null;
        this.currentUser = result.currentUser || null;
        resolve({ token: this.token, user: this.currentUser });
      });
    });
  }

  isAuthenticated() {
    return Boolean(this.token);
  }

  getUser() {
    return this.currentUser;
  }

  async logout() {
    await window.prospectorAPI.clearAuth();
    this.currentUser = null;
    this.token = null;
  }
}

window.prospectorAuth = new ProspectorAuth();
