// Compensar DPI scaling del WebView2.
(function() {
  var dpr = window.devicePixelRatio || 1;
  var panel = document.getElementById('panel');
  if (panel && dpr > 1) {
    panel.style.transform = 'scale(' + (1 / dpr).toFixed(6) + ')';
  }
  window._lucidDPR = dpr;
})();

// =============================================================================
// Bridge JS↔C++ vía window.chrome.webview (WebView2)
// =============================================================================
function postMsg(obj) {
  if (window.chrome && window.chrome.webview)
    window.chrome.webview.postMessage(obj);
}

// ---- Estado local sincronizado con C++ ----
var state = {
  mmRunning: false, mmUrl: '',
  zoom: 150,
  mouse_color: '#FFFFFF',
  rtHash: '0000000000000000'
};

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

// ---- Dispositivos conocidos (RT hashes del juego) ----
var DEVICES = [
  {hash:'6E445921D4FBB174', icon:'📺', name:'Pantalla Central Multimedia', info:'Volvo FH5/FH6, Scania'},
  {hash:'5891A3883361780B', icon:'🗺', name:'GPS Parabrisas',            info:'Genérico'},
  {hash:'F778E70824018E0B', icon:'📱', name:'GPS Celular',                info:'Genérico'},
  {hash:'E2A0D7B1DF649166', icon:'🖥', name:'Multimedia Compacta',        info:'Scania (mod)'},
];

// ---- Cambio de pestañas (Sección Enlaces eliminada) ----
var TABS = ['mm','cfg','lic','dbg'];
var licTabActive = false;
function tab(id) {
  TABS.forEach(function(t) {
    var tEl = document.getElementById('t-'+t);
    var pEl = document.getElementById('p-'+t);
    if (tEl) tEl.className = 'tab' + (t===id?' on':'');
    if (pEl) pEl.className = 'pane' + (t===id?' on':'');
  });
  licTabActive = (id === 'lic');
  if (id === 'lic' || id === 'cfg') postMsg({action:'licensequery'});
  dbgTabActive = (id === 'dbg');
  if (id === 'dbg') { if (dbgScanning) { dbgStartPoll(); postMsg({action:'dbgList'}); } dbgRenderRTs(); }
  else { dbgStopPoll(); }
}

setInterval(function(){ if (licTabActive) postMsg({action:'licensequery'}); }, 4000);

// ---- Cerrar menú ----
function closeMenu() { postMsg({action:'close'}); }
var bdEl = document.getElementById('bd');
if (bdEl) {
  bdEl.addEventListener('click', function(e) {
    if (e.target === this) closeMenu();
  });
}

// ---- Multimedia: INICIAR / DETENER ----
function mmStart() {
  var alert = document.getElementById('mm-alert');
  var zeroHash = !state.rtHash || state.rtHash === '0000000000000000';
  if (zeroHash) {
    if (alert) {
      alert.style.display = '';
      alert.textContent = '⚠ Selecciona un dispositivo abajo antes de iniciar.';
    }
    return;
  }
  if (alert) alert.style.display = 'none';
  postMsg({action:'startMm', hash:state.rtHash});
  setMmRunning(true, 'lucidgfx_home.html');
}

function mmStop() {
  postMsg({action:'stopMm'});
  setMmRunning(false, '');
}

function setMmRunning(running, url) {
  state.mmRunning = running;
  state.mmUrl     = url || '';
  var btn1 = document.getElementById('btn-iniciar');
  var btn2 = document.getElementById('btn-parar');
  var title = document.getElementById('mm-status-title');
  var info  = document.getElementById('mm-status-info');
  var fstatus = document.getElementById('fstatus');
  if (running) {
    if (btn1) btn1.style.display = 'none';
    if (btn2) btn2.style.display = '';
    if (title) title.textContent = '▶ Activo';
    if (info)  info.textContent  = url || 'En ejecución';
    if (fstatus) fstatus.textContent = 'Multimedia activa';
  } else {
    if (btn1) btn1.style.display = '';
    if (btn2) btn2.style.display = 'none';
    if (title) title.textContent = '⏸ Detenido';
    if (info)  info.textContent  = 'Haz clic en INICIAR para activar';
    if (fstatus) fstatus.textContent = 'MULTIMEDIA ATS SANTI activo';
  }
  updateSourceCards();
}

// ---- Zoom ----
function zoomAdj(delta) {
  var inp = document.getElementById('zoom-val');
  var sl  = document.getElementById('s-zoom');
  var v   = Math.max(10, Math.min(500, parseInt((inp ? inp.value : 150), 10) + delta * 10));
  if (inp) inp.value = v;
  if (sl) sl.value = v;
  postMsg({action:'setZoom', val:v});
}

