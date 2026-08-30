
// Compensar DPI scaling do WebView2.
// Sem isso, em monitores 200% DPI o WebView2 renderiza em 2x density:
//   CSS viewport = tela_fisica / 2  → painel de 680px ocupa 1360px físicos (GIGANTE).
// Aplicar scale(1/dpr) no painel faz ele ocupar o mesmo espaço físico em qualquer DPI.
// transform-origin: center center garante que o centro visual continua centrado.
(function() {
  var dpr = window.devicePixelRatio || 1;
  var panel = document.getElementById('panel');
  if (panel && dpr > 1) {
    panel.style.transform = 'scale(' + (1 / dpr).toFixed(6) + ')';
  }
  // Expor DPR globalmente para debug
  window._lucidDPR = dpr;
})();

// =============================================================================
// Bridge JS↔C++ via window.chrome.webview (WebView2)
// =============================================================================
function postMsg(obj) {
  if (window.chrome && window.chrome.webview)
    window.chrome.webview.postMessage(obj);
}

// ---- Estado local sincronizado com C++ ----
var state = {
  mmRunning: false, mmUrl: '',
  zoom: 150,
  mouse_color: '#FFFFFF',
  rtHash: '0000000000000000'
};

// ---- Dispositivos conhecidos (RT hashes do jogo) ----
// Esses hashes identificam as telas de multimídia dentro do ETS2.
// Clicar seleciona qual tela do jogo receberá o conteúdo do browser.
var DEVICES = [
  {hash:'6E445921D4FBB174', icon:'📺', name:'Multimídia Central', info:'Volvo FH5/FH6, Scania'},
  {hash:'5891A3883361780B', icon:'🗺', name:'GPS Vidro',           info:'Genérico'},
  {hash:'F778E70824018E0B', icon:'📱', name:'GPS Celular',         info:'Genérico'},
  {hash:'E2A0D7B1DF649166', icon:'🖥', name:'Multimídia Compacta', info:'Scania (mod)'},
];

// ---- Tab switching ----
var TABS = ['mm','cfg','lic','links','dbg'];
var licTabActive = false;
function tab(id) {
  TABS.forEach(function(t) {
    document.getElementById('t-'+t).className = 'tab' + (t===id?' on':'');
    document.getElementById('p-'+t).className = 'pane' + (t===id?' on':'');
  });
  licTabActive = (id === 'lic');
  // estado fresco de licença ao abrir Licença OU Config (a aba Config tem a seção Temas PRO,
  // que precisa de d.themes atualizado pra liberar/travar).
  if (id === 'lic' || id === 'cfg') postMsg({action:'licensequery'});
  // DEBUG: só faz sentido pollar a lista de RTs com a aba aberta.
  dbgTabActive = (id === 'dbg');
  if (id === 'dbg') { if (dbgScanning) { dbgStartPoll(); postMsg({action:'dbgList'}); } dbgRenderRTs(); }
  else { dbgStopPoll(); }
}
// Refresca o status enquanto a aba Licença está aberta — pega recuperação automática
// (servidor voltou), ban, expiração e mudança de versão AO VIVO, sem reabrir a aba.
setInterval(function(){ if (licTabActive) postMsg({action:'licensequery'}); }, 4000);

// ---- Close ----
function closeMenu() { postMsg({action:'close'}); }
document.getElementById('bd').addEventListener('click', function(e) {
  if (e.target === this) closeMenu();
});

// ---- Multimídia: INICIAR / PARAR ----
function mmStart() {
  var alert = document.getElementById('mm-alert');
  var zeroHash = !state.rtHash || state.rtHash === '0000000000000000';
  if (zeroHash) {
    // Sem dispositivo selecionado — mostrar aviso
    if (alert) {
      alert.style.display = '';
      alert.textContent = '⚠ Selecione um dispositivo abaixo antes de iniciar.';
    }
    return;
  }
  if (alert) alert.style.display = 'none';
  // Envia hash junto para reativar o RT mesmo após um PARAR
  postMsg({action:'startMm', hash:state.rtHash});
  setMmRunning(true, 'lucidgfx_home.html');
}
function mmStop() {
  postMsg({action:'stopMm'});
  setMmRunning(false, '');
  // NÃO apaga state.rtHash: próximo INICIAR vai lembrar o dispositivo
}

