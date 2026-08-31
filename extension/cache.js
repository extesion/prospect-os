/**
 * YouTube Prospector - Cache Local Temporário (TTL)
 * Mantém um cache rápido de curta duração para evitar requisições repetidas
 * na mesma sessão/página.
 */
class ProspectorCache {
  constructor(ttlMs = 5 * 60 * 1000) { // 5 minutos por padrão
    this.ttlMs = ttlMs;
    this.cache = new Map();
  }

  set(channelId, data) {
    if (!channelId) return;
    this.cache.set(channelId, {
      data,
      expiresAt: Date.now() + this.ttlMs
    });
  }

  get(channelId) {
    if (!channelId || !this.cache.has(channelId)) return null;
    const entry = this.cache.get(channelId);
    if (Date.now() > entry.expiresAt) {
      this.cache.delete(channelId);
      return null;
    }
    return entry.data;
  }

  has(channelId) {
    return this.get(channelId) !== null;
  }

  updateIfExists(channelId, updateFn) {
    const current = this.get(channelId);
    if (current) {
      const updated = updateFn(current);
      this.set(channelId, updated);
    }
  }

  clear() {
    this.cache.clear();
  }
}

// Global cache instance attached to window/global scope
window.prospectorCache = new ProspectorCache();