function zoomSet(v) {
  v = Math.max(10, Math.min(500, parseInt(v, 10) || 150));
  var inp = document.getElementById('zoom-val');
  var sl  = document.getElementById('s-zoom');
  if (inp) inp.value = v;
  if (sl) sl.value = v;
  postMsg({action:'setZoom', val:v});
}

// ---- Volumen de la multimedia (0-100) ----
function volAdj(delta) {
  var vv = document.getElementById('vol-val');
  var vs = document.getElementById('s-vol');
  var cur = vs ? parseInt(vs.value, 10) : 100;
  if (!Number.isFinite(cur)) cur = 100;
  var v = Math.max(0, Math.min(100, cur + delta));
  if (vv) vv.textContent = v + '%';
  if (vs) vs.value = v;
  try { localStorage.setItem('mmats_audio_volume', String(v)); } catch(e){} // preferencia bruta (la home lee esto)
  postMsg({action:'setVol', val:v});
}

function volLabel(v) {
  var vv = document.getElementById('vol-val');
  if (vv) vv.textContent = (Math.max(0, Math.min(100, parseInt(v, 10) || 0))) + '%';
}

function volSlider(v) {
  v = Math.max(0, Math.min(100, parseInt(v, 10) || 0));
  var vv = document.getElementById('vol-val');
  if (vv) vv.textContent = v + '%';
  try { localStorage.setItem('mmats_audio_volume', String(v)); } catch(e){} // preferencia bruta (la home lee esto)
  postMsg({action:'setVol', val:v});
}

// ---- Sensibilidad del ratón ----
function sensSet(v) {
  var pct = Math.max(30, Math.min(200, parseInt(v, 10) || 100));
  var lbl = document.getElementById('sens-val');
  if (lbl) lbl.textContent = (pct / 100).toFixed(1) + 'x';
  postMsg({action:'setSetting', key:'mouse_sensitivity', val: pct});
}

// ---- Color del cursor F8 ----
var MOUSE_COLORS = ['#FFFFFF','#000000','#FF3B30','#FF9500','#FFCC00','#34C759','#32ADE6','#0A84FF','#FF2D55','#AF52DE'];
function buildMouseColors() {
  var box = document.getElementById('mouse-colors');
  if (!box) return;
  box.innerHTML = '';
  MOUSE_COLORS.forEach(function(c) {
    var d = document.createElement('div');
    d.className = 'msw';
    d.dataset.color = c;
    d.style.cssText = 'width:22px;height:22px;border-radius:50%;cursor:pointer;background:' + c +
      ';border:2px solid rgba(255,255,255,0.15);box-sizing:border-box;transition:all 0.15s;';
    d.addEventListener('mousedown', function(e) { e.preventDefault(); mouseColorSet(c); });
    box.appendChild(d);
  });
  highlightMouseColor(state.mouse_color || '#FFFFFF');
}

function highlightMouseColor(c) {
  var sel = (c || '').toUpperCase();
  var els = document.querySelectorAll('#mouse-colors .msw');
  for (var i = 0; i < els.length; i++) {
    var on = els[i].dataset.color.toUpperCase() === sel;
    els[i].style.boxShadow   = on ? '0 0 0 2px #38bdf8, 0 0 8px rgba(56,189,248,0.6)' : 'none';
    els[i].style.borderColor = on ? '#38bdf8' : 'rgba(255,255,255,0.15)';
    els[i].style.transform   = on ? 'scale(1.15)' : 'scale(1)';
  }
}

function mouseColorSet(c) {
  state.mouse_color = c;
  highlightMouseColor(c);
  postMsg({action:'setMouseColor', val: c});
}

function powerGateSet(on) { postMsg({action:'setPowerGate', val: on ? '1' : '0'}); }
function mouseHintSet(on) { postMsg({action:'setMouseHint', val: on ? '1' : '0'}); }

// =============================================================================
// AUDIO INMERSIVO 3D POR CÁMARA
// El trabajo real lo hace el servicio externo mmats_audio_inmersivo.exe: detecta
// la cámara leyendo controls.sii + hook de teclado, y atenúa las sesiones de
// audio del WebView2 por WASAPI. Este overlay es solo su panel de control y
// habla con él por HTTP en 127.0.0.1.
//   No se hace desde aquí porque al abrir Spotify a pantalla completa la página
//   del mod se sustituye por la del sitio y cualquier script nuestro muere.
// =============================================================================
var IMMERSIVE_URL = 'http://127.0.0.1:48221';
var _immOnline = false;
var _immPollTimer = null;