function setMmRunning(running, url) {
  state.mmRunning = running;
  state.mmUrl     = url || '';
  var btn1 = document.getElementById('btn-iniciar');
  var btn2 = document.getElementById('btn-parar');
  var title = document.getElementById('mm-status-title');
  var info  = document.getElementById('mm-status-info');
  if (running) {
    if (btn1) btn1.style.display = 'none';
    if (btn2) btn2.style.display = '';
    if (title) title.textContent = '▶ Ativo';
    if (info)  info.textContent  = url || 'Em execução';
    document.getElementById('fstatus').textContent = 'Multimídia ativa';
  } else {
    if (btn1) btn1.style.display = '';
    if (btn2) btn2.style.display = 'none';
    if (title) title.textContent = '⏸ Parado';
    if (info)  info.textContent  = 'Clique em INICIAR para ativar';
    document.getElementById('fstatus').textContent = 'LucidGFX ativo';
  }
  // Atualizar hash cards
  updateSourceCards();
}

// ---- Zoom ----
function zoomAdj(delta) {
  var inp = document.getElementById('zoom-val');
  var sl  = document.getElementById('s-zoom');
  var v   = Math.max(10, Math.min(500, parseInt(inp.value||150,10) + delta * 10));
  inp.value = v; if (sl) sl.value = v;
  postMsg({action:'setZoom', val:v});
}
function zoomSet(v) {
  v = Math.max(10, Math.min(500, parseInt(v,10)||150));
  var inp = document.getElementById('zoom-val');
  var sl  = document.getElementById('s-zoom');
  if (inp) inp.value = v; if (sl) sl.value = v;
  postMsg({action:'setZoom', val:v});
}
// ---- Volume da multimídia (0-100). C++ persiste mm_audio_volume + aplica via WASAPI (nudge). ----
function volAdj(delta) {
  var vv = document.getElementById('vol-val');
  var vs = document.getElementById('s-vol');
  // NÃO usar (parseInt(...)||100): em 0% o parseInt dá 0, que é falsy, e o ||100 viraria 100
  // (bug: no 0 o "-" voltava pra 90). Ler NaN-safe preservando o zero.
  var cur = vs ? parseInt(vs.value, 10) : 100;
  if (!Number.isFinite(cur)) cur = 100;
  var v = Math.max(0, Math.min(100, cur + delta));
  if (vv) vv.textContent = v + '%';
  if (vs) vs.value = v;
  postMsg({action:'setVol', val:v});
}
// oninput (arrastando): só atualiza o rótulo local — NÃO manda pro C++ (senão seria saveToFile +
// enumeração WASAPI a cada pixel do arraste). A aplicação/persistência vai no 'change' (soltar).
function volLabel(v) {
  var vv = document.getElementById('vol-val');
  if (vv) vv.textContent = (Math.max(0, Math.min(100, parseInt(v,10)||0))) + '%';
}
function volSlider(v) {
  v = Math.max(0, Math.min(100, parseInt(v,10)||0));
  var vv = document.getElementById('vol-val');
  if (vv) vv.textContent = v + '%';
  postMsg({action:'setVol', val:v});
}
// ---- Sensibilidade do mouse (cursor da multimídia) ----
// Setting em % (100 = 1.0x). O C++ lê mouse_sensitivity e aplica no delta do cursor.
function sensSet(v) {
  var pct = Math.max(30, Math.min(200, parseInt(v, 10) || 100));
  var lbl = document.getElementById('sens-val');
  if (lbl) lbl.textContent = (pct / 100).toFixed(1) + 'x';
  postMsg({action:'setSetting', key:'mouse_sensitivity', val: pct});  // C++ persiste (saveToFile)
}

// ---- Cor do cursor F8 (bolinha) ----
// Swatches fixos; a cor escolhida vira o hex enviado ao C++ (setMouseColor -> setCursorColorHex).
// Usa swatches em vez de <input type=color> porque o host WebView2 e off-screen/composto e o
// popup nativo do color-picker nao aparece/captura direito.
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
      ';border:2px solid rgba(255,255,255,0.15);box-sizing:border-box;';
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
    els[i].style.boxShadow   = on ? '0 0 0 2px #fff' : 'none';
    els[i].style.borderColor = on ? '#fff' : 'rgba(255,255,255,0.15)';
  }
}
function mouseColorSet(c) {
  state.mouse_color = c;
  highlightMouseColor(c);
  postMsg({action:'setMouseColor', val: c});  // C++ persiste (mouse_color) + aplica ao vivo
}

