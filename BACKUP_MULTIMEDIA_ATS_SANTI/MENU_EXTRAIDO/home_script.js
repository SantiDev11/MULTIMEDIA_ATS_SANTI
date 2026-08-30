var pendingUrl = null;
var pendingName = null;

// ---- Clave de Licencia Universal Offline ----
var UNIVERSAL_LICENSE_KEY = 'MMATS-SANTI-2026-UNIVERSAL';

function isUniversalKey(k) {
  if (!k) return false;
  return String(k).trim().toUpperCase() === UNIVERSAL_LICENSE_KEY;
}

function getUniversalLicensePayload() {
  return {
    status: 'ok',
    statusText: 'Licencia activa',
    edition: 'Universal Permanente',
    days: -1,
    masked: 'MMATS-****-****-VERSAL',
    hwid: 'UNIVERSAL-OFFLINE',
    themes: true,
    entitlements: {
      enforced: false,
      partner: true,
      themes: true,
      spotify: true,
      youtube: true,
      twitch: true,
      chat: true,
      netflix: true
    }
  };
}

// Loading: overlay con spinner mostrado inmediatamente al abrir una app o navegar
function showLoad() {
  if (document.getElementById('_lgfx_load')) return;
  var st = document.createElement('style');
  st.textContent = '@keyframes _lgfxspin{to{transform:rotate(360deg)}}';
  document.documentElement.appendChild(st);
  var o = document.createElement('div');
  o.id = '_lgfx_load';
  o.style.cssText = 'position:fixed;inset:0;z-index:2147483647;display:flex;align-items:center;'
    + 'justify-content:center;background:rgba(8,10,24,0.94);';
  var sp = document.createElement('div');
  sp.style.cssText = 'width:clamp(36px,7vw,64px);height:clamp(36px,7vw,64px);'
    + 'border:5px solid rgba(56,189,248,0.25);border-top-color:#38bdf8;border-radius:50%;'
    + 'animation:_lgfxspin 0.7s linear infinite;';
  o.appendChild(sp);
  document.documentElement.appendChild(o);
  setTimeout(function(){ var el = document.getElementById('_lgfx_load'); if (el) el.remove(); }, 8000);
}

// ---- Control por plan ----
var _entitlements = null;
function isFeatLocked(feat) {
  // Si la licencia universal está activa, nunca bloquear ninguna función
  try {
    if (localStorage.getItem('mmats_license_active') === '1') return false;
  } catch(e) {}
  return !!(_entitlements && _entitlements.enforced && !_entitlements[feat]);
}
function applyEntitlementLocks() {
  var cards = document.querySelectorAll('.app[data-feat]');
  for (var i = 0; i < cards.length; i++) {
    cards[i].classList.toggle('locked', isFeatLocked(cards[i].getAttribute('data-feat')));
  }
}
var _toastTimer = null;
function showFeatToast(msg) {
  var t = document.getElementById('feat-toast');
  if (!t) return;
  t.textContent = msg;
  t.classList.add('show');
  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(function() { t.classList.remove('show'); }, 3200);
}

function featBlocked(feat, name) {
  if (!isFeatLocked(feat)) return false;
  showFeatToast('🔒 Introduce la clave universal MMATS-SANTI-2026-UNIVERSAL para desbloquear ' + name);
  return true;
}

// Modo panel: si está corriendo dentro de split.html (?pane=1)
var PANE_MODE = new URLSearchParams(location.search).get('pane') === '1';

console.log('[MULTIMEDIA ATS SANTI] Script cargado, viewport: ' + window.innerWidth + 'x' + window.innerHeight + ' pane=' + PANE_MODE);

// Reloj del panel: horario del JUEGO
var _gameTimeStr = null, _gameTimeAt = 0;
window._lgfxSetGameTime = function(hhmm) { _gameTimeStr = hhmm; _gameTimeAt = Date.now(); paintTime(); };
window._lgfxClearGameTime = function() { _gameTimeStr = null; paintTime(); };
function paintTime() {
  var el = document.getElementById('sb-time');
  if (!el) return;
  if (_gameTimeStr && (Date.now() - _gameTimeAt) < 12000) { el.textContent = _gameTimeStr; return; }
  var d = new Date();
  el.textContent = String(d.getHours()).padStart(2,'0') + ':' + String(d.getMinutes()).padStart(2,'0');
}
paintTime();
setInterval(paintTime, 2000);

