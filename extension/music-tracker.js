/**
 * YouTube Music & Web Spotify Player Tracker
 * Captura em tempo real os metadados das abas do YouTube Music e Web Player do Spotify
 * e despacha automaticamente para a API Central do PROSPECT OS.
 */

(function () {
  let lastTrackPayload = null;
  let syncInterval = null;

  function isYouTubeMusic() {
    return window.location.hostname.includes("music.youtube.com");
  }

  function isSpotifyWeb() {
    return window.location.hostname.includes("open.spotify.com");
  }

  function getYouTubeMusicInfo() {
    try {
      // Elements in YouTube Music player bar
      const titleEl = document.querySelector("ytmusic-player-bar .title, .ytmusic-player-bar.title, yt-formatted-string.title.ytmusic-player-bar");
      const bylineEl = document.querySelector("ytmusic-player-bar .byline, .ytmusic-player-bar.byline, .byline.ytmusic-player-bar");
      const thumbEl = document.querySelector("ytmusic-player-bar .thumbnail img, ytmusic-player-bar img.image");
      const playPauseBtn = document.querySelector("#play-pause-button, ytmusic-player-bar #play-pause-button");

      const title = titleEl ? titleEl.textContent.trim() : null;
      let artist = bylineEl ? bylineEl.textContent.trim() : null;
      // Clean up metadata strings (e.g. "Artist • Album • 2024")
      if (artist && artist.includes("•")) {
        artist = artist.split("•")[0].trim();
      }
      const albumArt = thumbEl ? (thumbEl.src || null) : null;
      
      // Determine if playing
      let isPlaying = false;
      if (playPauseBtn) {
        const titleAttr = (playPauseBtn.getAttribute("title") || "").toLowerCase();
        const ariaLabel = (playPauseBtn.getAttribute("aria-label") || "").toLowerCase();
        isPlaying = titleAttr.includes("paus") || ariaLabel.includes("paus");
      }

      if (!title) return null;

      return {
        provider: "youtube_music",
        track_name: title,
        artist: artist || "YouTube Music",
        album_art: albumArt,
        is_playing: isPlaying,
        track_url: window.location.href
      };
    } catch (e) {
      return null;
    }
  }

  function getSpotifyWebInfo() {
    try {
      const nowPlayingWidget = document.querySelector('[data-testid="now-playing-widget"]');
      if (!nowPlayingWidget) return null;

      const titleEl = nowPlayingWidget.querySelector('[data-testid="context-item-link"], [data-testid="nowplaying-track-link"]');
      const artistEl = nowPlayingWidget.querySelector('[data-testid="context-item-info-artist"], [data-testid="track-info-artists"]');
      const coverEl = nowPlayingWidget.querySelector('[data-testid="cover-art-image"]');
      const playBtn = document.querySelector('[data-testid="control-button-playpause"]');

      const title = titleEl ? titleEl.textContent.trim() : null;
      const artist = artistEl ? artistEl.textContent.trim() : null;
      const albumArt = coverEl ? coverEl.src : null;

      let isPlaying = false;
      if (playBtn) {
        const ariaLabel = (playBtn.getAttribute("aria-label") || "").toLowerCase();
        isPlaying = ariaLabel.includes("paus");
      }

      if (!title) return null;

      return {
        provider: "spotify",
        track_name: title,
        artist: artist || "Spotify",
        album_art: albumArt,
        is_playing: isPlaying,
        track_url: window.location.href
      };
    } catch (e) {
      return null;
    }
  }

  async function checkAndSyncMusic() {
    let track = null;
    if (isYouTubeMusic()) {
      track = getYouTubeMusicInfo();
    } else if (isSpotifyWeb()) {
      track = getSpotifyWebInfo();
    }

    if (!track || !track.track_name || !track.is_playing) {
      return;
    }

    // Check if changed
    const payloadStr = JSON.stringify({
      t: track.track_name,
      a: track.artist,
      p: track.provider,
      pl: track.is_playing
    });

    if (payloadStr === lastTrackPayload) {
      return;
    }

    lastTrackPayload = payloadStr;

    try {
      if (window.prospectorAPI) {
        await window.prospectorAPI.updateMusicNowPlaying(track);
      }
    } catch (e) {
      // Ignora erro de rede silenciosamente
    }
  }

  // Inicia observador e timer de 3 segundos
  clearInterval(syncInterval);
  syncInterval = setInterval(checkAndSyncMusic, 3000);
  setTimeout(checkAndSyncMusic, 1500);

})();