// ---- Links (aba Links) ----
// Cada entrada vira um card clicável que abre a URL no navegador padrão do PC
// (postMsg openUrl -> ShellExecute no C++). Adicionar link novo = só mais um item aqui.
var LINKS = [
  { title:'Site oficial', desc:'gfxmods.com.br', url:'https://gfxmods.com.br', color:'#13131a',
    icon:'<img src="data:image/png;base64,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" alt="GFXMods">' },
  { title:'Discord', desc:'Entre na comunidade', url:'https://discord.gg/v4jTeFByU2', color:'#5865F2',
    icon:'<svg viewBox="0 0 24 24"><path d="M20.317 4.369a19.79 19.79 0 00-4.885-1.515.074.074 0 00-.079.037c-.211.375-.444.865-.608 1.25a18.27 18.27 0 00-5.487 0 12.64 12.64 0 00-.617-1.25.077.077 0 00-.079-.037A19.736 19.736 0 003.677 4.37a.07.07 0 00-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 00.031.057 19.9 19.9 0 005.993 3.03.078.078 0 00.084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 00-.041-.106 13.107 13.107 0 01-1.872-.892.077.077 0 01-.008-.128 10.2 10.2 0 00.372-.292.074.074 0 01.077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 01.078.01c.12.098.246.198.373.292a.077.077 0 01-.006.127 12.3 12.3 0 01-1.873.892.077.077 0 00-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 00.084.028 19.839 19.839 0 006.002-3.03.077.077 0 00.032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 00-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/></svg>' },
  { title:'Instagram', desc:'@ggfxmods', url:'https://www.instagram.com/ggfxmods/', color:'linear-gradient(45deg,#f09433,#e6683c,#dc2743,#cc2366,#bc1888)',
    icon:'<svg viewBox="0 0 24 24"><path d="M12 2.16c3.2 0 3.58.01 4.85.07 1.17.05 1.8.25 2.23.41.56.22.96.48 1.38.9.42.42.68.82.9 1.38.16.42.36 1.06.41 2.23.06 1.27.07 1.65.07 4.85s-.01 3.58-.07 4.85c-.05 1.17-.25 1.8-.41 2.23-.22.56-.48.96-.9 1.38-.42.42-.82.68-1.38.9-.42.16-1.06.36-2.23.41-1.27.06-1.65.07-4.85.07s-3.58-.01-4.85-.07c-1.17-.05-1.8-.25-2.23-.41-.56-.22-.96-.48-1.38-.9-.42-.42-.68-.82-.9-1.38-.16-.42-.36-1.06-.41-2.23-.06-1.27-.07-1.65-.07-4.85s.01-3.58.07-4.85c.05-1.17.25-1.8.41-2.23.22-.56.48-.96.9-1.38.42-.42.82-.68 1.38-.9.42-.16 1.06-.36 2.23-.41 1.27-.06 1.65-.07 4.85-.07M12 0C8.74 0 8.33.01 7.05.07 5.78.13 4.9.33 4.14.63c-.79.31-1.46.72-2.13 1.38C1.35 2.68.94 3.35.63 4.14.33 4.9.13 5.78.07 7.05.01 8.33 0 8.74 0 12s.01 3.67.07 4.95c.06 1.27.26 2.15.56 2.91.31.79.72 1.46 1.38 2.13.67.66 1.34 1.07 2.13 1.38.76.3 1.64.5 2.91.56C8.33 23.99 8.74 24 12 24s3.67-.01 4.95-.07c1.27-.06 2.15-.26 2.91-.56.79-.31 1.46-.72 2.13-1.38.66-.67 1.07-1.34 1.38-2.13.3-.76.5-1.64.56-2.91.06-1.28.07-1.69.07-4.95s-.01-3.67-.07-4.95c-.06-1.27-.26-2.15-.56-2.91-.31-.79-.72-1.46-1.38-2.13C21.32 1.35 20.65.94 19.86.63 19.1.33 18.22.13 16.95.07 15.67.01 15.26 0 12 0z"/><path d="M12 5.84A6.16 6.16 0 1018.16 12 6.16 6.16 0 0012 5.84zM12 16a4 4 0 114-4 4 4 0 01-4 4z"/><circle cx="18.41" cy="5.59" r="1.44"/></svg>' },
  { title:'Funcionalidades', desc:'Vídeo no YouTube', url:'https://www.youtube.com/watch?v=Uzd4Gpse-aY', color:'#FF0000',
    icon:'<svg viewBox="0 0 24 24"><path d="M23.498 6.186a3.016 3.016 0 00-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 00.502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 002.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 002.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>' }
];
function buildLinks() {
  var box = document.getElementById('links-list');
  if (!box) return;
  box.innerHTML = '';
  LINKS.forEach(function(l) {
    var card = document.createElement('div');
    card.className = 'link-card';
    card.innerHTML =
      '<div class="link-ico" style="background:' + l.color + '">' + l.icon + '</div>' +
      '<div class="link-txt"><div class="link-title">' + l.title + '</div>' +
      '<div class="link-desc">' + l.desc + '</div></div>' +
      '<div class="link-arrow">↗</div>';
    card.addEventListener('mousedown', function(e) { e.preventDefault(); openLink(l.url); });
    box.appendChild(card);
  });
}
// Toggle "desligar multimídia com o caminhão desligado" (aba Config). C++ persiste + aplica.
function powerGateSet(on) { postMsg({action:'setPowerGate', val: on ? '1' : '0'}); }
// Toggle "aviso 'Mouse ativo' na tela" (aba Config). C++ persiste; o overlay lê por-frame.
function mouseHintSet(on) { postMsg({action:'setMouseHint', val: on ? '1' : '0'}); }