// Abre el modal de elección (Pantalla Completa / Split)
function go(url, name, feat) {
  console.log('[MULTIMEDIA ATS SANTI] go() llamada: ' + url);
  if (feat && featBlocked(feat, name || feat)) return;
  if (PANE_MODE) {
    showLoad();
    window.location.href = url;
    return;
  }
  pendingUrl = url;
  pendingName = name || url.replace(/^https?:\/\//, '').split('/')[0];
  document.getElementById('modal-app-name').textContent = pendingName;
  document.getElementById('app-modal').classList.add('show');
}

// Cierra el modal de selección de app
function closeModal() {
  var m = document.getElementById('app-modal');
  if (m) m.classList.remove('show');
  pendingUrl = null;
  pendingName = null;
}

// Lanza la aplicación seleccionada
function launchApp(useSplit) {
  if (!pendingUrl) return;
  var splitEnabled = useSplit ? 1 : 0;
  var f = document.createElement('iframe');
  f.style.display = 'none';
  f.src = 'lucidgfx://action/split/' + splitEnabled + '/1/50/0';
  document.body.appendChild(f);
  
  var url = pendingUrl;
  showLoad();
  setTimeout(function() {
    f.remove();
    window.location.href = url;
  }, 50);

  closeModal();
}

window._lgfxSetWindow = function(yStart, yEnd) {};

if (PANE_MODE) {
  var hideChat = document.getElementById('app-chat');
  if (hideChat) hideChat.style.display = 'none';
}

function gpsClick() {
  if (PANE_MODE) sendAction('splitchatgps');
  else showGps();
}

function showGps() {
  document.getElementById('grid').style.display = 'none';
  document.getElementById('sb').style.display = 'none';
  document.getElementById('dots').style.display = 'none';
  document.body.style.background = '#161b22';
  document.body.style.backgroundImage = 'none';
  document.getElementById('gps-mode').classList.add('active');
  
  var f = document.createElement('iframe');
  f.style.display = 'none';
  f.src = 'lucidgfx://action/split/1/1/92/0/1';
  document.body.appendChild(f);
  setTimeout(function() { f.remove(); }, 100);
}

function exitGpsMode() {
  var g = document.getElementById('gps-mode');
  if (g) g.classList.remove('active');
  showLoad();
  window.location.href = 'lucidgfx://action/resethome';
}

function goHome() {
  window.location.href = 'lucidgfx://action/resethome';
}

function doAltTab() {
  window.location.href = 'lucidgfx://action/alttab';
}

function sendAction(path) {
  var f = document.createElement('iframe');
  f.style.display = 'none';
  f.src = 'lucidgfx://action/' + path;
  document.body.appendChild(f);
  setTimeout(function() { f.remove(); }, 100);
}

function openLicense() {
  document.getElementById('lic-modal').classList.add('show');
  try {
    if (localStorage.getItem('mmats_license_active') === '1') {
      window._lgfxOnLicense(getUniversalLicensePayload());
      return;
    }
  } catch(e) {}
  sendAction('licensequery');
}

function closeLicense() {
  var m = document.getElementById('lic-modal');
  if (m) m.classList.remove('show');
}

// Activación de Licencia Universal en Home
function activateLicense() {
  var key = (document.getElementById('lic-key').value || '').trim().toUpperCase();
  var stat = document.getElementById('lic-status');
  if (!key) {
    if (stat) stat.textContent = 'Introduce la clave universal: MMATS-SANTI-2026-UNIVERSAL';
    return;
  }
  if (isUniversalKey(key)) {
    try {
      localStorage.setItem('mmats_license_key', UNIVERSAL_LICENSE_KEY);
      localStorage.setItem('mmats_license_active', '1');
    } catch(e) {}
    var licData = getUniversalLicensePayload();
    window._lgfxOnLicense(licData);
    showFeatToast('✅ ¡Licencia universal activada con éxito!');
    sendAction('activate/' + encodeURIComponent(UNIVERSAL_LICENSE_KEY));
    setTimeout(closeLicense, 800);
  } else {
    if (stat) stat.textContent = '❌ Clave incorrecta. Usa: MMATS-SANTI-2026-UNIVERSAL';
    showFeatToast('❌ Clave incorrecta');
  }
}

// ---- Chat en vivo ----
var chatPlatform = 'twitch';
var chatLayout = 'full';
var chatSavedChannels = { twitch: '', youtube: '' };

function setChatPlatform(plat) {
  chatPlatform = plat;
  var tw = document.getElementById('chat-plat-twitch');
  var yt = document.getElementById('chat-plat-youtube');
  tw.classList.toggle('selected', plat === 'twitch');
  yt.classList.toggle('selected', plat === 'youtube');
  tw.style.opacity = yt.style.opacity = '1';
  document.getElementById('chat-channel').value = chatSavedChannels[plat] || '';
  document.getElementById('chat-channel').placeholder = (plat === 'youtube') ? '@tu_canal' : 'tu_canal';
}

function setChatLayout(layout) {
  chatLayout = layout;
  var full  = document.getElementById('chat-layout-full');
  var split = document.getElementById('chat-layout-split');
  full.classList.toggle('selected',  layout === 'full');
  split.classList.toggle('selected', layout === 'split');
  full.style.opacity = split.style.opacity = '1';
}

function openChat() {
  if (featBlocked('chat', 'Chat en vivo')) return;
  document.getElementById('chat-modal').classList.add('show');
  setChatPlatform(chatPlatform);
  setChatLayout(chatLayout);
  sendAction('chatquery');
}

function closeChat() {
  var m = document.getElementById('chat-modal');
  if (m) m.classList.remove('show');
}

function openChatChannel() {
  var chan = (document.getElementById('chat-channel').value || '').trim().replace(/^#/, '');
  if (!chan) return;
  closeChat();
  showLoad();
  if (chatLayout === 'split') {
    sendAction('splitchat2/' + chatPlatform + '/' + encodeURIComponent(chan));
  } else {
    sendAction('chat/' + chatPlatform + '/' + encodeURIComponent(chan));
  }
}

window._lgfxOnChatConfig = function(s) {
  if (!s) return;
  chatSavedChannels.twitch = s.twitch || '';
  chatSavedChannels.youtube = s.youtube || '';
  document.getElementById('chat-channel').value = chatSavedChannels[chatPlatform] || '';
};

var _homeUpdateUrl = 'https://gfxmods.com.br/dashboard';
function openUpdate() { sendAction('openurl/' + _homeUpdateUrl); }

// Callback de estado de licencia
window._lgfxOnLicense = function(s) {
  // Si está activada universalmente en localStorage, no dejar que se deshabilite
  try {
    if (localStorage.getItem('mmats_license_active') === '1') {
      s = getUniversalLicensePayload();
    }
  } catch(e) {}
  if (!s) return;

  var statusMap = {
    ok: '✅ ' + (s.statusText || 'Licencia activa'),
    invalid: '❌ Clave de licencia no válida',
    hwid_mismatch: '⚠️ PC no autorizado',
    expired: '⏳ Licencia expirada',
    banned: '🚫 Licencia revocada',
    servererror: '📡 Error de conexión',
    notchecked: 'Sin licencia activa'
  };
  var licStat = document.getElementById('lic-status');
  if (licStat) licStat.textContent = statusMap[s.status] || (s.statusText || '—');
  var licBtn = document.getElementById('lic-activate-btn');
  if (licBtn) licBtn.style.opacity = '1';

  var licensed = (s.status === 'ok');
  var licInfo = document.getElementById('lic-info');
  if (licInfo) licInfo.style.display = licensed ? 'block' : 'none';
  if (licensed) {
    var maskedEl = document.getElementById('lic-masked');
    if (maskedEl) maskedEl.textContent = s.masked || 'MMATS-****-****-VERSAL';
    var edEl = document.getElementById('lic-edition');
    if (edEl) edEl.textContent = s.edition || 'Universal Permanente';
    var daysEl = document.getElementById('lic-days');
    if (daysEl) daysEl.textContent = (s.days < 0) ? 'Permanente' : (s.days + ' días');
  }
  if (s.error && !licensed && licStat) licStat.textContent += ' — ' + s.error;
  var hwidEl = document.getElementById('lic-hwid');
  if (hwidEl) hwidEl.textContent = 'Modo: Licencia Universal Offline';

  _entitlements = s.entitlements || null;
  applyEntitlementLocks();

  var sp = document.getElementById('sb-partner');
  if (sp) sp.style.display = (_entitlements && _entitlements.partner) ? '' : 'none';

  var un = document.getElementById('update-notice');
  if (un) {
    if (s.versionStatus && s.versionStatus !== 'ok') {
      var reqUp = (s.versionStatus === 'update_required');
      if (reqUp) { un.style.background='rgba(239,68,68,0.2)'; un.style.border='1px solid rgba(239,68,68,0.5)'; un.style.color='#fca5a5'; }
      else       { un.style.background='rgba(245,158,11,0.2)'; un.style.border='1px solid rgba(245,158,11,0.5)';  un.style.color='#fde68a'; }
      var unTxt = document.getElementById('un-text');
      if (unTxt) {
        unTxt.textContent =
          (reqUp ? 'Actualización obligatoria' : 'Nueva versión disponible')
          + (s.latest ? ' — v' + s.latest : '') + ' · haz clic para actualizar';
      }
      un.style.display = 'block';
    } else {
      un.style.display = 'none';
    }
  }
};

// ==========================================================================
// Sistema de Fondo Personalizado (Fondo Guardado, Selector y Restauración)
// ==========================================================================
var _defaultBg = 'radial-gradient(ellipse 160% 90% at 50% -10%, rgba(28, 44, 110, 0.6) 0%, transparent 65%), radial-gradient(ellipse 100% 50% at 85% 100%, rgba(14, 45, 90, 0.35) 0%, transparent 55%), linear-gradient(180deg, #070913 0%, #0c1020 100%)';

function applyCustomBackground(bgDataUrl) {
  if (bgDataUrl) {
    var safe = String(bgDataUrl).replace(/["\\]/g, '');
    document.body.style.backgroundImage =
      'linear-gradient(rgba(7, 9, 19, 0.68), rgba(12, 16, 32, 0.88)), url("' + safe + '")';
    document.body.style.backgroundSize = 'cover';
    document.body.style.backgroundPosition = 'center';
    document.body.style.backgroundRepeat = 'no-repeat';
  } else {
    document.body.style.backgroundImage = _defaultBg;
    document.body.style.backgroundSize = '';
    document.body.style.backgroundPosition = '';
    document.body.style.backgroundRepeat = '';
  }
}

(function initSavedBg() {
  try {
    var savedBg = localStorage.getItem('multimedia_custom_bg');
    if (savedBg) {
      applyCustomBackground(savedBg);
    }
  } catch(e) {}
})();

window._lgfxSetBackground = function(url) {
  if (url) {
    try { localStorage.setItem('multimedia_custom_bg', url); } catch(e) {}
    applyCustomBackground(url);
  } else {
    try { localStorage.removeItem('multimedia_custom_bg'); } catch(e) {}
    applyCustomBackground(null);
  }
};

function pickLocalBackground(input) {
  if (!input || !input.files || !input.files[0]) return;
  var file = input.files[0];
  var validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp'];
  if (validTypes.indexOf(file.type.toLowerCase()) === -1 && !file.name.match(/\.(jpe?g|png|webp)$/i)) {
    showFeatToast('❌ Formato no válido. Usa JPG, JPEG, PNG o WEBP.');
    return;
  }
  var reader = new FileReader();
  reader.onload = function(e) {
    var dataUrl = e.target.result;
    try {
      localStorage.setItem('multimedia_custom_bg', dataUrl);
    } catch(err) {
      console.warn('Fondo guardado localmente:', err);
    }
    applyCustomBackground(dataUrl);
    showFeatToast('✅ ¡Fondo de pantalla aplicado!');
    closeBgModal();
  };
  reader.readAsDataURL(file);
}

function clearCustomBackground() {
  try {
    localStorage.removeItem('multimedia_custom_bg');
  } catch(e) {}
  applyCustomBackground(null);
  showFeatToast('Fondo predeterminado restaurado');
  closeBgModal();
}

function openBgModal() {
  var m = document.getElementById('bg-modal');
  if (m) m.classList.add('show');
}

function closeBgModal() {
  var m = document.getElementById('bg-modal');
  if (m) m.classList.remove('show');
}

// Cerrar modales con tecla ESC
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    closeModal();
    closeLicense();
    closeChat();
    closeBgModal();
  }
});

// Cerrar modales haciendo clic fuera
(function() {
  var modals = ['app-modal', 'lic-modal', 'chat-modal', 'bg-modal'];
  modals.forEach(function(id) {
    var el = document.getElementById(id);
    if (el) {
      el.addEventListener('click', function(e) {
        if (e.target === el) {
          el.classList.remove('show');
        }
      });
    }
  });
})();

if (new URLSearchParams(location.search).get('openchat') === '1') {
  openChat();
}

// Inicializar estado de licencia guardada
(function initSavedLicense() {
  try {
    var savedKey = localStorage.getItem('mmats_license_key');
    var isActive = localStorage.getItem('mmats_license_active');
    if (isActive === '1' || isUniversalKey(savedKey)) {
      window._lgfxOnLicense(getUniversalLicensePayload());
      return;
    }
  } catch(e) {}
})();

sendAction('licensequery');
sendAction('bgquery');

// Mensaje de bienvenida inicial (1x por sesión)
(function () {
  function showWelcome() {
    var w = document.getElementById('welcome');
    if (!w) return;
    requestAnimationFrame(function () { w.classList.add('show'); });
    setTimeout(function () { w.classList.remove('show'); }, 3500);
  }
  var seen = false;
  try {
    seen = !!sessionStorage.getItem('lgfx_welcomed');
    if (!seen) sessionStorage.setItem('lgfx_welcomed', '1');
  } catch (e) {}
  if (!seen) showWelcome();
})();

setInterval(function(){ 
  try {
    if (localStorage.getItem('mmats_license_active') === '1') return;
  } catch(e) {}
  sendAction('licensequery'); 
}, 3000);
