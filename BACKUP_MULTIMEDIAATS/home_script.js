
var pendingUrl = null;
var pendingName = null;

// Loading: overlay com spinner mostrado NA HORA que abre um app / navega, pra dar
// feedback imediato enquanto o WebView carrega a página (que demora — YouTube etc).
// A página nova substitui tudo ao carregar. Fallback de 8s remove se algo travar.
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
    + 'border:5px solid rgba(155,95,255,0.25);border-top-color:#9B5FFF;border-radius:50%;'
    + 'animation:_lgfxspin 0.7s linear infinite;';
  o.appendChild(sp);
  document.documentElement.appendChild(o);
  setTimeout(function(){ var el = document.getElementById('_lgfx_load'); if (el) el.remove(); }, 8000);
}

// ---- Gating por plano (entitlements vindos do C++ via _lgfxOnLicense) ----
// A trava REAL é nativa (o C++ cancela a navegação/ação); aqui é só a UX: escurece os
// cards travados e mostra um aviso ao clicar. s.entitlements.enforced=false (dev) => nada trava.
var _entitlements = null;
function isFeatLocked(feat) {
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
// Retorna true (e mostra aviso) se a feature está travada pelo plano.
function featBlocked(feat, name) {
  if (!isFeatLocked(feat)) return false;
  showFeatToast('🔒 ' + name + ' faz parte de um plano superior. Faça upgrade para desbloquear.');
  return true;
}

// Modo painel: a home está rodando DENTRO do split.html (?pane=1). Nesse modo,
// abrir um app navega o próprio iframe (sem modal de split), e o app "Chat" some
// (evita split-dentro-de-split). O chat já está no painel ao lado.
var PANE_MODE = new URLSearchParams(location.search).get('pane') === '1';

console.log('[LUCID] Script carregado, viewport: ' + window.innerWidth + 'x' + window.innerHeight + ' pane=' + PANE_MODE);

// Relógio do painel: horário do JOGO (via plugin de telemetria SCS, lido pela
// dxgi.dll) quando disponível; senão relógio do PC. O C++ (TelemetryTime) chama
// _lgfxSetGameTime a cada minuto in-game + keep-alive. Se parar de chegar por
// >12s (plugin ausente/menu longo/game fechado), volta pro relógio do PC.
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

// Abre o modal de escolha (Tela cheia/Split) — OU, em modo painel, abre direto no iframe.
function go(url, name, feat) {
  console.log('[LUCID] go() chamada: ' + url);
  // Trava por plano (defesa de UX; a trava real é nativa no C++).
  if (feat && featBlocked(feat, name || feat)) return;
  // Em modo painel (dentro do split), o app abre no próprio iframe. O chat do lado
  // fica intacto. Sem modal — já estamos em split.
  if (PANE_MODE) {
    showLoad();
    window.location.href = url;
    return;
  }
  pendingUrl = url;
  pendingName = name || url.replace(/^https?:\/\//, '').split('/')[0];
  document.getElementById('modal-app-name').textContent = pendingName;
  document.getElementById('app-modal').classList.add('show');
  console.log('[LUCID] Modal aberto');
}

// Fecha o modal
function closeModal() {
  document.getElementById('app-modal').classList.remove('show');
  pendingUrl = null;
  pendingName = null;
}

// Lança o app com ou sem split
function launchApp(useSplit) {
  if (!pendingUrl) return;
  
  // Enviar configuração de split para o C++
  // ratio=50 (50% GPS, 50% browser), gpsOnLeft=1, gpsHash=0 (própria tela)
  var splitEnabled = useSplit ? 1 : 0;
  var f = document.createElement('iframe');
  f.style.display = 'none';
  f.src = 'lucidgfx://action/split/' + splitEnabled + '/1/50/0';
  document.body.appendChild(f);
  
  // Navegar após pequeno delay para garantir que o split foi configurado
  var url = pendingUrl;
  showLoad();  // feedback imediato ao escolher Tela cheia/Split
  setTimeout(function() {
    f.remove();
    window.location.href = url;
  }, 50);

  closeModal();
}

// Ponto de entrada do banco de calibracao — chamado pelo DLL quando detecta o RT.
// Nao faz nada neste layout (fullscreen), mas evita erros se o DLL injetar.
window._lgfxSetWindow = function(yStart, yEnd) {};

// Modo painel (dentro do split): esconder apps que não fazem sentido aqui.
// - Chat: já está no painel ao lado (evita split-dentro-de-split).
// - GPS: usa split-shader do jogo (não funciona dentro de iframe).
if (PANE_MODE) {
  // Esconde só o Chat (já está no painel ao lado). O GPS FICA visível — no pane
  // ele dispara splitchatgps (mostra o GPS do jogo no painel, chat intacto).
  var hideChat = document.getElementById('app-chat');
  if (hideChat) hideChat.style.display = 'none';
}

// GPS: no modo pane (split com chat) abre o GPS do jogo NO PAINEL (chat continua);
// fora do split, modo GPS normal (tela cheia + barra).
function gpsClick() {
  if (PANE_MODE) sendAction('splitchatgps');
  else showGps();
}

// Mostra o GPS do jogo (barra inferior, GPS 92%)
function showGps() {
  console.log('[LUCID] showGps() - split vertical');
  
  // Esconder tudo
  document.getElementById('grid').style.display = 'none';
  document.getElementById('sb').style.display = 'none';
  document.getElementById('dots').style.display = 'none';
  
  // Fundo para a barra inferior
  document.body.style.background = '#161b22';
  document.body.style.backgroundImage = 'none';
  
  // Mostrar botão
  document.getElementById('gps-mode').classList.add('active');
  
  // Split vertical: GPS em cima (92%), barra embaixo (8%)
  // Formato: enabled/gpsTop/ratio/hash/vertical
  var f = document.createElement('iframe');
  f.style.display = 'none';
  f.src = 'lucidgfx://action/split/1/1/92/0/1';
  document.body.appendChild(f);
  setTimeout(function() { f.remove(); }, 100);
}

// Sai do modo GPS e volta para Home
function exitGpsMode() {
  console.log('[LUCID] exitGpsMode() - enviando action/resethome');
  // Esconde o #gps-mode NA HORA: senão o botão HOME (agora em tamanho normal, mas o
  // WebView ainda está grande enquanto a home recarrega) fica ocupando a tela inteira
  // como uma tela "🏠 HOME" gigante até a home nova carregar.
  var g = document.getElementById('gps-mode');
  if (g) g.classList.remove('active');
  showLoad();  // spinner cobre o gap até a home carregar
  // Usar action especial que desativa split e força reload
  window.location.href = 'lucidgfx://action/resethome';
}

// Volta para Home (desativa split e recarrega)
function goHome() {
  console.log('[LUCID] goHome() - enviando action/resethome');
  window.location.href = 'lucidgfx://action/resethome';
}

// Minimiza o jogo (Alt+Tab)
function doAltTab() {
  console.log('[LUCID] doAltTab() - minimizando jogo');
  window.location.href = 'lucidgfx://action/alttab';
}

// ---- Licença ----
// Envia uma action sem navegar (via iframe oculto), para não sair da home.
function sendAction(path) {
  var f = document.createElement('iframe');
  f.style.display = 'none';
  f.src = 'lucidgfx://action/' + path;
  document.body.appendChild(f);
  setTimeout(function() { f.remove(); }, 100);
}

function openLicense() {
  document.getElementById('lic-modal').classList.add('show');
  sendAction('licensequery');   // o DLL responde via window._lgfxOnLicense(...)
}

function closeLicense() {
  document.getElementById('lic-modal').classList.remove('show');
}

function activateLicense() {
  var key = (document.getElementById('lic-key').value || '').trim();
  if (!key) { document.getElementById('lic-status').textContent = 'Digite uma chave'; return; }
  document.getElementById('lic-status').textContent = 'Ativando...';
  document.getElementById('lic-activate-btn').style.opacity = '0.5';
  sendAction('activate/' + encodeURIComponent(key));
}

// ---- Chat (widget estilo Streamlabs/OBS, só chat) ----
var chatPlatform = 'twitch';
var chatLayout = 'full';   // 'full' = tela cheia | 'split' = dividido com o GPS
var chatSavedChannels = { twitch: '', youtube: '' };

function setChatPlatform(plat) {
  chatPlatform = plat;
  var tw = document.getElementById('chat-plat-twitch');
  var yt = document.getElementById('chat-plat-youtube');
  // Realce por classe .selected (borda+fundo+glow), não mais opacidade sutil.
  tw.classList.toggle('selected', plat === 'twitch');
  yt.classList.toggle('selected', plat === 'youtube');
  tw.style.opacity = yt.style.opacity = '1';
  document.getElementById('chat-channel').value = chatSavedChannels[plat] || '';
  document.getElementById('chat-channel').placeholder = (plat === 'youtube') ? '@seu_canal' : 'seu_canal';
  console.log('[LUCID] chat platform selecionada = ' + plat);
}

function setChatLayout(layout) {
  chatLayout = layout;
  var full  = document.getElementById('chat-layout-full');
  var split = document.getElementById('chat-layout-split');
  full.classList.toggle('selected',  layout === 'full');
  split.classList.toggle('selected', layout === 'split');
  full.style.opacity = split.style.opacity = '1';
  console.log('[LUCID] chat layout selecionado = ' + layout);
}

function openChat() {
  if (featBlocked('chat', 'Chat ao vivo')) return;
  document.getElementById('chat-modal').classList.add('show');
  setChatPlatform(chatPlatform);
  setChatLayout(chatLayout);
  sendAction('chatquery');   // o DLL responde via window._lgfxOnChatConfig(...)
}
function closeChat() {
  document.getElementById('chat-modal').classList.remove('show');
}

// Modo split → abre o shell split.html (chat | conteúdo, na mesma página).
// Modo split → splitchat2 (2 WebViews): chat de um lado, HOME do outro (a pessoa
//   escolhe o app na home, que abre no painel; chat fica intacto).
// Modo full  → chat ocupando a tela toda.
function openChatChannel() {
  var chan = (document.getElementById('chat-channel').value || '').trim().replace(/^#/, '');
  if (!chan) return;
  closeChat();
  showLoad();  // feedback imediato: abrir chat navega o WebView (demora)
  if (chatLayout === 'split') {
    sendAction('splitchat2/' + chatPlatform + '/' + encodeURIComponent(chan));
  } else {
    sendAction('chat/' + chatPlatform + '/' + encodeURIComponent(chan));
  }
}

// Callback chamado pelo DLL com os canais salvos (ao abrir o modal)
window._lgfxOnChatConfig = function(s) {
  if (!s) return;
  chatSavedChannels.twitch = s.twitch || '';
  chatSavedChannels.youtube = s.youtube || '';
  document.getElementById('chat-channel').value = chatSavedChannels[chatPlatform] || '';
};

// Pílula de atualização → abre o dashboard no navegador (C++ trata "openurl/<url>").
var _homeUpdateUrl = 'https://gfxmods.com.br/dashboard';
function openUpdate() { sendAction('openurl/' + _homeUpdateUrl); }

// Callback chamado pelo DLL com o estado da licença (query ou após ativação)
window._lgfxOnLicense = function(s) {
  if (!s) return;
  var statusMap = {
    ok: '✅ ' + (s.statusText || 'Licença ativa'),
    invalid: '❌ Chave inválida',
    hwid_mismatch: '⚠️ PC não autorizado',
    expired: '⏳ Licença expirada',
    banned: '🚫 Licença revogada',
    servererror: '📡 Erro de conexão',
    notchecked: 'Sem licença ativa'
  };
  document.getElementById('lic-status').textContent = statusMap[s.status] || (s.statusText || '—');
  document.getElementById('lic-activate-btn').style.opacity = '1';

  var licensed = (s.status === 'ok');
  document.getElementById('lic-info').style.display = licensed ? 'block' : 'none';
  if (licensed) {
    document.getElementById('lic-masked').textContent = s.masked || '—';
    document.getElementById('lic-edition').textContent = s.edition || 'stable';
    document.getElementById('lic-days').textContent = (s.days < 0) ? 'Permanente' : (s.days + ' dias');
  }
  if (s.error && !licensed) document.getElementById('lic-status').textContent += ' — ' + s.error;
  document.getElementById('lic-hwid').textContent = 'HWID: ' + (s.hwid || '—');

  // Aplica os cadeados de plano nos cards (entitlements + enforced vindos do C++).
  _entitlements = s.entitlements || null;
  applyEntitlementLocks();
  // Selo "Parceiro Oficial" — só p/ parceiros (flag partner, assinada, vinda do C++).
  var sp = document.getElementById('sb-partner');
  if (sp) sp.style.display = (_entitlements && _entitlements.partner) ? '' : 'none';
  // Aviso de atualização — pílula no topo quando o servidor sinaliza update (mesmo dado do PgUp).
  var un = document.getElementById('update-notice');
  if (un) {
    if (s.versionStatus && s.versionStatus !== 'ok') {
      var reqUp = (s.versionStatus === 'update_required');
      if (reqUp) { un.style.background='rgba(255,71,87,0.16)'; un.style.border='1px solid rgba(255,71,87,0.45)'; un.style.color='#ffd3d7'; }
      else       { un.style.background='rgba(255,193,7,0.16)'; un.style.border='1px solid rgba(255,193,7,0.5)';  un.style.color='#ffe28a'; }
      document.getElementById('un-text').textContent =
        (reqUp ? 'Atualização obrigatória' : 'Nova versão disponível')
        + (s.latest ? ' — v' + s.latest : '') + ' · toque para atualizar';
      un.style.display = 'block';
    } else {
      un.style.display = 'none';
    }
  }
};

// Fechar modal com ESC ou clique fora
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') closeModal();
});

// Garante que DOM está pronto antes de adicionar listeners
(function() {
  var modal = document.getElementById('app-modal');
  if (modal) {
    modal.addEventListener('click', function(e) {
      if (e.target === modal) closeModal();
    });
  }
})();

// ?openchat=1 → abre o menu de chat automaticamente (usado pelo botão "↩ voltar"
// do chat-split, que volta pra home pra escolher outro canal).
if (new URLSearchParams(location.search).get('openchat') === '1') {
  openChat();
}

// ---- Fundo customizado (Temas PRO) ----
// O C++ chama _lgfxSetBackground(url) com a imagem do usuário (só se plano PRO/themes
// permitido — a trava real é nativa). url vazio = restaura o gradiente padrão. Um scrim
// escuro por cima mantém os ícones legíveis sobre qualquer imagem.
var _lgfxDefaultBg = document.body.style.backgroundImage;  // captura o gradiente do CSS
window._lgfxSetBackground = function(url) {
  if (url) {
    var safe = String(url).replace(/["\\]/g, '');  // sem aspas/barra invertida (defesa em CSS)
    document.body.style.backgroundImage =
      'linear-gradient(rgba(6,8,20,0.55), rgba(6,8,20,0.72)), url("' + safe + '")';
    document.body.style.backgroundSize = 'cover';
    document.body.style.backgroundPosition = 'center';
    document.body.style.backgroundRepeat = 'no-repeat';
  } else {
    document.body.style.backgroundImage = _lgfxDefaultBg;
    document.body.style.backgroundSize = '';
    document.body.style.backgroundPosition = '';
    document.body.style.backgroundRepeat = '';
  }
};

// Ao abrir a home, pede o estado da licença ao C++ (responde via _lgfxOnLicense) para
// aplicar os cadeados de plano nos cards já na entrada.
sendAction('licensequery');
sendAction('bgquery');   // C++ aplica o fundo salvo (via _lgfxSetBackground) se for PRO

// Boas-vindas (qualquer usuário): aparece 1x por sessão da multimídia. sessionStorage
// sobrevive à navegação (voltar/home recarrega a home no mesmo WebView) mas zera quando o
// WebView é recriado (novo boot do jogo) — então não repete a cada retorno à home.
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
// Re-consulta periodicamente: a licença pode mudar em OUTRO WebView (overlay do PgUp —
// ativar/remover chave). A home é um WebView separado, então precisa re-perguntar pra
// refletir os cadeados sem recarregar a página. Barato (só lê o snapshot, sem rede).
setInterval(function(){ sendAction('licensequery'); }, 3000);