function immersiveAudioOn(){ try{ return localStorage.getItem('mmats_immersive_audio') === '1'; }catch(e){ return false; } }

function _immPost(payload) {
  // text/plain evita el preflight CORS: el servicio parsea el cuerpo como JSON igual.
  return fetch(IMMERSIVE_URL + '/config', {
    method: 'POST',
    headers: { 'Content-Type': 'text/plain' },
    body: JSON.stringify(payload)
  }).then(function(r){ return r.json(); }).then(_immApply).catch(function(){ _immOffline(); });
}

function immersiveToggleSet(on) {
  try { localStorage.setItem('mmats_immersive_audio', on ? '1' : '0'); } catch(e) {}
  var cb = document.getElementById('immersive-toggle');
  if (cb) cb.checked = !!on;
  _immPost({ enabled: !!on });
}

function immersiveLevelLabel(v) {
  var el = document.getElementById('immersive-val');
  if (el) el.textContent = (Math.max(0, Math.min(100, parseInt(v, 10) || 0))) + '%';
}

function immersiveLevelSet(v) {
  v = Math.max(0, Math.min(100, parseInt(v, 10) || 0));
  immersiveLevelLabel(v);
  try { localStorage.setItem('mmats_immersive_level', String(v)); } catch(e) {}
  _immPost({ exterior_pct: v });
}

function _immApply(st) {
  if (!st || !st.ok) { _immOffline(); return; }
  _immOnline = true;
  var cb = document.getElementById('immersive-toggle');
  if (cb) cb.checked = !!st.enabled;
  var sl = document.getElementById('s-immersive');
  if (sl && document.activeElement !== sl) sl.value = st.exterior_pct;
  immersiveLevelLabel(st.exterior_pct);
  try {
    localStorage.setItem('mmats_immersive_audio', st.enabled ? '1' : '0');
    localStorage.setItem('mmats_immersive_level', String(st.exterior_pct));
  } catch(e) {}

  var lbl = document.getElementById('immersive-status');
  if (!lbl) return;
  if (!st.enabled) {
    lbl.style.color = '#64748b';
    lbl.textContent = 'Desactivado';
  } else if (!st.juego) {
    lbl.style.color = '#94a3b8';
    lbl.textContent = 'Listo · esperando a ATS';
  } else if (!st.sesiones) {
    lbl.style.color = '#f59e0b';
    lbl.textContent = 'Sin audio · abre Spotify o YouTube';
  } else if (st.interior) {
    lbl.style.color = '#10b981';
    lbl.textContent = '🎧 En cabina · volumen pleno';
  } else {
    lbl.style.color = '#38bdf8';
    lbl.textContent = '🚚 Cámara ' + st.camara + ' · atenuado al ' + st.exterior_pct + '%';
  }
}

function _immOffline() {
  _immOnline = false;
  var lbl = document.getElementById('immersive-status');
  if (lbl) {
    lbl.style.color = '#ef4444';
    lbl.textContent = 'Servicio no iniciado';
  }
}

function immersivePoll() {
  fetch(IMMERSIVE_URL + '/estado', { cache: 'no-store' })
    .then(function(r){ return r.json(); })
    .then(_immApply)
    .catch(function(){ _immOffline(); });
}

function immersiveStartPoll() {
  if (_immPollTimer) return;
  immersivePoll();
  _immPollTimer = setInterval(immersivePoll, 1500);
}

function openLink(url) { postMsg({action:'openUrl', val: url}); }

var _updateUrl = 'https://gfxmods.com.br/dashboard';
function openUpdate() { postMsg({action:'openUrl', val: _updateUrl}); }

function zoomSlider(v) {
  var inp = document.getElementById('zoom-val');
  if (inp) inp.value = v;
  postMsg({action:'setZoom', val:parseInt(v, 10)});
}

function selectDevice(dev) {
  state.rtHash = dev.hash;
  postMsg({action:'selectHash', hash:dev.hash});
  updateSourceCards();
}

function buildDeviceCard(dev) {
  var isActive = state.rtHash === dev.hash;
  var d = document.createElement('div');
  d.className = 'hash-card' + (isActive ? ' active' : '');
  d.id = 'card-' + dev.hash;
  d.innerHTML =
    '<div class="card-icon">' + dev.icon + '</div>' +
    '<div class="card-name">' + dev.name + '</div>' +
    '<div class="card-truck">' + dev.info + '</div>';
  d.addEventListener('mousedown', function(e) { e.stopPropagation(); selectDevice(dev); });
  return d;
}

