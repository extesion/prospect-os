/**
 * YouTube Prospector - DOM Parser
 * Detecta e extrai metadados de canais em todas as visualizações do YouTube:
 * - Resultados de busca (canais e vídeos)
 * - Página de reprodução de vídeos (Owner / Uploader)
 * - Página principal do próprio canal
 * - Feeds, recomendações e vídeos relacionados
 */
class YouTubeParser {
  constructor() {
    this.channelIdRegex = /UC[a-zA-Z0-9_-]{22}/;
  }

  getCurrentSearchTerm() {
    try {
      const params = new URLSearchParams(window.location.search);
      return params.get("search_query") || "";
    } catch {
      return "";
    }
  }

  getCurrentSource() {
    const path = window.location.pathname;
    if (path.includes("/results")) return "youtube_search";
    if (path.includes("/watch")) return "youtube_watch";
    if (path.startsWith("/@") || path.startsWith("/channel/")) return "youtube_channel_page";
    return "youtube_feed";
  }

  /**
   * Extrai o channel_id de uma URL ou string
   */
  extractChannelIdFromHref(href) {
    if (!href) return null;
    const match = href.match(this.channelIdRegex);
    if (match) return match[0];
    return null;
  }

  /**
   * Extrai o handle (@handle) de uma URL
   */
  extractHandleFromHref(href) {
    if (!href) return null;
    const match = href.match(/@([a-zA-Z0-9_.-]+)/);
    if (match) return `@${match[1]}`;
    return null;
  }

  /**
   * Constrói URL canônica limpa
   */
  normalizeChannelUrl(href) {
    if (!href) return "";
    if (href.startsWith("http")) {
      const url = new URL(href);
      return `https://www.youtube.com${url.pathname}`;
    }
    const cleanPath = href.split("?")[0];
    return `https://www.youtube.com${cleanPath.startsWith("/") ? "" : "/"}${cleanPath}`;
  }

  /**
   * Analisa a página atual se estiver diretamente em um canal (ex: /@handle ou /channel/UC...)
   */
  parseCurrentChannelPage() {
    const path = window.location.pathname;
    if (!path.startsWith("/@") && !path.startsWith("/channel/")) {
      return null;
    }

    let channelId = null;
    const canonicalLink = document.querySelector('link[rel="canonical"]');
    if (canonicalLink && canonicalLink.href) {
      channelId = this.extractChannelIdFromHref(canonicalLink.href);
    }

    if (!channelId) {
      const metaItemProp = document.querySelector('meta[itemprop="channelId"]');
      if (metaItemProp) channelId = metaItemProp.content;
    }

    const handle = this.extractHandleFromHref(path) || (path.startsWith("/@") ? path.split("/")[1] : null);
    
    if (!channelId && handle) {
      channelId = `UC_HDL_${handle.replace("@", "").toLowerCase()}`;
    }

    if (!channelId) {
      return null;
    }

    const nameElem = document.querySelector("#channel-name #text, yt-page-header-renderer h1, .dynamic-text-view-model-wiz__h1");
    const channelName = nameElem ? nameElem.innerText.trim() : (handle || "Canal YouTube");

    return {
      channel_id: channelId,
      channel_name: channelName,
      channel_handle: handle,
      channel_url: this.normalizeChannelUrl(window.location.href),
      source: "youtube_channel_page",
      search_term: ""
    };
  }

  /**
   * Encontra todos os nós de canais no DOM atual
   */
  findChannelContainers(root = document) {
    const containers = [];

    // 1. Canais dedicados em resultados de pesquisa
    root.querySelectorAll("ytd-channel-renderer").forEach((el) => {
      containers.push({ element: el, type: "channel_renderer" });
    });

    // 2. Vídeos normais em pesquisa ou feed
    root.querySelectorAll("ytd-video-renderer, ytd-rich-item-renderer, ytd-grid-video-renderer, ytd-compact-video-renderer").forEach((el) => {
      if (el.querySelector("ytd-ad-slot-renderer")) return;
      containers.push({ element: el, type: "video_renderer" });
    });

    // 3. Seção do Dono do Vídeo na página de reprodução (/watch)
    const videoOwner = root.querySelector("ytd-watch-metadata #owner, #owner.ytd-watch-flexy, ytd-video-owner-renderer");
    if (videoOwner) {
      containers.push({ element: videoOwner, type: "video_owner" });
    }

    // 4. Header de página de canal
    const channelHeader = root.querySelector("ytd-c4-tabbed-header-renderer, yt-page-header-renderer, #channel-header");
    if (channelHeader) {
      containers.push({ element: channelHeader, type: "channel_header" });
    }

    return containers;
  }

  /**
   * Extrai dados de um elemento de canal identificado
   */
  extractDataFromContainer(containerObj) {
    const { element, type } = containerObj;

    let linkElem = null;
    let nameElem = null;

    if (type === "channel_renderer") {
      linkElem = element.querySelector("a#main-link, a.ytd-channel-renderer, #avatar-section a");
      nameElem = element.querySelector("#channel-title #text, #text.ytd-channel-name");
    } else if (type === "video_renderer") {
      linkElem = element.querySelector("#channel-name a, .ytd-channel-name a, ytd-channel-name a, #byline a, #channel-thumbnail");
      nameElem = element.querySelector("#channel-name #text, .ytd-channel-name #text, ytd-channel-name #text");
    } else if (type === "video_owner") {
      linkElem = element.querySelector("ytd-channel-name a, #channel-name a, a.yt-simple-endpoint");
      nameElem = element.querySelector("#channel-name #text, ytd-channel-name #text, #upload-info #text");
    } else if (type === "channel_header") {
      linkElem = element.querySelector("#channel-name a, a.yt-page-header-renderer__link") || { href: window.location.href };
      nameElem = element.querySelector("#channel-name #text, h1.dynamic-text-view-model-wiz__h1, #text.ytd-channel-name");
    }

    if (!linkElem || !linkElem.href) {
      return null;
    }

    const href = linkElem.href;
    let channelId = this.extractChannelIdFromHref(href);
    const handle = this.extractHandleFromHref(href);

    if (!channelId && handle) {
      channelId = `UC_HDL_${handle.replace("@", "").toLowerCase()}`;
    }

    if (!channelId) {
      return null;
    }

    const channelName = (nameElem && nameElem.innerText ? nameElem.innerText.trim() : "") || handle || "Canal YouTube";
    const channelUrl = this.normalizeChannelUrl(href);

    return {
      element,
      type,
      data: {
        channel_id: channelId,
        channel_name: channelName,
        channel_handle: handle,
        channel_url: channelUrl,
        source: this.getCurrentSource(),
        search_term: this.getCurrentSearchTerm()
      }
    };
  }
}

window.youtubeParser = new YouTubeParser();