function openLink(url) { postMsg({action:'openUrl', val: url}); }

// Update: link pro dashboard (onde se baixa a versão nova). A policy pode mandar um download_url
// próprio (d.downloadUrl); senão cai no dashboard padrão. Abre no navegador (ação openUrl).
var _updateUrl = 'https://gfxmods.com.br/dashboard';
function openUpdate() { postMsg({action:'openUrl', val: _updateUrl}); }

function zoomSlider(v) {
  var inp = document.getElementById('zoom-val');
  if (inp) inp.value = v;
  postMsg({action:'setZoom', val:parseInt(v,10)});
}

// ---- Selecionar dispositivo (RT hash do jogo) ----
function selectDevice(dev) {
  state.rtHash = dev.hash;
  postMsg({action:'selectHash', hash:dev.hash});
  updateSourceCards();
}

// ---- Populador de hash cards ----
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
// DEBUG — scanner de RTs (só no build de diagnóstico; aba escondida por state.debug)
// =============================================================================
var dbgScanning = false;   // scan ligado no C++
var dbgRTs = [];           // último snapshot recebido
var dbgPollTimer = null;   // timer de polling da lista (só roda com a aba DEBUG aberta)
var dbgTabActive = false;

function dbgStartPoll() {
  if (dbgPollTimer) return;
  dbgPollTimer = setInterval(function() { postMsg({action:'dbgList'}); }, 800);
}
function dbgStopPoll() {
  if (dbgPollTimer) { clearInterval(dbgPollTimer); dbgPollTimer = null; }
}
// Liga/desliga a coleta no C++. O scan continua rodando mesmo saindo da aba (pra acumular
// enquanto o usuário dirige); só o polling da UI é pausado ao trocar de aba.
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
// Testa pintar um RT da lista: vira o alvo + aplica o hitIndex atual + inicia a multimídia.
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
      (dbgScanning ? 'Nenhum RT ainda — feche o menu e olhe pro painel do caminhão.' : 'Ligue o scan pra listar.') +
      '</div>';
    return;
  }
  box.innerHTML = '';
  list.forEach(function(rt) {
    var active = (state.rtHash || '').toUpperCase() === rt.hash.toUpperCase();
    var row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:10px;' +
      'padding:8px 10px;margin-bottom:6px;border-radius:8px;' +
      'background:' + (active ? 'rgba(126,184,255,0.14)' : 'rgba(255,255,255,0.04)') + ';' +
      'border:1px solid ' + (active ? '#7eb8ff' : 'rgba(255,255,255,0.08)') + ';';
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

// ---- Aplicar estado completo recebido de C++ ----
function applyState(s) {
  if (!s) return;
  // RT hash ativo
  if (s.rtHash) { state.rtHash = s.rtHash; }
  // Zoom
  if (s.zoom) {
    var zi = document.getElementById('zoom-val');
    var zs = document.getElementById('s-zoom');
    if (zi) zi.value = s.zoom;
    if (zs) zs.value = s.zoom;
  }
  // Volume da multimídia
  if (typeof s.volLevel === 'number') {
    var vv = document.getElementById('vol-val');
    var vs = document.getElementById('s-vol');
    if (vv) vv.textContent = s.volLevel + '%';
    if (vs) vs.value = s.volLevel;
  }
  // Sensibilidade do mouse
  if (typeof s.mouseSens === 'number') {
    var ss = document.getElementById('s-sens');
    var sl = document.getElementById('sens-val');
    if (ss) ss.value = s.mouseSens;
    if (sl) sl.textContent = (s.mouseSens / 100).toFixed(1) + 'x';
  }
  // Cor do cursor (bolinha F8)
  if (typeof s.mouseColor === 'string' && s.mouseColor) {
    state.mouse_color = s.mouseColor;
    highlightMouseColor(s.mouseColor);
  }
  // Versão real do build no cabeçalho (em vez do "v1.0" antigo chumbado)
  if (typeof s.version === 'string' && s.version) {
    var hv = document.getElementById('hdr-ver');
    if (hv) hv.textContent = 'v' + s.version;
  }
  // Aba DEBUG: só aparece no build de diagnóstico (C++ manda debug=true só com VERBOSE_LOGS).
  if (typeof s.debug !== 'undefined') {
    var td = document.getElementById('t-dbg');
    if (td) td.style.display = s.debug ? '' : 'none';
  }
  // Toggle: desligar multimídia com o caminhão desligado
  if (typeof s.powerGate !== 'undefined') {
    var pg = document.getElementById('pg-toggle');
    if (pg) pg.checked = (s.powerGate === 1 || s.powerGate === '1' || s.powerGate === true);
  }
  // Toggle: aviso "Mouse ativo" na tela
  if (typeof s.mouseHint !== 'undefined') {
    var mh = document.getElementById('mh-toggle');
    if (mh) mh.checked = (s.mouseHint === 1 || s.mouseHint === '1' || s.mouseHint === true);
  }
  // Multimídia
  setMmRunning(!!s.mmRunning, s.mmUrl||'');
  // Hotkeys — reflete o valor salvo nos botões (só as 2 reais). Como a captura é no C++,
  // o getState pós-rebind chega aqui e é quando encerramos o estado visual "Pressione...".
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
  // Volume (Ctrl + tecla) — prefixa "Ctrl + " pra deixar claro que o modificador é fixo.
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
  // Atualizar cards com hash ativo
  updateSourceCards();
}

// ---- Licença ----
var LIC_MAP = {
  ok:'✅ Licença ativa', activating:'⏳ Ativando...', invalid:'❌ Chave inválida',
  hwid_mismatch:'⚠️ PC não autorizado', expired:'⏳ Licença expirada',
  banned:'🚫 Licença revogada', servererror:'📡 Erro de conexão', notchecked:'Sem licença ativa'
};
var licPollTimer = null;

// ---- Temas PRO (fundo customizado da multimídia) ----
// A seleção do arquivo é feita no C++ (GetOpenFileNameW ancorado na janela do jogo) — o
// <input type=file> não funciona no host WebView2 off-screen. A trava PRO real é nativa;
// aqui só refletimos o estado (applyThemesGate) e mostramos feedback (_lgfxBgResult).
function bgPick() {
  var st = document.getElementById('bg-status');
  if (st) st.textContent = 'Abrindo seletor de arquivo…';
  postMsg({action:'pickBackground'});
}
function bgClear() { postMsg({action:'clearBackground'}); }
window._lgfxBgResult = function(kind) {
  var st = document.getElementById('bg-status');
  if (!st) return;
  var m = {
    ok:       '✅ Fundo aplicado!',
    cleared:  'Fundo removido.',
    nopro:    '🔒 Disponível só no plano PRO.',
    badtype:  '❌ Formato inválido — use JPG, PNG ou WebP.',
    toobig:   '❌ Arquivo muito grande (máximo 8 MB).',
    copyfail: '❌ Não consegui ler/copiar o arquivo.'
  };
  st.textContent = m[kind] || '';
};
// Habilita/trava a seção Temas conforme o entitlement themes (d.themes vindo da licença).
function applyThemesGate(allowed) {
  var on = (allowed !== false);  // undefined (ainda sem licença) => não trava
  var lock = document.getElementById('theme-lock');
  if (lock) lock.style.display = on ? 'none' : 'block';
  ['bg-pick','bg-clear'].forEach(function(id) {
    var b = document.getElementById(id);
    if (b) { b.disabled = !on; b.style.opacity = on ? '1' : '0.4'; b.style.pointerEvents = on ? 'auto' : 'none'; }
  });
}

function applyLicense(d) {
  var badge = document.getElementById('lic-badge');
  badge.textContent = LIC_MAP[d.status] || d.statusText || d.status;
  badge.className = 'lic-badge ' + (d.status === 'ok' ? 'ok' : 'nok');
  document.getElementById('lic-msg').textContent = d.error || '';

  var active = (d.status === 'ok');
  document.getElementById('lic-info').style.display     = active ? 'block' : 'none';
  document.getElementById('lic-activate').style.display = active ? 'none'  : 'block';
  if (active) {
    document.getElementById('lic-edition').textContent = d.edition || '—';
    document.getElementById('lic-days').textContent =
      (typeof d.days === 'number' && d.days < 0) ? 'Permanente' : ((d.days||0) + ' dias');
  }
  document.getElementById('lic-hwid').textContent = 'HWID: ' + (d.hwid || '—');
  applyThemesGate(d.themes);  // libera/trava a seção Temas (PRO) na aba Config

  // Versão / atualização
  var ver       = document.getElementById('lic-ver');
  var banner    = document.getElementById('update-banner');
  var mmBlocked = document.getElementById('mm-blocked');
  var mmNormal  = document.getElementById('mm-normal');
  if (d.downloadUrl) _updateUrl = d.downloadUrl;   // policy pode mandar um link próprio de download
  var req = (d.versionStatus === 'update_required');
  var hasUpdate = active && d.versionStatus && d.versionStatus !== 'ok';
  if (hasUpdate) {
    ver.style.display = 'block';
    var vb = document.getElementById('ver-badge');
    vb.textContent = req ? 'Atualização OBRIGATÓRIA' : 'Nova versão disponível';
    vb.className = 'lic-badge ' + (req ? 'nok' : 'ok');
    document.getElementById('ver-msg').textContent =
      (d.versionMsg || '') + (d.latest ? (' (v' + d.latest + ')') : '');
    var dl = document.getElementById('ver-dl');
    if (d.downloadUrl) { dl.style.display = 'block'; dl.textContent = '↓ ' + d.downloadUrl; }
    else dl.style.display = 'none';
    // Banner do topo (todas as abas): VERMELHO (obrigatória) / AMARELO (opcional). Linka p/ dashboard.
    if (banner) {
      banner.style.display = 'block';
      if (req) { banner.style.background='rgba(255,71,87,0.16)'; banner.style.border='1px solid rgba(255,71,87,0.45)'; banner.style.color='#ffd3d7'; }
      else     { banner.style.background='rgba(255,193,7,0.16)'; banner.style.border='1px solid rgba(255,193,7,0.5)';  banner.style.color='#ffe28a'; }
      document.getElementById('ub-text').textContent =
        (req ? 'Atualização OBRIGATÓRIA' : 'Nova versão disponível')
        + (d.latest ? ' — v' + d.latest : '') + '  ·  toque para atualizar';
    }
  } else {
    ver.style.display = 'none';
    if (banner) banner.style.display = 'none';
  }
  // Aba Multimídia: bloqueio total só na atualização OBRIGATÓRIA (o mod já está desligado);
  // caso contrário mostra os controles normais.
  if (mmBlocked && mmNormal) {
    mmBlocked.style.display = req ? 'block' : 'none';
    mmNormal.style.display  = req ? 'none'  : 'block';
    if (req) {
      var mbv = document.getElementById('mm-blocked-ver');
      if (mbv) mbv.textContent = d.latest ? ('Nova versão: v' + d.latest) : '';
    }
  }

  // Enquanto ativando, faz polling até resolver.
  if (d.status === 'activating') {
    if (licPollTimer) clearTimeout(licPollTimer);
    licPollTimer = setTimeout(function(){ postMsg({action:'licensequery'}); }, 1500);
  } else if (licPollTimer) {
    clearTimeout(licPollTimer); licPollTimer = null;
  }
}

function activateLicense() {
  var key = (document.getElementById('lic-key').value || '').trim().toUpperCase();
  if (!key) return;
  postMsg({action:'activate', key:key});
}

// Remove a licença ativa deste PC (permite ativar outra chave). A remoção é async (thread de
// licença do C++), então re-consulta o estado até refletir "sem licença".
function deactivateLicense() {
  var badge = document.getElementById('lic-badge');
  if (badge) badge.textContent = 'Removendo...';
  postMsg({action:'deactivate'});
  setTimeout(function(){ postMsg({action:'licensequery'}); }, 400);
  setTimeout(function(){ postMsg({action:'licensequery'}); }, 1200);
}

// ---- Hotkeys (rebind) ----
// Teclas com efeito real no backend: navegação ('menu'/'mouse') e zoom da multimídia
// ('zoomin'/'zoomout'). A captura é no C++ (WndProc); aqui só o valor salvo é exibido.
var HK_MAP = {
  menu:    {btn:'hk-menu',    key:'hotkey_menu'},
  mouse:   {btn:'hk-mouse',   key:'hotkey_interact'},
  zoomin:  {btn:'hk-zoomin',  key:'hotkey_zoom_in'},
  zoomout: {btn:'hk-zoomout', key:'hotkey_zoom_out'},
  gps:     {btn:'hk-gps',     key:'hotkey_gps'},
  volup:   {btn:'hk-volup',   key:'hotkey_vol_up'},
  voldown: {btn:'hk-voldown', key:'hotkey_vol_down'}
};

// VK code → nome amigável (espelha overlay.cpp vkToName; só as teclas usáveis como hotkey).
function vkName(vk) {
  if (vk === 0)               return '—';                        // desativado
  if (vk >= 112 && vk <= 123) return 'F' + (vk - 111);          // F1..F12
  if (vk >= 48 && vk <= 57)   return String(vk - 48);            // 0..9
  if (vk >= 65 && vk <= 90)   return String.fromCodePoint(vk);   // A..Z
  if (vk >= 96 && vk <= 105)  return 'Num ' + (vk - 96);         // Numpad 0..9
  var M = {33:'Page Up',34:'Page Down',36:'Home',35:'End',45:'Insert',46:'Delete',
           9:'Tab',13:'Enter',32:'Space',20:'Caps Lock',144:'Num Lock',145:'Scroll Lock',
           19:'Pause',192:'` (Til)',189:'-',187:'=',219:'[',221:']',220:'\\',
           106:'Num *',107:'Num +',109:'Num -',110:'Num .',111:'Num /'};
  return M[vk] || ('VK ' + vk);
}

var hkRecording = null;  // qual slot ('menu'/'mouse') está gravando, ou null

// A captura da tecla é feita no C++ (WndProc), não aqui — PostMessage de WM_KEYDOWN cru
// nem sempre gera keydown no DOM do Chromium. Aqui só sinalizamos e mostramos "Pressione...".
// O C++ persiste a tecla e dispara um getState, que atualiza o botão via applyState.
function hkRecord(slot) {
  if (!HK_MAP[slot]) return;
  if (hkRecording) {  // cancela gravação anterior visualmente
    var prev = document.getElementById(HK_MAP[hkRecording].btn);
    if (prev) prev.classList.remove('recording');
  }
  hkRecording = slot;
  var btn = document.getElementById(HK_MAP[slot].btn);
  if (btn) { btn.classList.add('recording'); btn.textContent = 'Pressione...'; }
  postMsg({action:'hkRecordStart', key: HK_MAP[slot].key});
}

// ---- Receiver de mensagens C++ → JS ----
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

// ---- Drag do painel pela barra de título ----
(function() {
  var panel = document.getElementById('panel');
  var title = document.getElementById('title');
  var dragging = false, ox = 0, oy = 0;
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
})();

// ---- Init ----
window.addEventListener('load', function() {
  updateSourceCards();
  buildMouseColors();
  buildLinks();
  // Solicitar estado atual de C++
  postMsg({action:'getState'});
  postMsg({action:'licensequery'});
});

window.onerror = function(msg, src, line) {
  console.error('ovr:error ' + msg + ' @' + src + ':' + line);
  return false;
};