function updateSourceCards() {
  var list = document.getElementById('hash-list');
  if (list) {
    list.innerHTML = '';
    DEVICES.forEach(function(d) { list.appendChild(buildDeviceCard(d)); });
  }
}

// =============================================================================
// DEBUG
// =============================================================================
var dbgScanning = false;
var dbgRTs = [];
var dbgPollTimer = null;
var dbgTabActive = false;

function dbgStartPoll() {
  if (dbgPollTimer) return;
  dbgPollTimer = setInterval(function() { postMsg({action:'dbgList'}); }, 800);
}
function dbgStopPoll() {
  if (dbgPollTimer) { clearInterval(dbgPollTimer); dbgPollTimer = null; }
}

function dbgScanToggle(on) {
  dbgScanning = on;
  postMsg({action:'dbgScan', val: on ? '1' : '0'});
  var b1 = document.getElementById('dbg-scan-on');
  var b2 = document.getElementById('dbg-scan-off');
  if (b1) b1.style.display = on ? 'none' : '';
  if (b2) b2.style.display = on ? '' : 'none';
  if (on) { dbgStartPoll(); postMsg({action:'dbgList'}); }
  else    { dbgStopPoll(); }
}
function dbgHitSet(v) {
  var n = Math.max(0, Math.min(30, parseInt(v, 10) || 0));
  var el = document.getElementById('dbg-hit');
  if (el) el.value = n;
  postMsg({action:'dbgHit', val: n});
}
function dbgHitAdj(d) {
  var el = document.getElementById('dbg-hit');
  dbgHitSet((parseInt(el ? el.value : 0, 10) || 0) + d);
}
function dbgIsScreen(rt) {
  var S = {128:1, 256:1, 512:1, 1024:1, 2048:1};
  return S[rt.w] && S[rt.h];
}
function dbgPaintRT(hash) {
  state.rtHash = hash;
  postMsg({action:'selectHash', hash: hash});
  postMsg({action:'dbgHit', val: parseInt((document.getElementById('dbg-hit')||{}).value, 10) || 0});
  postMsg({action:'startMm', hash: hash});
  setMmRunning(true, 'lucidgfx_home.html');
  dbgRenderRTs();
}
function dbgRenderRTs() {
  var box = document.getElementById('dbg-rt-list');
  if (!box) return;
  var onlyScreens = document.getElementById('dbg-screens-only');
  var list = dbgRTs.slice();
  if (onlyScreens && onlyScreens.checked) list = list.filter(dbgIsScreen);
  var cnt = document.getElementById('dbg-count');
  if (cnt) cnt.textContent = '(' + list.length + ')';
  if (!list.length) {
    box.innerHTML = '<div style="color:rgba(255,255,255,0.4);font-size:12px;">' +
      (dbgScanning ? 'Ningún RT detectado aún — cierra el menú y mira hacia la pantalla del camión.' : 'Activa el escaneo para listar.') +
      '</div>';
    return;
  }
  box.innerHTML = '';
  list.forEach(function(rt) {
    var active = (state.rtHash || '').toUpperCase() === rt.hash.toUpperCase();
    var row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:10px;' +
      'padding:8px 10px;margin-bottom:6px;border-radius:8px;' +
      'background:' + (active ? 'rgba(56,189,248,0.18)' : 'rgba(255,255,255,0.04)') + ';' +
      'border:1px solid ' + (active ? '#38bdf8' : 'rgba(255,255,255,0.08)') + ';';
    var info = document.createElement('div');
    info.style.cssText = 'min-width:0;flex:1;';
    info.innerHTML =
      '<div style="font-family:monospace;font-size:12px;color:#cfe0ff;letter-spacing:0.5px;">' +
        rt.hash + (active ? ' &#10003;' : '') + '</div>' +
      '<div style="font-size:10.5px;color:rgba(255,255,255,0.45);margin-top:2px;">' +
        rt.w + '×' + rt.h + ' &middot; fmt ' + rt.fmt + ' &middot; mips ' + rt.mips +
        ' &middot; arr ' + rt.arr + ' &middot; máx/frame ' + rt.max + '</div>';
    var btn = document.createElement('button');
    btn.className = 'btn';
    btn.textContent = 'Pintar';
    btn.style.cssText = 'padding:6px 12px;font-size:12px;flex:none;';
    btn.addEventListener('mousedown', function(e) { e.stopPropagation(); dbgPaintRT(rt.hash); });
    row.appendChild(info);
    row.appendChild(btn);
    box.appendChild(row);
  });
}

