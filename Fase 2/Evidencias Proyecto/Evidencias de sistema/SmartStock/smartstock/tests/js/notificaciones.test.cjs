const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const {JSDOM, VirtualConsole} = require('jsdom');
const fuente = readFileSync(path.join(__dirname, '../../static/js/notificaciones.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
const noticia = (id, extra = {}) => ({id, tipo: 'OTRO', titulo: 'Producto actualizado', mensaje: 'Cambio guardado ' + id, fecha: '28/10 20:30', link: '', ...extra});
const datos = (items = [], total = items.length) => ({success: true, data: {items, total}});

test('la campana abre el historial de SMS desde la notificación de revisión', async t => {
    const c = await campana(t, {url: 'http://localhost/alertas-sms/'});
    await c.responder(0, datos([noticia(1, {link: '/alertas-sms/#tituloHistorialSMS'})]));
    c.el('ss-notif-list').querySelector('button').click();
    await c.responder(1, {success: true}); await c.responder(2);
    assert.equal(c.w.location.hash, '#tituloHistorialSMS'); assert.deepEqual(c.errores, []);
});

test('la campana permite abrir las ubicaciones de la bodega del aviso', async t => {
    const c = await campana(t, {url: 'http://localhost/ubicaciones/?bodega=2'});
    await c.responder(0, datos([noticia(1, {link: '/ubicaciones/?bodega=2#estructura'})]));
    c.el('ss-notif-list').querySelector('button').click();
    await c.responder(1, {success: true}); await c.responder(2);
    assert.equal(c.w.location.search, '?bodega=2'); assert.equal(c.w.location.hash, '#estructura');
    assert.deepEqual(c.errores, []);
});

async function campana(t, config = {}) {
    const errores = [], virtualConsole = new VirtualConsole(); virtualConsole.on('jsdomError', e => errores.push(e.message));
    const dom = new JSDOM('<nav><div><button id="btn-logout-test">Cerrar sesión</button></div></nav>', {
        url: config.url || 'http://localhost/productos/', runScripts: 'outside-only', pretendToBeVisual: true, virtualConsole,
    });
    const w = dom.window, requests = [], toasts = [], intervalos = [], canales = [];
    t.after(() => w.close());
    if (!config.sinSesion) w.localStorage.setItem('access_token', 'token-prueba');
    w.localStorage.setItem('usuario', JSON.stringify({id: config.id || 1}));
    if (config.vistos) w.sessionStorage.setItem('ss-notificaciones-vistas:' + (config.id || 1), JSON.stringify(config.vistos));
    w.bootstrap = {Toast: {getOrCreateInstance: elemento => ({show() { toasts.push(elemento.querySelector('.toast-body').textContent); }, hide() {}})}};
    w.Notification = {requestPermission() { throw new Error('No solicitar permisos del sistema'); }};
    w.BroadcastChannel = class {
        constructor(nombre) { this.nombre = nombre; this.mensajes = []; canales.push(this); }
        addEventListener(tipo, callback) { this.recibir = callback; }
        postMessage(mensaje) { this.mensajes.push(mensaje); }
        close() { this.cerrado = true; }
    };
    w.setInterval = fn => { intervalos.push(fn); return intervalos.length; };
    w.fetch = (url, options) => new Promise((resolve, reject) => requests.push({url: new URL(url, w.location.href), options, resolve, reject}));
    w.eval(fuente); await tick();
    const el = id => w.document.getElementById(id);
    const responder = async (i, body = datos(), status = 200) => { requests[i].resolve({ok: status >= 200 && status < 300, status, json: async () => body}); await tick(); };
    const cambio = () => w.dispatchEvent(new w.Event('smartstock:notifications-changed'));
    return {w, el, requests, toasts, intervalos, canales, errores, responder, cambio};
}

test('una operación actualiza la campana y muestra un único aviso aunque se vuelva a consultar', async t => {
    const c = await campana(t); await c.responder(0); c.cambio(); await c.responder(1, datos([noticia(1)]));
    assert.equal(c.el('ss-notif-count').textContent, '1'); assert.equal(c.el('ss-notif-count').hidden, false);
    assert.match(c.el('ss-notif-btn').getAttribute('aria-label'), /1 sin leer/); assert.equal(c.toasts.length, 1);
    c.cambio(); await c.responder(2, datos([noticia(1)])); c.intervalos[0](); await c.responder(3, datos([noticia(1)]));
    assert.equal(c.toasts.length, 1); assert.equal(c.el('ss-notif-list').children.length, 1);
});

test('un cambio durante la carga conserva una recarga pendiente sin consultas paralelas', async t => {
    const c = await campana(t); c.cambio(); c.cambio(); assert.equal(c.requests.length, 1);
    await c.responder(0); assert.equal(c.requests.length, 2); await c.responder(1, datos([noticia(1)]));
    assert.equal(c.toasts.length, 1); assert.equal(c.el('ss-notif-count').textContent, '1'); assert.equal(c.requests.length, 2);
});

test('los avisos existentes se muestran al entrar sin repetir el aviso emergente', async t => {
    const c = await campana(t); await c.responder(0, datos([noticia(10), noticia(9)]));
    assert.equal(c.toasts.length, 0); assert.equal(c.el('ss-notif-list').children.length, 2);
    c.cambio(); await c.responder(1, datos([noticia(11), noticia(10), noticia(9)])); assert.equal(c.toasts.length, 1);
    assert.match(c.toasts[0], /Cambio guardado 11/);
});

test('la referencia de avisos vistos se conserva al cambiar de módulo', async t => {
    const c = await campana(t, {vistos: [10, 9]}); await c.responder(0, datos([noticia(10), noticia(9)]));
    assert.equal(c.toasts.length, 0); c.cambio(); await c.responder(1, datos([noticia(11), noticia(10)]));
    assert.equal(c.toasts.length, 1); assert.ok(JSON.parse(c.w.sessionStorage.getItem('ss-notificaciones-vistas:1')).includes(11));
});

test('leer uno de los primeros 20 no anuncia como nuevo el aviso antiguo que aparece después', async t => {
    const c = await campana(t); await c.responder(0, datos(Array.from({length: 20}, (_, i) => noticia(40 - i)), 40));
    c.el('ss-notif-list').querySelector('button').click(); c.el('ss-notif-list').querySelector('button').click();
    assert.equal(c.requests.length, 2); assert.equal(c.requests[1].url.pathname, '/api/v1/productos/notificaciones/40/marcar-leida/');
    await c.responder(1, {success: true}); await c.responder(2, datos(Array.from({length: 20}, (_, i) => noticia(39 - i)), 39));
    assert.equal(c.toasts.length, 0); assert.equal(c.el('ss-notif-count').textContent, '39');
    assert.ok(JSON.parse(c.w.sessionStorage.getItem('ss-notificaciones-vistas:1')).includes(40));
});

test('marcar todas evita doble envío y sincroniza el contador sin crear otro aviso', async t => {
    const c = await campana(t); await c.responder(0, datos([noticia(2), noticia(1)]));
    c.el('ss-notif-read-all').click(); c.el('ss-notif-read-all').click(); assert.equal(c.requests.length, 2);
    assert.equal(c.requests[1].options.method, 'POST'); await c.responder(1, {success: true}); await c.responder(2);
    assert.equal(c.el('ss-notif-count').hidden, true); assert.equal(c.el('ss-notif-read-all').disabled, true);
    assert.equal(c.toasts.length, 0); assert.match(c.el('ss-notif-list').textContent, /No tienes notificaciones/);
    assert.ok(c.canales[0].mensajes.includes('actualizar'));
});

test('un error de lectura conserva los avisos y permite reintentar desde la campana', async t => {
    const c = await campana(t); await c.responder(0, datos([noticia(1)])); c.cambio(); await c.responder(1, {}, 503);
    assert.equal(c.el('ss-notif-count').textContent, '1'); assert.equal(c.el('ss-notif-list').children.length, 1);
    assert.equal(c.el('ss-notif-error').hidden, false); c.el('ss-notif-btn').click(); await c.responder(2, datos([noticia(1)]));
    assert.equal(c.el('ss-notif-error').hidden, true); assert.equal(c.toasts.length, 0);
});

test('un fallo al marcar leída se muestra dentro de la campana sin perder el aviso', async t => {
    const c = await campana(t); await c.responder(0, datos([noticia(1)])); const b = c.el('ss-notif-list').querySelector('button'); b.click();
    c.requests[1].reject(new TypeError('Sin conexión')); await tick();
    assert.equal(b.disabled, false); assert.match(c.el('ss-notif-error').textContent, /Vuelve a intentarlo/);
    assert.equal(c.el('ss-notif-count').textContent, '1'); assert.deepEqual(c.errores, []);
});

test('un error al marcar todas permite reintentar y conserva el contador', async t => {
    const c = await campana(t); await c.responder(0, datos([noticia(1)])); c.el('ss-notif-read-all').click(); await c.responder(1, {}, 503);
    assert.equal(c.el('ss-notif-read-all').disabled, false); assert.equal(c.el('ss-notif-count').textContent, '1');
    assert.equal(c.el('ss-notif-error').hidden, false); assert.deepEqual(c.errores, []);
});

test('los textos de las notificaciones no se interpretan como HTML', async t => {
    const c = await campana(t); await c.responder(0); c.cambio(); await c.responder(1, datos([noticia(1, {titulo: '<img src=x onerror=alert(1)>', mensaje: '<svg onload=alert(1)>'})]));
    assert.equal(c.el('ss-notif-list').querySelector('img,svg'), null); assert.equal(c.toasts.length, 1); assert.match(c.toasts[0], /<svg/);
});

test('los enlaces del catálogo conservan la búsqueda y la bodega al marcar leída', async t => {
    const c = await campana(t, {url: 'http://localhost/productos/?q=CAT-1&bodega=2'});
    await c.responder(0, datos([noticia(1, {link: '/productos/?q=CAT-1&bodega=2#detalle'})]));
    c.el('ss-notif-list').querySelector('button').click(); await c.responder(1, {success: true}); await c.responder(2);
    assert.equal(c.w.location.hash, '#detalle'); assert.equal(c.w.location.search, '?q=CAT-1&bodega=2'); assert.deepEqual(c.errores, []);
});

test('la campana rechaza enlaces externos, javascript y rutas no permitidas', async t => {
    for (const link of ['https://externo.example/productos/', '//externo.example/productos/', 'javascript:alert(1)', '/admin/']) {
        const c = await campana(t); await c.responder(0, datos([noticia(1, {link})]));
        c.el('ss-notif-list').querySelector('button').click(); await c.responder(1, {success: true}); await c.responder(2);
        assert.equal(c.w.location.href, 'http://localhost/productos/'); assert.deepEqual(c.errores, []);
    }
});

test('los avisos de bodegas abren su módulo conservando la ruta interna', async t => {
    const c = await campana(t, {url:'http://localhost/bodegas/'});
    await c.responder(0,datos([noticia(1,{link:'/bodegas/#organizacion'})]));
    c.el('ss-notif-list').querySelector('button').click();
    await c.responder(1,{success:true});await c.responder(2);
    assert.equal(c.w.location.pathname,'/bodegas/');assert.equal(c.w.location.hash,'#organizacion');assert.deepEqual(c.errores,[]);
});

test('consultar una lista sin cambios conserva el foco de teclado', async t => {
    const c = await campana(t); await c.responder(0, datos([noticia(1)])); const b = c.el('ss-notif-list').querySelector('button'); b.focus();
    c.intervalos[0](); await c.responder(1, datos([noticia(1)])); assert.equal(c.w.document.activeElement, b);
});

test('los avisos de transferencias pueden abrir su historial desde la campana', async t => {
    const c=await campana(t,{url:'http://localhost/transferencias/'});
    await c.responder(0,datos([noticia(1,{link:'/transferencias/#historial'})]));
    c.el('ss-notif-list').querySelector('button').click();
    await c.responder(1,{success:true});await c.responder(2);
    assert.equal(c.w.location.hash,'#historial');assert.deepEqual(c.errores,[]);
});

test('el contador usa 99+ y la consulta utiliza el token actual sin caché', async t => {
    const c = await campana(t); await c.responder(0, datos([noticia(1)], 120));
    assert.equal(c.el('ss-notif-count').textContent, '99+'); assert.match(c.el('ss-notif-btn').getAttribute('aria-label'), /120 sin leer/);
    c.w.localStorage.setItem('access_token', 'rotado'); c.cambio(); assert.equal(c.requests[1].options.headers.Authorization, 'Bearer rotado');
    assert.equal(c.requests[1].options.cache, 'no-store');
});

test('los cambios de otra pestaña recargan la bandeja y se cierra el canal al salir', async t => {
    const c = await campana(t); await c.responder(0); c.canales[0].recibir({data: 'actualizar'}); await c.responder(1, datos([noticia(1)]));
    assert.equal(c.toasts.length, 1); assert.equal(c.canales[0].mensajes.length, 0);
    c.w.dispatchEvent(new c.w.Event('pagehide')); assert.equal(c.canales[0].cerrado, true);
});

test('sin sesión no se instala la campana ni se solicitan notificaciones', async t => {
    const c = await campana(t, {sinSesion: true}); assert.equal(c.el('ss-notif-btn'), null); assert.equal(c.requests.length, 0);
});
