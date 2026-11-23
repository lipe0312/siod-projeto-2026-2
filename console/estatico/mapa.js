/* Mapa de satélite da ficha (issue #35): as camadas do <nome>.camadas.geojson (embutido na página) sobre o
   EOX Sentinel-2 cloudless de 2020 (antes do corte da EUDR) e do mosaico mais recente (depois), lado a lado e com o
   zoom sincronizado. Leaflet 1.9.4 servido pelo próprio console. Se a imagem não carrega (sem internet, provedor fora),
   o bloco some e volta o mapa SVG da ficha com o aviso. Todo texto do GeoJSON entra por textContent. */
(function () {
  'use strict';
  var raiz = document.querySelector('[data-sat]');
  var fonte = document.getElementById('camadas-dados');
  if (!raiz || !fonte) return;
  var secao = raiz.closest('#mapa') || document;
  var aviso = secao.querySelector('.sat-aviso');
  var encerrado = false;

  function falhar() {
    if (encerrado) return;
    encerrado = true;
    raiz.hidden = true;
    if (secao.classList) secao.classList.remove('sat-on');
    if (aviso) aviso.hidden = false;
  }

  if (!window.L) { falhar(); return; }
  var dados;
  try { dados = JSON.parse(fonte.textContent); } catch (e) { falhar(); return; }
  var feicoes = (dados.features || []).filter(function (f) { return f && f.geometry && f.properties; });
  if (!feicoes.length) { falhar(); return; }

  var reduz = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var URL = 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-{ano}_3857/default/g/{z}/{y}/{x}.jpg';
  var NOMES = {};
  var cores = {};
  raiz.hidden = false;
  secao.classList.add('sat-on');
  raiz.querySelectorAll('[data-camada]').forEach(function (cx) {
    var c = cx.getAttribute('data-camada');
    var sw = cx.parentNode.querySelector('[data-sw]');
    cores[c] = sw ? getComputedStyle(sw).backgroundColor : '#ffffff';
    NOMES[c] = Array.prototype.filter.call(cx.parentNode.childNodes, function (n) { return n.nodeType === 3; })
      .map(function (n) { return n.textContent; }).join('').trim();
  });

  function estilo(c, destaque) {
    var cor = cores[c] || '#ffffff';
    return { color: cor, fillColor: cor, opacity: 1, weight: destaque ? 6 : (c === 'car' ? 3 : 2),
             fillOpacity: c === 'car' ? 0 : (destaque ? 0.45 : 0.25), dashArray: /_resto$/.test(c) ? '6 4' : null };
  }

  function dataBr(v) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(v || '');
    return m ? m[3] + '/' + m[2] + '/' + m[1] : (v || '');
  }

  function popup(p) {
    var div = document.createElement('div');
    div.className = 'sat-pop';
    var t = document.createElement('strong');
    t.textContent = (p.rotulo && p.rotulo !== 'CAR' ? p.rotulo + ' · ' : '') + (NOMES[p.camada] || p.camada || '');
    div.appendChild(t);
    [['Fonte', p.fonte], ['Data da imagem', p.data_imagem ? dataBr(p.data_imagem) : 'não se aplica'],
     ['Área', p.ha == null ? 'não informada' : String(p.ha).replace('.', ',') + ' ha'], ['Situação', p.situacao]]
      .forEach(function (par) {
        if (par[1] == null || par[1] === '') return;
        var l = document.createElement('div');
        l.textContent = par[0] + ': ' + par[1];
        div.appendChild(l);
      });
    return div;
  }

  var carregou = false, erros = 0, mapas = [], grupos = [], porRotulo = [];
  var sincronizando = false;

  ['antes', 'depois'].forEach(function (qual, i) {
    var el = document.getElementById('sat-' + qual);
    var ano = raiz.getAttribute('data-' + qual);
    var m = L.map(el, { zoomAnimation: !reduz, fadeAnimation: !reduz, markerZoomAnimation: !reduz,
                        attributionControl: false, scrollWheelZoom: false });
    var tiles = L.tileLayer(URL.replace('{ano}', ano), { maxZoom: 17 });
    tiles.on('tileload', function () {
      if (!carregou) { carregou = true; secao.classList.add('sat-ok'); }
    });
    tiles.on('tileerror', function () { erros += 1; if (!carregou && erros >= 4) falhar(); });
    tiles.addTo(m);
    var g = {}, r = {};
    feicoes.forEach(function (f) {
      var c = f.properties.camada;
      var camada = L.geoJSON(f, { style: function () { return estilo(c); } });
      camada.bindPopup(function () { return popup(f.properties); });
      if (c !== 'car' && f.properties.rotulo) {
        var rot = document.createElement('span');
        rot.textContent = String(f.properties.rotulo);  // string no Leaflet entra como HTML; elemento com textContent não
        camada.bindTooltip(rot, { permanent: true, direction: 'center', className: 'sat-rot' });
      }
      (g[c] = g[c] || L.featureGroup().addTo(m)).addLayer(camada);
      if (f.properties.rotulo) r[f.properties.rotulo] = { camada: camada, c: c };
    });
    var base = g.car || L.featureGroup(Object.keys(g).map(function (k) { return g[k]; }));
    m.fitBounds(base.getBounds(), { padding: [16, 16], animate: false });
    mapas.push(m); grupos.push(g); porRotulo.push(r);
  });

  // zoom e posição sincronizados
  mapas.forEach(function (m, i) {
    m.on('move', function () {
      if (sincronizando) return;
      sincronizando = true;
      mapas[1 - i].setView(m.getCenter(), m.getZoom(), { animate: false });
      sincronizando = false;
    });
  });

  setTimeout(function () { if (!carregou) falhar(); }, 10000);

  // ligar e desligar camadas (nos dois mapas)
  raiz.querySelectorAll('[data-camada]').forEach(function (cx) {
    cx.addEventListener('change', function () {
      var c = cx.getAttribute('data-camada');
      mapas.forEach(function (m, i) {
        var g = grupos[i][c];
        if (!g) return;
        if (cx.checked) m.addLayer(g); else m.removeLayer(g);
      });
    });
  });

  // "Ver no mapa" num cartão do plano: centraliza e destaca os polígonos daquela evidência
  document.querySelectorAll('a.leva[data-rot]').forEach(function (a) {
    a.addEventListener('click', function () {
      if (encerrado || !a.getAttribute('data-rot')) return;
      var letras = a.getAttribute('data-rot').split(/\s+/).filter(Boolean);
      var padrao = new RegExp('^(' + letras.join('|') + ')\\d+$');
      var achados = [];
      porRotulo.forEach(function (r, i) {
        Object.keys(r).forEach(function (rot) { if (padrao.test(rot)) achados.push([i, r[rot]]); });
      });
      if (!achados.length) return;
      var limites = L.latLngBounds([]);
      achados.forEach(function (par) {
        var i = par[0], item = par[1];
        var cx = raiz.querySelector('[data-camada="' + item.c + '"]');
        if (cx && !cx.checked) { cx.checked = true; cx.dispatchEvent(new Event('change')); }
        if (i === 1) limites.extend(item.camada.getBounds());
        item.camada.setStyle(estilo(item.c, true));
        setTimeout(function () { item.camada.setStyle(estilo(item.c)); }, 2500);
      });
      if (limites.isValid()) mapas[1].fitBounds(limites, { padding: [24, 24], maxZoom: 16, animate: !reduz });
    });
  });
})();