// ---- Aplicar estado completo recibido de C++ ----
function applyState(s) {
  if (!s) return;
  if (s.rtHash) { state.rtHash = s.rtHash; }
  if (s.zoom) {
    var zi = document.getElementById('zoom-val');
    var zs = document.getElementById('s-zoom');
    if (zi) zi.value = s.zoom;
    if (zs) zs.value = s.zoom;
  }
  if (typeof s.volLevel === 'number') {
    var vv = document.getElementById('vol-val');
    var vs = document.getElementById('s-vol');
    if (vv) vv.textContent = s.volLevel + '%';
    if (vs) vs.value = s.volLevel;
  }
  if (typeof s.mouseSens === 'number') {
    var ss = document.getElementById('s-sens');
    var sl = document.getElementById('sens-val');
    if (ss) ss.value = s.mouseSens;
    if (sl) sl.textContent = (s.mouseSens / 100).toFixed(1) + 'x';
  }
  if (typeof s.mouseColor === 'string' && s.mouseColor) {
    state.mouse_color = s.mouseColor;
    highlightMouseColor(s.mouseColor);
  }
  if (typeof s.version === 'string' && s.version) {
    var hv = document.getElementById('hdr-ver');
    if (hv) hv.textContent = 'v' + s.version;
  }
  if (typeof s.debug !== 'undefined') {
    var td = document.getElementById('t-dbg');
    if (td) td.style.display = s.debug ? '' : 'none';
  }
  if (typeof s.powerGate !== 'undefined') {
    var pg = document.getElementById('pg-toggle');
    if (pg) pg.checked = (s.powerGate === 1 || s.powerGate === '1' || s.powerGate === true);
  }
  if (typeof s.mouseHint !== 'undefined') {
    var mh = document.getElementById('mh-toggle');
    if (mh) mh.checked = (s.mouseHint === 1 || s.mouseHint === '1' || s.mouseHint === true);
  }
  setMmRunning(!!s.mmRunning, s.mmUrl||'');

  if (typeof s.hkMenu === 'number') {
    state.hk_menu = s.hkMenu;
    var bm = document.getElementById('hk-menu');
    if (bm) { bm.textContent = vkName(s.hkMenu); bm.classList.remove('recording'); }
    if (hkRecording === 'menu') hkRecording = null;
  }
  if (typeof s.hkInteract === 'number') {
    state.hk_mouse = s.hkInteract;
    var bi = document.getElementById('hk-mouse');
    if (bi) { bi.textContent = vkName(s.hkInteract); bi.classList.remove('recording'); }
    if (hkRecording === 'mouse') hkRecording = null;
  }
  if (typeof s.hkZoomIn === 'number') {
    state.hk_zoomin = s.hkZoomIn;
    var bzi = document.getElementById('hk-zoomin');
    if (bzi) { bzi.textContent = vkName(s.hkZoomIn); bzi.classList.remove('recording'); }
    if (hkRecording === 'zoomin') hkRecording = null;
  }
  if (typeof s.hkZoomOut === 'number') {
    state.hk_zoomout = s.hkZoomOut;
    var bzo = document.getElementById('hk-zoomout');
    if (bzo) { bzo.textContent = vkName(s.hkZoomOut); bzo.classList.remove('recording'); }
    if (hkRecording === 'zoomout') hkRecording = null;
  }
  if (typeof s.hkGps === 'number') {
    state.hk_gps = s.hkGps;
    var bgps = document.getElementById('hk-gps');
    if (bgps) { bgps.textContent = vkName(s.hkGps); bgps.classList.remove('recording'); }
    if (hkRecording === 'gps') hkRecording = null;
  }
  if (typeof s.hkVolUp === 'number') {
    state.hk_volup = s.hkVolUp;
    var bvu = document.getElementById('hk-volup');
    if (bvu) { bvu.textContent = 'Ctrl + ' + vkName(s.hkVolUp); bvu.classList.remove('recording'); }
    if (hkRecording === 'volup') hkRecording = null;
  }
  if (typeof s.hkVolDown === 'number') {
    state.hk_voldown = s.hkVolDown;
    var bvd = document.getElementById('hk-voldown');
    if (bvd) { bvd.textContent = 'Ctrl + ' + vkName(s.hkVolDown); bvd.classList.remove('recording'); }
    if (hkRecording === 'voldown') hkRecording = null;
  }
  updateSourceCards();
}

// ---- Licencia ----
var LIC_MAP = {
  ok:'✅ Licencia activa', activating:'⏳ Activando...', invalid:'❌ Clave no válida',
  hwid_mismatch:'⚠️ PC no autorizado', expired:'⏳ Licencia expirada',
  banned:'🚫 Licencia revocada', servererror:'📡 Error de conexión con el servidor', notchecked:'Sin licencia activa'
};
var licPollTimer = null;

