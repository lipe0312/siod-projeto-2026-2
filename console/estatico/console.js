// Console local do AgroValid: busca Ctrl/⌘ K, formulário da nova consulta e cruzamento ao vivo (polling).
// O documento só sai daqui num POST JSON; nunca vai para a URL nem para o armazenamento do navegador.
(function () {
  'use strict';
  var FORMATO_CAR = /^[A-Z]{2}-\d{7}-[0-9A-F]{32}$/;
  var LIMITE_AREA = 2 * 1024 * 1024;
  var ETAPAS = ['SICAR', 'PRODES da UF', 'IBAMA', 'DETER', 'Lista Suja', 'Áreas protegidas'];
  var SITUACAO = {
    'com pendência': ['pend', 'st-pend'], 'com indício': ['indi', 'st-indi'],
    'sem pendência nas fontes verificadas': ['sem', 'st-sem'], 'inconclusivo': ['inco', 'st-inco']
  };
  var ICONE_ETAPA = { ok: 'sem', inco: 'inco', nao: 'nao', vai: 'loader', espera: 'nao' };
  var NOME_ESTADO = { ok: 'consultado', inco: 'sem resposta ou dado incompleto', nao: 'não cruzado' };
  var calmo = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var $ = function (s) { return document.querySelector(s); };

  function el(tag, attrs, filhos) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === 'text') n.textContent = attrs[k]; else n.setAttribute(k, attrs[k]);
    });
    (filhos || []).forEach(function (f) { if (f) n.appendChild(f); });
    return n;
  }
  function ico(nome, classe) {
    var s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    s.setAttribute('class', classe || 'ico'); s.setAttribute('aria-hidden', 'true');
    var u = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    u.setAttribute('href', '#i-' + nome); s.appendChild(u); return s;
  }
  function segundos(s) { return String((Math.round(s * 10) / 10).toFixed(1)).replace('.', ',') + ' s'; }

  // Busca: Ctrl/⌘ K (por ora, leva ao campo do CAR)
  function focarBusca() {
    var car = $('#car');
    if (!car) { window.location.href = '/consulta#car'; return; }
    var modo = document.querySelector('input[name=modo][value=car]');
    if (modo && !modo.checked) { modo.checked = true; trocarModo(); }
    car.focus(); car.select();
  }
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) { e.preventDefault(); focarBusca(); }
  });
  var busca = document.querySelector('[data-busca]');
  if (busca) {
    if (/Mac|iPhone|iPad/.test(navigator.platform || '')) {
      var kbd = busca.querySelector('kbd'); if (kbd) kbd.textContent = '⌘ K';
    }
    busca.addEventListener('click', focarBusca);
  }

  var form = $('#form-consulta');
  if (!form) return;
  if (window.location.hash === '#car') focarBusca();

  // Modo: código do CAR ou coordenada
  function modoAtual() { return (document.querySelector('input[name=modo]:checked') || {}).value || 'car'; }
  function trocarModo() {
    var m = modoAtual();
    document.querySelectorAll('[data-modo]').forEach(function (b) { b.hidden = b.getAttribute('data-modo') !== m; });
  }
  document.querySelectorAll('input[name=modo]').forEach(function (r) { r.addEventListener('change', trocarModo); });

  // CAR conferido ao digitar
  var car = $('#car'), carAjuda = $('#car-ajuda'), ajudaPadrao = carAjuda.textContent;
  function conferirCar(final) {
    var v = car.value.trim().toUpperCase();
    if (car.value !== v && document.activeElement !== car) car.value = v;
    if (!v) { car.removeAttribute('aria-invalid'); carAjuda.textContent = ajudaPadrao; carAjuda.className = 'ajuda'; return false; }
    var ok = FORMATO_CAR.test(v);
    if (ok) {
      car.setAttribute('aria-invalid', 'false'); carAjuda.className = 'ajuda bom';
      carAjuda.textContent = 'Formato certo: ' + v.slice(0, 2) + ', município ' + v.slice(3, 10) + '.';
    } else if (final || v.length >= 43) {
      car.setAttribute('aria-invalid', 'true'); carAjuda.className = 'ajuda ruim';
      carAjuda.textContent = 'Fora do formato: UF-IBGE-32 hexadecimais (' + v.length + ' de 43 caracteres).';
    } else {
      car.removeAttribute('aria-invalid'); carAjuda.className = 'ajuda';
      carAjuda.textContent = v.length + ' de 43 caracteres. ' + ajudaPadrao;
    }
    return ok;
  }
  car.addEventListener('input', function () {
    var pos = car.selectionStart; car.value = car.value.toUpperCase(); car.setSelectionRange(pos, pos); conferirCar(false);
  });
  car.addEventListener('blur', function () { conferirCar(true); });

  // Documento mascarado (CPF ou CNPJ conforme a quantidade de dígitos)
  var doc = $('#documento');
  doc.addEventListener('input', function () {
    var d = doc.value.replace(/\D/g, '').slice(0, 14), f;
    if (d.length <= 11) f = d.replace(/^(\d{3})(\d)/, '$1.$2').replace(/^(\d{3})\.(\d{3})(\d)/, '$1.$2.$3').replace(/\.(\d{3})(\d{1,2})$/, '.$1-$2');
    else f = d.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{1,2})$/, '$1.$2.$3/$4-$5');
    doc.value = f;
  });

  // Área de produção lida no navegador e enviada como texto
  var area = $('#area'), areaAjuda = $('#area-ajuda'), areaPadrao = areaAjuda.textContent, areaLida = null;
  area.addEventListener('change', function () {
    areaLida = null; areaAjuda.className = 'ajuda'; areaAjuda.textContent = areaPadrao;
    var f = area.files && area.files[0];
    if (!f) return;
    if (!/\.(kml|geojson|json)$/i.test(f.name)) { areaAjuda.className = 'ajuda ruim'; areaAjuda.textContent = 'Use um arquivo .kml, .geojson ou .json.'; area.value = ''; return; }
    if (f.size > LIMITE_AREA) { areaAjuda.className = 'ajuda ruim'; areaAjuda.textContent = 'Arquivo com mais de 2 MB: não é o da área de produção.'; area.value = ''; return; }
    var r = new FileReader();
    r.onload = function () {
      areaLida = { nome: f.name, texto: String(r.result) };
      areaAjuda.className = 'ajuda bom'; areaAjuda.textContent = 'Arquivo lido (' + Math.max(1, Math.round(f.size / 1024)) + ' KB). ' + areaPadrao;
    };
    r.onerror = function () { areaAjuda.className = 'ajuda ruim'; areaAjuda.textContent = 'O arquivo não pôde ser lido.'; };
    r.readAsText(f);
  });

  // Cruzamento
  var botao = $('#cruzar'), erro = $('#erro'), lista = $('#etapas'), andamento = $('#andamento'),
    resultado = $('#resultado'), vazio = $('#vazio'), relogio = null;

  function mostrarErro(texto) { erro.textContent = texto; erro.hidden = !texto; }
  function ocupado(sim) {
    botao.disabled = sim; botao.setAttribute('aria-busy', sim ? 'true' : 'false');
    botao.textContent = sim ? 'Cruzando…' : 'Cruzar agora';
  }
  function linha(nome, estado, texto) {
    return el('li', { 'class': estado }, [ico(ICONE_ETAPA[estado] || 'loader'),
      el('span', {}, [el('b', { text: nome }), el('span', { 'class': 'o-que', text: texto }),
        NOME_ESTADO[estado] ? el('span', { 'class': 'sr', text: ' (' + NOME_ESTADO[estado] + ')' }) : null])]);
  }
  function inicioDasEtapas() {
    vazio.hidden = true; resultado.hidden = true; resultado.textContent = '';
    lista.textContent = '';
    ETAPAS.forEach(function (n) { lista.appendChild(linha(n, 'espera', 'aguardando')); });
    lista.hidden = false;
    andamento.textContent = '';
    andamento.appendChild(ico('loader'));
    andamento.appendChild(el('span', { text: 'Consultando o SICAR e cruzando as fontes' }));
    andamento.appendChild(el('span', { 'class': 'tm', id: 'tm', text: '0,0 s' }));
    andamento.hidden = false;
  }

  function pedido() {
    var dados = {};
    if (modoAtual() === 'car') {
      if (!conferirCar(true)) { car.focus(); return 'Confira o código do CAR: UF-IBGE-32 hexadecimais.'; }
      dados.car = car.value.trim().toUpperCase();
    } else {
      dados.lat = $('#lat').value.trim(); dados.lon = $('#lon').value.trim();
      if (!dados.lat || !dados.lon) { $('#lat').focus(); return 'Informe a latitude e a longitude da sede.'; }
    }
    var d = doc.value.replace(/\D/g, '');
    if (d) {
      if (d.length !== 11 && d.length !== 14) { doc.focus(); return 'CPF tem 11 dígitos e CNPJ, 14.'; }
      dados.documento = d;
    }
    if (areaLida) dados.area = areaLida;
    var c = document.querySelector('input[name=commodity]:checked');
    if (c) dados.commodity = c.value;
    return dados;
  }

  function cruzar() {
    mostrarErro('');
    var dados = pedido();
    if (typeof dados === 'string') { mostrarErro(dados); return; }
    ocupado(true);
    fetch('/api/consultas', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(dados), cache: 'no-store' })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (r) {
        if (!r.ok) { ocupado(false); mostrarErro(r.j.erro || 'A consulta não pôde começar.'); return; }
        inicioDasEtapas();
        acompanhar(r.j.id);
      })
      .catch(function () { ocupado(false); mostrarErro('O console não respondeu. Ele ainda está aberto no terminal?'); });
  }

  function acompanhar(id) {
    var inicio = performance.now();
    clearInterval(relogio);
    relogio = setInterval(function () { var t = $('#tm'); if (t) t.textContent = segundos((performance.now() - inicio) / 1000); }, 100);
    (function consultar() {
      fetch('/api/consultas/' + encodeURIComponent(id), { cache: 'no-store' })
        .then(function (r) { return r.json(); })
        .then(function (e) {
          if (e.estado === 'rodando') { setTimeout(consultar, 400); return; }
          clearInterval(relogio);
          terminar(e);
        })
        .catch(function () { setTimeout(consultar, 1000); });
    })();
  }

  function terminar(e) {
    andamento.hidden = true;
    if (e.estado === 'erro') {
      lista.hidden = true;
      montarResultado(e, null);
      ocupado(false);
      return;
    }
    var itens = lista.querySelectorAll('li');
    (e.etapas || []).forEach(function (et, i) {
      var trocar = function () { var nova = linha(et.nome, et.estado, et.texto); if (itens[i]) lista.replaceChild(nova, itens[i]); else lista.appendChild(nova); };
      if (calmo) trocar(); else setTimeout(trocar, 140 * i);
    });
    var fim = function () { montarResultado(e, e.etapas); ocupado(false); };
    if (calmo) fim(); else setTimeout(fim, 140 * (e.etapas || []).length + 60);
  }

  function montarResultado(e, etapas) {
    resultado.textContent = '';
    if (e.estado === 'erro') {
      resultado.appendChild(el('p', { 'class': 'motivo', text: e.erro }));
    } else {
      var s = SITUACAO[e.situacao] || ['nao', 'st-nao'];
      resultado.appendChild(el('span', { 'class': 'selo ' + s[1] }, [ico(s[0]), el('span', { text: e.situacao })]));
      if (e.resumo) resultado.appendChild(el('p', { 'class': 'resumo', text: e.resumo }));
      if (e.motivo) resultado.appendChild(el('p', { 'class': 'motivo', text: 'Motivo: ' + e.motivo }));
    }
    var botoes = el('div', { 'class': 'botoes' });
    if (e.ficha) {
      botoes.appendChild(el('a', { 'class': 'btn b-pri leva', href: '/fichas/' + encodeURIComponent(e.ficha), target: '_blank', rel: 'noopener' },
        [el('span', { text: 'Abrir a ficha' }), ico('arrow', 'ico seta')]));
    }
    if (e.estado === 'erro' || e.situacao === 'inconclusivo') {
      var de_novo = el('button', { 'class': 'btn b-sec acao', type: 'button' }, [ico('redo'), el('span', { text: 'Tentar de novo' })]);
      de_novo.addEventListener('click', cruzar);
      botoes.appendChild(de_novo);
    }
    resultado.appendChild(botoes);
    var pe = [];
    if (typeof e.tempo_s === 'number') pe.push('Tempo total medido: ' + segundos(e.tempo_s));
    if (e.documento_curto) pe.push('documento virou o código ' + e.documento_curto + '…');
    if (e.ficha) pe.push('execução avulsa gravada no lago');
    if (pe.length) resultado.appendChild(el('p', { 'class': 'pe', text: pe.join(' · ') }));
    resultado.hidden = false;
    resultado.focus();
  }

  form.addEventListener('submit', function (ev) { ev.preventDefault(); if (!botao.disabled) cruzar(); });
})();
