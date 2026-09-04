(function () {
  let lastSignature = "";
  let lastSentAt = 0;
  let media = null;
  let debounceTimer = null;

  const text = (selector, root = document) => root.querySelector(selector)?.textContent?.trim() || "";
  const image = (selector, root = document) => root.querySelector(selector)?.src || null;

  function readTrack() {
    media = document.querySelector("video, audio") || media;
    const youtubeMusic = location.hostname === "music.youtube.com";
    const spotify = location.hostname === "open.spotify.com";
    let title, artist, cover;
    if (spotify) {
      const root = document.querySelector('[data-testid="now-playing-widget"]');
      if (!root) return null;
      title = text('[data-testid="context-item-link"], [data-testid="nowplaying-track-link"]', root);
      artist = text('[data-testid="context-item-info-artist"], [data-testid="track-info-artists"]', root);
      cover = image('[data-testid="cover-art-image"]', root);
    } else if (youtubeMusic) {
      title = text("ytmusic-player-bar .title, yt-formatted-string.title.ytmusic-player-bar");
      artist = text("ytmusic-player-bar .byline, .byline.ytmusic-player-bar").split("•")[0].trim();
      cover = image("ytmusic-player-bar .thumbnail img, ytmusic-player-bar img.image");
    } else {
      title = text("h1.ytd-watch-metadata yt-formatted-string, h1.title");
      artist = text("#owner #channel-name a, ytd-channel-name a");
      cover = document.querySelector('meta[property="og:image"]')?.content || null;
    }
    if (!title || !media || !Number.isFinite(media.duration)) return null;
    return {
      provider: spotify ? "spotify" : (youtubeMusic ? "youtube_music" : "youtube"),
      track_id: spotify ? null : new URL(location.href).searchParams.get("v"),
      track_name: title, artist: artist || "--", album_art: cover,
      track_url: location.href, is_playing: !media.paused && !media.ended,
      position_ms: Math.round((media.currentTime || 0) * 1000),
      duration_ms: Math.round(media.duration * 1000)
    };
  }

  async function sync(force = false) {
    const track = readTrack();
    if (!track) return;
    const signature = JSON.stringify([track.provider, track.track_id, track.track_name, track.artist,
      track.is_playing, track.duration_ms, Math.round(track.position_ms / 5000)]);
    if (!force && signature === lastSignature && Date.now() - lastSentAt < 30000) return;
    try {
      await window.prospectorAPI?.updateMusicNowPlaying(track);
      lastSignature = signature;
      lastSentAt = Date.now();
    } catch (_) {}
  }

  function schedule(force = false) {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => sync(force), 250);
  }

  function bindMedia() {
    const found = document.querySelector("video, audio");
    if (!found || found === media) return;
    media = found;
    ["play", "pause", "seeking", "seeked", "durationchange", "loadedmetadata", "ended"]
      .forEach(event => media.addEventListener(event, () => schedule(true)));
    schedule(true);
  }

  new MutationObserver(() => { bindMedia(); schedule(); })
    .observe(document.documentElement, { childList: true, subtree: true });
  bindMedia();
})();