// ---- Fondo Personalizado (Pestaña Configuración) ----
function bgPick() {
  var fileInp = document.getElementById('bg-file-input');
  if (fileInp) {
    fileInp.click();
  } else {
    var st = document.getElementById('bg-status');
    if (st) st.textContent = 'Abriendo selector de archivos…';
    postMsg({action:'pickBackground'});
  }
}

function handleOverlayBgSelect(input) {
  if (!input || !input.files || !input.files[0]) return;
  var file = input.files[0];
  var validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp'];
  if (validTypes.indexOf(file.type.toLowerCase()) === -1 && !file.name.match(/\.(jpe?g|png|webp)$/i)) {
    var st = document.getElementById('bg-status');
    if (st) st.textContent = '❌ Formato no válido — usa JPG, JPEG, PNG o WEBP.';
    return;
  }
  var reader = new FileReader();
  reader.onload = function(e) {
    var dataUrl = e.target.result;
    try {
      localStorage.setItem('multimedia_custom_bg', dataUrl);
    } catch(err) {
      console.warn('Storage:', err);
    }
    var st = document.getElementById('bg-status');
    if (st) st.textContent = '✅ ¡Fondo guardado y aplicado!';
    postMsg({action:'setBackgroundData', val: dataUrl});
  };
  reader.readAsDataURL(file);
}

function bgClear() {
  try {
    localStorage.removeItem('multimedia_custom_bg');
  } catch(e) {}
  var st = document.getElementById('bg-status');
  if (st) st.textContent = 'Fondo restaurado al predeterminado.';
  postMsg({action:'clearBackground'});
}

window._lgfxBgResult = function(kind) {
  var st = document.getElementById('bg-status');
  if (!st) return;
  var m = {
    ok:       '✅ ¡Fondo de pantalla aplicado!',
    cleared:  'Fondo predeterminado restaurado.',
    nopro:    '🔒 Función disponible para usuarios autorizados.',
    badtype:  '❌ Formato no válido — usa JPG, JPEG, PNG o WEBP.',
    toobig:   '❌ Archivo demasiado grande (máximo 8 MB).',
    copyfail: '❌ No se pudo leer o cargar el archivo de imagen.'
  };
  st.textContent = m[kind] || '';
};

function applyThemesGate(allowed) {
  var on = (allowed !== false);
  var lock = document.getElementById('theme-lock');
  if (lock) lock.style.display = on ? 'none' : 'block';
  ['bg-pick','bg-clear'].forEach(function(id) {
    var b = document.getElementById(id);
    if (b) { b.disabled = !on; b.style.opacity = on ? '1' : '0.4'; b.style.pointerEvents = on ? 'auto' : 'none'; }
  });
}

