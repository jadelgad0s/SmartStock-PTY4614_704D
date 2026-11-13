const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const root = path.resolve(__dirname, '../..');
const html = readFileSync(path.join(root, 'templates/dashboard.html'), 'utf8').replace(/{%[\s\S]*?%}/g, '');
const fuente = readFileSync(path.join(root, 'static/js/dashboard.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
const alerta = (id = 1, extra = {}) => ({producto_id: id, producto: 'Producto ' + id, sku: 'SKU-' + id, stock: 0, minimo: 5, estado: 'agotado', bodega: 'Bodega Central', bodega_id: 1, ...extra});
const movimiento = (extra = {}) => ({id: 4, movimiento_id: 3, producto: 'Bebida Cherry', sku: 'ABC/123', fecha_iso: '2026-10-28T02:30:00Z', tipo: 'SALIDA', cantidad: 2, usuario: 'Persona Prueba', bodega: 'Bodega Central', documento_referencia: 'Guía 123', ...extra});
function datos(extra = {}) {
    const dias = extra.dias || 7;
    return {bodega: {id: 1, nombre: 'Bodega Central'}, bodegas: [{id: 1, nombre: 'Bodega Central'}, {id: 2, nombre: 'Anexo'}], dias, desde: '2026-10-21', hasta: '2026-10-27', actualizado: '2026-10-28T02:30:00Z', kpi_stock: 15, kpi_entradas: 12, kpi_salidas: 2, kpi_alertas: 1, estado_inventario: {total: 3, suficiente: 1, bajo: 1, agotado: 1}, chart_labels: Array.from({length: dias}, (_, i) => String(i + 1)), chart_fechas: Array.from({length: dias}, (_, i) => '2026-10-' + String(i + 1).padStart(2, '0')), chart_entradas: Array.from({length: dias}, (_, i) => i === dias - 1 ? 12 : 0), chart_salidas: Array.from({length: dias}, (_, i) => i === dias - 1 ? 2 : 0), recientes: [movimiento()], alertas: [alerta(), alerta(2, {estado: 'bajo', stock: 2})], permisos: {registrar_movimiento: true, auditoria: true, usuarios: true, configuracion: false}, ...extra};
}
const pagina = (count = 55, n = 1) => ({count, results: Array.from({length: Math.max(0, Math.min(25, count - (n - 1) * 25))}, (_, i) => alerta((n - 1) * 25 + i + 1))});
async function pantalla(t, options = {}) {
    const dom = new JSDOM(html, {url: 'http://localhost/dashboard/', runScripts: 'outside-only', pretendToBeVisual: true});
    t.after(() => dom.window.close());
    const w = dom.window, requests = [], modelos = new Map(), charts = [], timers = new Map();
    w.localStorage.setItem('access_token', 'test'); w.localStorage.setItem('refresh_token', 'refresh');
    w.localStorage.setItem('usuario', options.sesion || JSON.stringify({nombre_completo: 'Admin Prueba', rol_nombre: 'Administrador'}));
    w.smartstockClearSession = () => { w.localStorage.removeItem('access_token'); w.localStorage.removeItem('refresh_token'); };
    w.matchMedia = () => ({matches: false});
    w.HTMLCanvasElement.prototype.getContext = () => ({});
    if (options.chart !== false) w.Chart = class {
        constructor(ctx, config) { Object.assign(this, config); this.updates = 0; charts.push(this); }
        destroy() { this.destruido = true; }
        update() { this.updates++; }
    };
    w.bootstrap = {Modal: {getOrCreateInstance(elemento) {
        if (!modelos.has(elemento)) modelos.set(elemento, {
            show() { elemento.dispatchEvent(new w.Event('show.bs.modal')); elemento.classList.add('show'); elemento.dispatchEvent(new w.Event('shown.bs.modal')); },
            hide() { elemento.dispatchEvent(new w.Event('hide.bs.modal')); elemento.classList.remove('show'); elemento.dispatchEvent(new w.Event('hidden.bs.modal')); },
        }); return modelos.get(elemento);
    }}};
    let timer = 0;
    w.setTimeout = (fn, delay) => { timers.set(++timer, {fn, delay}); return timer; }; w.clearTimeout = id => timers.delete(id);
    w.fetch = (url, opts) => new Promise((resolve, reject) => requests.push({url: new URL(url, w.location.href), options: opts, resolve, reject}));
    w.eval(fuente); await tick();
    const el = id => w.document.getElementById(id);
    const responder = async (index, data, status = 200) => { requests[index].resolve({ok: status >= 200 && status < 300, status, json: async () => data}); await tick(); };
    const iniciar = async (info = datos()) => responder(0, {success: true, data: info});
    const campo = (id, value, type = 'change') => { el(id).value = value; el(id).dispatchEvent(new w.Event(type)); };
    const abrirAlertas = () => el('dashboardVerAlertas').click();
    const debounce = async () => { [...timers.entries()].filter(([, v]) => v.delay === 300).forEach(([id, v]) => { timers.delete(id); v.fn(); }); await tick(); };
    return {w, el, requests, modelos, charts, responder, iniciar, campo, abrirAlertas, debounce};
}

test('resumen expresa unidades y el gráfico circular cuenta productos sin mezclar cantidades', async t => {
    const c = await pantalla(t); await c.iniciar();
    assert.equal(c.el('kpi-stock').textContent, '15'); assert.equal(c.el('dashboardTotalProductos').textContent, '3');
    assert.deepEqual(Array.from(c.charts.find(g => g.type === 'doughnut').data.datasets[0].data), [1, 1, 1]);
    assert.equal(c.el('dashboardSuficiente').textContent, '1'); assert.equal(c.el('dashboardBajo').textContent, '1');
    assert.match(c.el('dashboardActualizado').textContent, /27\/10\/2026 23:30:00/);
    assert.match(c.el('dashboardScope').textContent, /Bodega Central/);
    assert.equal(c.requests[0].options.cache, 'no-store');
    assert.equal(c.requests[0].url.searchParams.get('dias'), '7');
});

test('sin agotados la tarjeta deja de presentar una alarma roja aunque haya stock bajo', async t => {
    const c = await pantalla(t); await c.iniciar(datos({estado_inventario: {total: 3, suficiente: 2, bajo: 1, agotado: 0}}));
    assert.equal(c.el('dashboardKpiAlertas').classList.contains('ss-dash-kpi-danger'), false);
    assert.equal(c.el('dashboardKpiAlertas').classList.contains('ss-dash-kpi-ok'), true);
    assert.equal(c.el('dashboardAlertaNota').textContent, 'Sin productos agotados');
    assert.match(c.el('dashboardResumenAlertas').textContent, /1 con stock bajo/);
});

test('sin productos ni actividad no inventa un segmento de valor uno ni un gráfico con datos', async t => {
    const c = await pantalla(t); await c.iniciar(datos({estado_inventario: {total: 0, suficiente: 0, bajo: 0, agotado: 0}, kpi_stock: 0, kpi_entradas: 0, kpi_salidas: 0, chart_entradas: Array(7).fill(0), chart_salidas: Array(7).fill(0), alertas: [], recientes: []}));
    assert.equal(c.charts.length, 0); assert.equal(c.el('dashboardSinMovimientos').hidden, false);
    assert.equal(c.el('dashboardSinProductos').hidden, false); assert.equal(c.el('dashboardVerAlertas').disabled, true);
    assert.equal(c.el('dashboardCentroEstado').hidden, true);
    assert.match(c.el('tabla-recientes').textContent, /No hay movimientos/);
    assert.equal(c.el('dashboardDatosGrafico').children.length, 7);
});

test('sin bodegas activas presenta el alcance vacío sin anunciar inventario saludable', async t => {
    const c = await pantalla(t); await c.iniciar(datos({bodega: null, bodegas: [], estado_inventario: {total: 0, suficiente: 0, bajo: 0, agotado: 0}, kpi_stock: 0, alertas: []}));
    assert.equal(c.el('dashboardBodega').disabled, true); assert.match(c.el('dashboardScope').textContent, /No hay bodegas activas/);
    assert.equal(c.el('dashboardKpiAlertas').classList.contains('ss-dash-kpi-ok'), false);
});

test('cambiar bodega limpia el alcance anterior y descarta respuestas atrasadas', async t => {
    const c = await pantalla(t); await c.iniciar();
    c.campo('dashboardBodega', '2'); assert.equal(c.el('kpi-stock').textContent, '—');
    assert.equal(c.requests[1].url.searchParams.get('bodega'), '2');
    c.campo('dashboardBodega', '1');
    await c.responder(2, {data: datos({kpi_stock: 25})}); await c.responder(1, {data: datos({bodega: {id: 2, nombre: 'Anexo'}, kpi_stock: 100})});
    assert.equal(c.el('kpi-stock').textContent, '25'); assert.equal(c.el('dashboardBodega').value, '1');
    assert.equal(c.el('dashboardContenido').getAttribute('aria-busy'), 'false');
});

test('el período de 30 días conserva la bodega y muestra cantidades enteras y tabla accesible', async t => {
    const c = await pantalla(t); await c.iniciar(); c.campo('dashboardDias', '30');
    assert.equal(c.requests[1].url.searchParams.get('dias'), '30'); assert.equal(c.requests[1].url.searchParams.get('bodega'), '1');
    await c.responder(1, {data: datos({dias: 30})});
    const g = c.charts.filter(g => g.type === 'line').at(-1);
    assert.equal(g.data.labels.length, 30); assert.equal(g.options.scales.y.ticks.precision, 0);
    assert.equal(g.data.datasets[1].borderDash.length, 2); assert.equal(c.el('dashboardDatosGrafico').children.length, 30);
});

test('una actualización pendiente no se duplica y un fallo conserva los datos con aviso de antigüedad', async t => {
    const c = await pantalla(t); await c.iniciar(); c.el('dashboardActualizar').click(); c.el('dashboardActualizar').click();
    assert.equal(c.requests.length, 2); await c.responder(1, {mensaje: 'Servidor no disponible'}, 503);
    assert.equal(c.el('kpi-stock').textContent, '15'); assert.match(c.el('dashboardActualizado').textContent, /Datos sin actualizar/);
    assert.match(c.el('dashboardError').textContent, /Servidor no disponible/); assert.equal(c.el('dashboardActualizar').disabled, false);
    c.el('dashboardActualizar').click(); await c.responder(2, {data: datos({kpi_stock: 20})});
    assert.equal(c.el('kpi-stock').textContent, '20'); assert.equal(c.el('dashboardError').hidden, true);
});

test('al regresar a una pestaña se actualiza sin generar consultas paralelas por visibilidad', async t => {
    const c = await pantalla(t); await c.iniciar();
    Object.defineProperty(c.w.document, 'hidden', {configurable: true, value: false});
    c.w.document.dispatchEvent(new c.w.Event('visibilitychange')); c.w.document.dispatchEvent(new c.w.Event('visibilitychange'));
    assert.equal(c.requests.length, 2); await c.responder(1, {data: datos()});
    Object.defineProperty(c.w.document, 'hidden', {configurable: true, value: true}); c.w.document.dispatchEvent(new c.w.Event('visibilitychange'));
    assert.equal(c.requests.length, 2);
});

test('error inicial y respuesta inválida muestran reintento sin representar ceros falsos', async t => {
    const c = await pantalla(t); c.requests[0].reject(new TypeError('Failed to fetch')); await tick();
    assert.equal(c.el('kpi-stock').textContent, '—'); assert.equal(c.el('dashboardError').hidden, false);
    assert.match(c.el('dashboardAlertaNota').textContent, /Datos no disponibles/);
    assert.doesNotMatch(c.el('tabla-recientes').textContent, /Cargando/);
    assert.match(c.el('dashboardSinProductos').textContent, /no disponible/);
    c.el('dashboardActualizar').click(); await c.responder(1, {data: {kpi_stock: 0}});
    assert.match(c.el('dashboardError').textContent, /formato inválido/);
    c.el('dashboardActualizar').click(); await c.responder(2, {data: datos()}); assert.equal(c.el('dashboardError').hidden, true);
});

test('sin biblioteca de gráficos conserva indicadores, tabla y estado por categoría', async t => {
    const c = await pantalla(t, {chart: false}); await c.iniciar();
    assert.equal(c.el('kpi-stock').textContent, '15'); assert.equal(c.el('dashboardBajo').textContent, '1');
    assert.equal(c.el('dashboardChartError').hidden, false); assert.equal(c.w.document.querySelector('.ss-dash-chart-data').open, true);
    assert.equal(c.el('tabla-recientes').querySelectorAll('.ss-dash-movement').length, 1);
});

test('el cambio de tema actualiza colores sin recargar el resumen', async t => {
    const c = await pantalla(t); await c.iniciar(); c.w.document.documentElement.setAttribute('data-bs-theme', 'dark');
    c.w.dispatchEvent(new c.w.CustomEvent('smartstock:themechange', {detail: {theme: 'dark'}}));
    assert.equal(c.charts[0].data.datasets[1].borderColor, '#93c5fd'); assert.equal(c.charts[0].updates, 1); assert.equal(c.requests.length, 1);
});

test('nombres, SKU y operadores de movimientos y alertas se insertan como texto', async t => {
    const c = await pantalla(t); const mal = '<img src=x onerror=alert(1)>';
    await c.iniciar(datos({alertas: [alerta(1, {producto: mal, sku: 'SKU/?&x=1'})], recientes: [movimiento({producto: mal, usuario: '<script>x</script>'})]}));
    assert.equal(c.el('lista-alertas').querySelector('img'), null); assert.equal(c.el('tabla-recientes').querySelector('script'), null);
    assert.match(c.el('lista-alertas').textContent, /<img/); assert.match(c.el('lista-alertas').querySelector('a').getAttribute('href'), /SKU%2F%3F%26x%3D1/);
    assert.equal(new URL(c.el('lista-alertas').querySelector('a').href).searchParams.get('bodega'), '1');
    assert.match(c.el('tabla-recientes').textContent, /27\/10\/2026/); assert.match(c.el('tabla-recientes').textContent, /23:30:00/);
    assert.match(c.el('tabla-recientes').textContent, /Salida/); assert.doesNotMatch(c.el('tabla-recientes').textContent, /Completada/);
    assert.equal(c.w.document.querySelector('.ss-dash-recent .card-header a').getAttribute('href'), '/movimientos/');
});

test('permisos de servidor controlan accesos aunque la sesión local diga administrador', async t => {
    const c = await pantalla(t); await c.iniciar(datos({permisos: {registrar_movimiento: false, usuarios: false, auditoria: false, configuracion: false}}));
    for (const id of ['dashboardRegistrar', 'menu-usuarios', 'menu-auditoria', 'menu-config', 'menu-sistema-title']) assert.equal(c.el(id).hidden, true);
});

test('sesión local malformada no impide cargar datos autorizados por servidor', async t => {
    const c = await pantalla(t, {sesion: 'no-json'}); await c.iniciar(); assert.equal(c.el('user-name').textContent, 'Usuario'); assert.equal(c.el('kpi-stock').textContent, '15');
});

test('alertas recorre páginas reales conservando bodega, búsqueda y estado', async t => {
    const c = await pantalla(t); await c.iniciar(); c.abrirAlertas(); await c.responder(1, pagina());
    assert.equal(c.el('dashboardListaAlertas').children.length, 25);
    assert.equal(c.el('dashboardPaginasAlertas').querySelector('button[data-page="0"]').disabled, true);
    assert.equal(c.el('dashboardPaginasAlertas').querySelector('button[data-page="0"]').parentElement.classList.contains('disabled'), true);
    c.campo('dashboardBuscarAlerta', 'Producto', 'input'); await c.debounce(); await c.responder(2, pagina());
    c.campo('dashboardEstadoAlerta', 'bajo'); await c.responder(3, pagina());
    c.el('dashboardPaginasAlertas').querySelector('button[data-page="2"]').click();
    const p = c.requests[4].url.searchParams;
    for (const [key, value] of Object.entries({page: '2', search: 'Producto', estado: 'bajo', bodega: '1'})) assert.equal(p.get(key), value);
    await c.responder(4, pagina(55, 2)); assert.match(c.el('dashboardContadorAlertas').textContent, /26–50 de 55/);
});

test('buscar alertas invalida la respuesta previa durante el debounce', async t => {
    const c = await pantalla(t); await c.iniciar(); c.abrirAlertas(); await c.responder(1, pagina());
    c.el('dashboardPaginasAlertas').querySelector('button[data-page="2"]').click(); c.campo('dashboardBuscarAlerta', 'Nueva', 'input');
    await c.responder(2, pagina(55, 2)); assert.equal(c.el('dashboardListaAlertas').children.length, 0);
    await c.debounce(); await c.responder(3, pagina(0)); assert.match(c.el('dashboardContadorAlertas').textContent, /No hay productos/);
});

test('página desaparecida se recupera mediante last una sola vez y permite reintentar', async t => {
    const c = await pantalla(t); await c.iniciar(); c.abrirAlertas(); await c.responder(1, pagina());
    c.el('dashboardPaginasAlertas').querySelector('button[data-page="3"]').click(); await c.responder(2, {}, 404);
    assert.equal(c.requests[3].url.searchParams.get('page'), 'last'); await c.responder(3, {}, 404);
    assert.equal(c.requests.length, 4); assert.equal(c.el('dashboardReintentarAlertas').hidden, false);
    c.el('dashboardReintentarAlertas').click(); await c.responder(4, pagina(55, 3)); assert.equal(c.el('dashboardReintentarAlertas').hidden, true);
});

test('cerrar el modal de alertas descarta la respuesta que seguía pendiente', async t => {
    const c = await pantalla(t); await c.iniciar(); c.abrirAlertas(); c.modelos.get(c.el('modalDashboardAlertas')).hide();
    await c.responder(1, pagina()); assert.equal(c.el('dashboardListaAlertas').children.length, 0);
});

test('detalle consulta el movimiento real e ignora una respuesta tras cerrar', async t => {
    const c = await pantalla(t); await c.iniciar(); c.el('tabla-recientes').querySelector('button').click();
    assert.equal(c.requests[1].url.pathname, '/api/v1/productos/movimientos/4/');
    await c.responder(1, {data: movimiento()}); assert.match(c.el('dashboardDetalleDatos').textContent, /Guía 123/); assert.match(c.el('dashboardDetalleDatos').textContent, /27\/10\/2026 23:30:00/);
    c.modelos.get(c.el('modalDashboardDetalle')).hide(); c.el('tabla-recientes').querySelector('button').click();
    c.modelos.get(c.el('modalDashboardDetalle')).hide(); await c.responder(2, {data: movimiento({producto: 'Respuesta atrasada'})});
    assert.equal(c.el('dashboardDetalleDatos').children.length, 0);
});

test('solicitudes concurrentes con JWT vencido comparten renovación y reintentan con el token nuevo', async t => {
    const c = await pantalla(t); await c.iniciar(); c.el('dashboardActualizar').click(); c.el('tabla-recientes').querySelector('button').click();
    await c.responder(1, {}, 401); await c.responder(2, {}, 401);
    assert.equal(c.requests.filter(r => r.url.pathname === '/api/v1/auth/refresh/').length, 1);
    await c.responder(3, {access: 'nuevo', refresh: 'rotado'});
    assert.equal(c.requests[4].options.headers.Authorization, 'Bearer nuevo'); assert.equal(c.requests[5].options.headers.Authorization, 'Bearer nuevo');
    await c.responder(4, {data: datos()}); await c.responder(5, {data: movimiento()});
    assert.equal(c.w.localStorage.getItem('refresh_token'), 'rotado'); assert.match(c.el('dashboardDetalleDatos').textContent, /Guía/);
});

test('un rechazo de acceso borra los indicadores anteriores y los accesos protegidos', async t => {
    const c = await pantalla(t); await c.iniciar(); c.el('dashboardActualizar').click(); await c.responder(1, {}, 403);
    assert.equal(c.el('kpi-stock').textContent, '—'); assert.equal(c.el('menu-usuarios').hidden, true); assert.match(c.el('dashboardError').textContent, /no tiene acceso/);
});