function applyLicense(d) {
  // Si la licencia ya fue activada universalmente en localStorage, no permitir que el backend offline la desactive
  try {
    var savedActive = localStorage.getItem('mmats_license_active');
    if (savedActive === '1' && d.status !== 'ok') {
      d = getUniversalLicensePayload();
    }
  } catch(e) {}

  var badge = document.getElementById('lic-badge');
  if (badge) {
    badge.textContent = LIC_MAP[d.status] || d.statusText || d.status;
    badge.className = 'lic-badge ' + (d.status === 'ok' ? 'ok' : 'nok');
  }
  var licMsg = document.getElementById('lic-msg');
  if (licMsg) licMsg.textContent = d.error || '';

  var active = (d.status === 'ok');
  var licInfo = document.getElementById('lic-info');
  var licAct = document.getElementById('lic-activate');
  if (licInfo) licInfo.style.display = active ? 'block' : 'none';
  if (licAct) licAct.style.display   = active ? 'none'  : 'block';
  if (active) {
    var licEd = document.getElementById('lic-edition');
    if (licEd) licEd.textContent = d.edition || 'Edición Universal';
    var licD = document.getElementById('lic-days');
    if (licD) licD.textContent = (typeof d.days === 'number' && d.days < 0) ? 'Permanente' : ((d.days||0) + ' días');
  }
  var hwEl = document.getElementById('lic-hwid');
  if (hwEl) hwEl.textContent = 'Estado: Validación Offline Universal';
  applyThemesGate(true);

  var ver       = document.getElementById('lic-ver');
  var banner    = document.getElementById('update-banner');
  var mmBlocked = document.getElementById('mm-blocked');
  var mmNormal  = document.getElementById('mm-normal');
  if (d.downloadUrl) _updateUrl = d.downloadUrl;
  var req = (d.versionStatus === 'update_required');
  var hasUpdate = active && d.versionStatus && d.versionStatus !== 'ok';
  if (hasUpdate) {
    if (ver) ver.style.display = 'block';
    var vb = document.getElementById('ver-badge');
    if (vb) {
      vb.textContent = req ? 'Actualización OBLIGATORIA' : 'Nueva versión disponible';
      vb.className = 'lic-badge ' + (req ? 'nok' : 'ok');
    }
    var vm = document.getElementById('ver-msg');
    if (vm) vm.textContent = (d.versionMsg || '') + (d.latest ? (' (v' + d.latest + ')') : '');
    var dl = document.getElementById('ver-dl');
    if (dl) {
      if (d.downloadUrl) { dl.style.display = 'block'; dl.textContent = '↓ ' + d.downloadUrl; }
      else dl.style.display = 'none';
    }
    if (banner) {
      banner.style.display = 'block';
      if (req) { banner.style.background='rgba(239,68,68,0.2)'; banner.style.border='1px solid rgba(239,68,68,0.5)'; banner.style.color='#fca5a5'; }
      else     { banner.style.background='rgba(245,158,11,0.2)'; banner.style.border='1px solid rgba(245,158,11,0.5)';  banner.style.color='#fde68a'; }
      var ubt = document.getElementById('ub-text');
      if (ubt) {
        ubt.textContent =
          (req ? 'Actualización OBLIGATORIA' : 'Nueva versión disponible')
          + (d.latest ? ' — v' + d.latest : '') + '  ·  haz clic para actualizar';
      }
    }
  } else {
    if (ver) ver.style.display = 'none';
    if (banner) banner.style.display = 'none';
  }

  if (mmBlocked && mmNormal) {
    mmBlocked.style.display = req ? 'block' : 'none';
    mmNormal.style.display  = req ? 'none'  : 'block';
    if (req) {
      var mbv = document.getElementById('mm-blocked-ver');
      if (mbv) mbv.textContent = d.latest ? ('Nueva versión: v' + d.latest) : '';
    }
  }

  if (d.status === 'activating') {
    if (licPollTimer) clearTimeout(licPollTimer);
    licPollTimer = setTimeout(function(){ postMsg({action:'licensequery'}); }, 1500);
  } else if (licPollTimer) {
    clearTimeout(licPollTimer); licPollTimer = null;
  }
}

// ---- Validación de Licencia Universal Offline ----
function activateLicense() {
  var inp = document.getElementById('lic-key');
  var key = (inp ? inp.value : '').trim().toUpperCase();
  var badge = document.getElementById('lic-badge');
  var msg = document.getElementById('lic-msg');

  if (!key) {
    if (msg) msg.textContent = 'Por favor, introduce una clave de licencia.';
    return;
  }

  if (isUniversalKey(key)) {
    try {
      localStorage.setItem('mmats_license_key', UNIVERSAL_LICENSE_KEY);
      localStorage.setItem('mmats_license_active', '1');
    } catch(e) {}

    var licData = getUniversalLicensePayload();
    applyLicense(licData);
    if (msg) msg.textContent = '✅ ¡Licencia universal activada con éxito!';
    postMsg({action:'activate', key: UNIVERSAL_LICENSE_KEY});
  } else {
    if (badge) {
      badge.textContent = '❌ Clave no válida';
      badge.className = 'lic-badge nok';
    }
    if (msg) msg.textContent = 'Clave incorrecta. Clave universal: MMATS-SANTI-2026-UNIVERSAL';
  }
}

function deactivateLicense() {
  try {
    localStorage.removeItem('mmats_license_key');
    localStorage.removeItem('mmats_license_active');
  } catch(e) {}

  var badge = document.getElementById('lic-badge');
  if (badge) {
    badge.textContent = 'Sin licencia activa';
    badge.className = 'lic-badge nok';
  }
  var licInfo = document.getElementById('lic-info');
  var licAct = document.getElementById('lic-activate');
  if (licInfo) licInfo.style.display = 'none';
  if (licAct) licAct.style.display   = 'block';

  var msg = document.getElementById('lic-msg');
  if (msg) msg.textContent = 'Licencia desactivada en este equipo.';
  postMsg({action:'deactivate'});
}

// ---- Hotkeys ----
var HK_MAP = {
  menu:    {btn:'hk-menu',    key:'hotkey_menu'},
  mouse:   {btn:'hk-mouse',   key:'hotkey_interact'},
  zoomin:  {btn:'hk-zoomin',  key:'hotkey_zoom_in'},
  zoomout: {btn:'hk-zoomout', key:'hotkey_zoom_out'},
  gps:     {btn:'hk-gps',     key:'hotkey_gps'},
  volup:   {btn:'hk-volup',   key:'hotkey_vol_up'},
  voldown: {btn:'hk-voldown', key:'hotkey_vol_down'}
};

function vkName(vk) {
  if (vk === 0)               return '—';
  if (vk >= 112 && vk <= 123) return 'F' + (vk - 111);
  if (vk >= 48 && vk <= 57)   return String(vk - 48);
  if (vk >= 65 && vk <= 90)   return String.fromCodePoint(vk);
  if (vk >= 96 && vk <= 105)  return 'Num ' + (vk - 96);
  var M = {33:'Page Up',34:'Page Down',36:'Home',35:'End',45:'Insert',46:'Delete',
           9:'Tab',13:'Enter',32:'Espacio',20:'Bloq Mayús',144:'Bloq Num',145:'Bloq Despl',
           19:'Pausa',192:'` (Tilde)',189:'-',187:'=',219:'[',221:']',220:'\\',
           106:'Num *',107:'Num +',109:'Num -',110:'Num .',111:'Num /'};
  return M[vk] || ('VK ' + vk);
}

var hkRecording = null;

function hkRecord(slot) {
  if (!HK_MAP[slot]) return;
  if (hkRecording) {
    var prev = document.getElementById(HK_MAP[hkRecording].btn);
    if (prev) prev.classList.remove('recording');
  }
  hkRecording = slot;
  var btn = document.getElementById(HK_MAP[slot].btn);
  if (btn) { btn.classList.add('recording'); btn.textContent = 'Presiona una tecla...'; }
  postMsg({action:'hkRecordStart', key: HK_MAP[slot].key});
}

// ---- Receptor de mensajes C++ → JS ----
if (window.chrome && window.chrome.webview) {
  window.chrome.webview.addEventListener('message', function(e) {
    var data = e.data;
    if (!data) return;
    if (data.ev === 'state') {
      applyState(data);
    } else if (data.ev === 'mmState') {
      setMmRunning(!!data.running, data.url||'');
    } else if (data.ev === 'license') {
      applyLicense(data);
    } else if (data.ev === 'dbgRTs') {
      dbgRTs = data.rts || [];
      dbgRenderRTs();
    }
  });
}

// ---- Arrastre de ventana ----
(function() {
  var panel = document.getElementById('panel');
  var title = document.getElementById('title');
  var dragging = false, ox = 0, oy = 0;
  if (title && panel) {
    title.addEventListener('mousedown', function(e) {
      if (e.target.id === 'close') return;
      dragging = true;
      var r = panel.getBoundingClientRect();
      ox = e.clientX - r.left;
      oy = e.clientY - r.top;
      e.preventDefault();
    });
    document.addEventListener('mousemove', function(e) {
      if (!dragging) return;
      panel.style.left = (e.clientX - ox) + 'px';
      panel.style.top  = (e.clientY - oy) + 'px';
    });
    document.addEventListener('mouseup', function() { dragging = false; });
  }
})();

// ---- Inicialización ----
window.addEventListener('load', function() {
  updateSourceCards();
  buildMouseColors();
  
  // Pinta el último estado conocido para que el panel no salga en blanco, y
  // arranca el sondeo al servicio de audio inmersivo (él manda sobre esto).
  (function(){
    var cb = document.getElementById('immersive-toggle');
    if (cb) cb.checked = immersiveAudioOn();
    var lvl = 12;
    try { var g = parseInt(localStorage.getItem('mmats_immersive_level'), 10); if (Number.isFinite(g)) lvl = g; } catch(e){}
    var sl = document.getElementById('s-immersive');
    if (sl) sl.value = lvl;
    immersiveLevelLabel(lvl);
    immersiveStartPoll();
  })();
  
  // Cargar licencia guardada localmente
  try {
    var savedKey = localStorage.getItem('mmats_license_key');
    var isActive = localStorage.getItem('mmats_license_active');
    if (isActive === '1' || isUniversalKey(savedKey)) {
      applyLicense(getUniversalLicensePayload());
    } else {
      applyLicense({ status: 'notchecked', statusText: 'Sin licencia activa' });
    }
  } catch(e) {}

  postMsg({action:'getState'});
  postMsg({action:'licensequery'});
});

window.onerror = function(msg, src, line) {
  console.error('ovr:error ' + msg + ' @' + src + ':' + line);
  return false;
};
