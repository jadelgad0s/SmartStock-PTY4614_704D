const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const root = path.resolve(__dirname, '../..');
const html = readFileSync(path.join(root, 'templates/auditoria.html'), 'utf8').replace(/{%[\s\S]*?%}/g, '');
const fuente = readFileSync(path.join(root, 'static/js/auditoria.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
const evento = id => ({id, fecha: '27/10/2026 20:30:12', zona_horaria: 'America/Santiago', usuario: 'Javier Delgado',
    usuario_email: 'javier@example.com', accion: 'LOGIN_FAILED', accion_etiqueta: 'Acceso fallido', modelo: 'Usuario',
    descripcion: 'Intento de acceso.\nDescripción completa.', objeto_id: '10', ip_address: '192.0.2.1', user_agent: 'Navegador de prueba'});
function paginaDatos(count = 55, pagina = 1) {
    return {count, zona_horaria: 'America/Santiago', results: Array.from({length: Math.max(0, Math.min(25, count - (pagina - 1) * 25))},
        (_, i) => evento((pagina - 1) * 25 + i + 1))};
}
const opciones = {success: true, data: {usuarios: [{id: 1, nombre: 'Javier Delgado', email: 'javier@example.com'}], sin_usuario: true,
    acciones: [{valor: 'LOGIN', etiqueta: 'Inicio de sesión'}, {valor: 'LOGIN_FAILED', etiqueta: 'Acceso fallido'},
        {valor: 'DEACTIVATE', etiqueta: 'Desactivación'}, {valor: 'REACTIVATE', etiqueta: 'Reactivación'},
        {valor: 'DELETE', etiqueta: 'Eliminación definitiva'}], modelos: ['Usuario', 'Movimiento']}};

async function pantalla(t, usuario = {rol_nombre: 'Administrador'}) {
    const dom = new JSDOM(html, {url: 'http://localhost/auditoria/', runScripts: 'outside-only', pretendToBeVisual: true});
    t.after(() => dom.window.close());
    const w = dom.window;
    const requests = [], descargas = [], blobs = [], impresiones = [];
    const timers = new Map(), modelos = new Map();
    let timer = 0;
    w.localStorage.setItem('access_token', 'token-prueba');
    w.localStorage.setItem('usuario', JSON.stringify(usuario));
    w.HTMLElement.prototype.scrollIntoView = () => {};
    w.HTMLAnchorElement.prototype.click = function () { descargas.push({nombre: this.download, url: this.href}); };
    w.URL.createObjectURL = blob => { blobs.push(blob); return 'blob:http://localhost/' + blobs.length; };
    w.URL.revokeObjectURL = () => {};
    const crear = w.document.createElement.bind(w.document);
    w.document.createElement = (...args) => {
        const elemento = crear(...args);
        if (String(args[0]).toLowerCase() === 'iframe') elemento.addEventListener('load', () => {
            elemento.contentWindow.focus = () => {};
            elemento.contentWindow.print = () => impresiones.push(elemento.srcdoc);
        }, {capture: true});
        return elemento;
    };
    w.bootstrap = {Modal: {getOrCreateInstance(elemento) {
        if (!modelos.has(elemento)) modelos.set(elemento, {
            show() { elemento.classList.add('show'); elemento.dispatchEvent(new w.Event('shown.bs.modal')); },
            hide() {
                elemento.dispatchEvent(new w.Event('hide.bs.modal'));
                elemento.classList.remove('show');
                elemento.dispatchEvent(new w.Event('hidden.bs.modal'));
            },
        });
        return modelos.get(elemento);
    }}};
    w.setTimeout = (fn, delay) => { timers.set(++timer, {fn, delay}); return timer; };
    w.clearTimeout = id => timers.delete(id);
    w.fetch = (url, options) => new Promise((resolve, reject) => requests.push({url: new URL(url, w.location.href), options, resolve, reject}));
    w.eval(fuente);
    await tick();
    const el = id => w.document.getElementById(id);
    const campo = (id, value, tipo = 'change') => { el(id).value = value; el(id).dispatchEvent(new w.Event(tipo)); };
    const responder = async (index, data, status = 200, tipo = 'application/json') => {
        requests[index].resolve({ok: status >= 200 && status < 300, status,
            headers: new Headers({'Content-Type': tipo, 'Content-Disposition': 'attachment; filename="auditoria-prueba.csv"'}),
            json: async () => data, text: async () => String(data), blob: async () => new Blob([String(data)], {type: tipo})});
        await tick();
    };
    const debounce = async () => {
        const pendientes = [...timers.entries()].filter(([, v]) => v.delay === 300);
        pendientes.forEach(([id, v]) => { timers.delete(id); v.fn(); });
        await tick();
    };
    const iniciar = async (datos = paginaDatos()) => { await responder(1, opciones); await responder(0, datos); };
    return {w, el, requests, descargas, blobs, impresiones, modelos, campo, responder, debounce, iniciar};
}

test('auditoría consulta el historial completo y mantiene todos los filtros al paginar', async t => {
    const c = await pantalla(t);
    assert.equal(c.requests[0].url.pathname, '/api/v1/auditoria/historial/');
    assert.equal(c.el('exportarAuditoria').disabled, true);
    await c.iniciar();
    c.campo('buscarAuditoria', 'FER-022', 'input');
    c.campo('usuarioAuditoria', '1');
    c.campo('accionAuditoria', 'LOGIN_FAILED');
    c.campo('modeloAuditoria', 'Usuario');
    c.campo('desdeAuditoria', '2026-10-20');
    c.campo('hastaAuditoria', '2026-10-27');
    await c.responder(c.requests.length - 1, paginaDatos());
    c.el('paginacionAuditoria').querySelector('button[data-page="2"]').click();
    const params = c.requests.at(-1).url.searchParams;
    for (const [key, value] of Object.entries({search: 'FER-022', usuario: '1', accion: 'LOGIN_FAILED', modelo: 'Usuario', desde: '2026-10-20', hasta: '2026-10-27', page: '2'})) assert.equal(params.get(key), value);
    await c.responder(c.requests.length - 1, paginaDatos(55, 2));
    assert.equal(c.el('listaAuditoria').querySelectorAll('.ss-audit-row').length, 25);
    assert.match(c.el('resumenAuditoria').textContent, /26–50 de 55 eventos/);
    assert.match(c.el('zonaHorariaAuditoria').textContent, /America\/Santiago/);
});

test('buscar invalida respuestas anteriores y exportación antes del debounce', async t => {
    const c = await pantalla(t);
    await c.iniciar();
    c.el('paginacionAuditoria').querySelector('button[data-page="2"]').click();
    const vieja = c.requests.length - 1;
    c.campo('buscarAuditoria', 'Nueva consulta', 'input');
    assert.equal(c.el('exportarAuditoria').disabled, true);
    assert.equal(c.el('paginacionAuditoria').children.length, 0);
    await c.responder(vieja, paginaDatos(55, 2));
    assert.match(c.el('resumenAuditoria').textContent, /Cargando/);
    await c.debounce();
    assert.equal(c.requests.at(-1).url.searchParams.get('page'), '1');
    await c.responder(c.requests.length - 1, paginaDatos(1));
    assert.match(c.el('resumenAuditoria').textContent, /1–1 de 1/);
});

test('filtros móviles, fechas inválidas y limpieza conservan un estado coherente', async t => {
    const c = await pantalla(t);
    await c.iniciar();
    c.el('mostrarFiltrosAuditoria').click();
    assert.equal(c.el('mostrarFiltrosAuditoria').getAttribute('aria-expanded'), 'true');
    c.campo('desdeAuditoria', '2026-10-28');
    const cantidad = c.requests.length;
    c.campo('hastaAuditoria', '2026-10-27');
    assert.equal(c.requests.length, cantidad);
    assert.match(c.el('errorHistorialAuditoria').textContent, /posterior/);
    assert.equal(c.el('imprimirAuditoria').disabled, true);
    c.el('limpiarFiltrosAuditoria').click();
    assert.equal(c.requests.at(-1).url.searchParams.has('desde'), false);
    assert.equal(c.requests.at(-1).url.searchParams.get('page'), '1');
    await c.responder(c.requests.length - 1, paginaDatos());
    assert.equal(c.el('errorHistorialAuditoria').classList.contains('d-none'), true);
    assert.equal(c.el('imprimirAuditoria').disabled, false);
});

test('página desaparecida se recupera una sola vez con page=last', async t => {
    const c = await pantalla(t);
    await c.iniciar();
    c.el('paginacionAuditoria').querySelector('button[data-page="3"]').click();
    await c.responder(c.requests.length - 1, {}, 404);
    assert.equal(c.requests.at(-1).url.searchParams.get('page'), 'last');
    await c.responder(c.requests.length - 1, paginaDatos(26, 2));
    assert.match(c.el('resumenAuditoria').textContent, /26–26 de 26/);
    c.el('paginacionAuditoria').querySelector('button[data-page="1"]').click();
    await c.responder(c.requests.length - 1, {}, 404);
    assert.match(c.el('resumenAuditoria').textContent, /Error/);
});

test('detalle muestra texto completo sin interpretar HTML ni inventar IP o navegador', async t => {
    const c = await pantalla(t);
    const e = {...evento(1), descripcion: '<img src=x onerror=alert(1)>\n' + 'Texto completo '.repeat(100), ip_address: null, user_agent: ''};
    await c.iniciar({count: 1, results: [e]});
    assert.equal(c.el('listaAuditoria').querySelectorAll('img').length, 0);
    assert.equal(c.el('listaAuditoria').querySelector('.ss-audit-badge-failed').textContent, 'Acceso fallido');
    c.el('listaAuditoria').querySelector('button[data-detalle]').click();
    await c.responder(c.requests.length - 1, {data: e});
    assert.equal(c.el('detalleAuditoriaDescripcion').textContent, e.descripcion);
    assert.equal(c.el('detalleAuditoriaDescripcion').querySelector('img'), null);
    assert.equal(c.el('detalleAuditoriaIp').textContent, 'No registrada.');
    assert.equal(c.el('detalleAuditoriaAgente').textContent, 'No registrado.');
    assert.equal(c.el('detalleAuditoriaRegistrada').hidden, true);
    c.modelos.get(c.el('modalDetalleAuditoria')).hide();
    assert.equal(c.w.document.activeElement.dataset.detalle, '1');
});

test('detalle cerrado ignora respuestas tardías y conserva el evento siguiente', async t => {
    const c = await pantalla(t);
    await c.iniciar();
    const botones = c.el('listaAuditoria').querySelectorAll('button[data-detalle]');
    botones[0].click();
    const vieja = c.requests.length - 1;
    c.modelos.get(c.el('modalDetalleAuditoria')).hide();
    botones[1].click();
    await c.responder(c.requests.length - 1, {data: evento(2)});
    await c.responder(vieja, {data: evento(1)});
    assert.equal(c.el('detalleAuditoriaId').textContent, '#2');
});

test('opciones de filtro fallidas pueden reintentarse sin bloquear el historial', async t => {
    const c = await pantalla(t);
    await c.responder(0, paginaDatos());
    await c.responder(1, {}, 500);
    assert.equal(c.el('listaAuditoria').querySelectorAll('.ss-audit-row').length, 25);
    assert.equal(c.el('reintentarOpcionesAuditoria').classList.contains('d-none'), false);
    c.el('reintentarOpcionesAuditoria').click();
    await c.responder(c.requests.length - 1, opciones);
    assert.equal(c.el('usuarioAuditoria').disabled, false);
    assert.ok([...c.el('usuarioAuditoria').options].some(o => o.value === 'sin_usuario'));
    assert.equal(c.el('errorOpcionesAuditoria').classList.contains('d-none'), true);
});

test('CSV incluye filtros sin page ni token en URL, usa autenticación y bloquea dobles descargas', async t => {
    const c = await pantalla(t);
    await c.iniciar();
    c.campo('modeloAuditoria', 'Movimiento');
    await c.responder(c.requests.length - 1, paginaDatos());
    c.el('paginacionAuditoria').querySelector('button[data-page="2"]').click();
    await c.responder(c.requests.length - 1, paginaDatos(55, 2));
    const antes = c.requests.length;
    c.el('exportarAuditoria').click();
    c.el('exportarAuditoria').dispatchEvent(new c.w.Event('click'));
    assert.equal(c.requests.length, antes + 1);
    const request = c.requests.at(-1);
    assert.equal(request.url.pathname, '/api/v1/auditoria/exportar/');
    assert.equal(request.url.searchParams.get('modelo'), 'Movimiento');
    assert.equal(request.url.searchParams.has('page'), false);
    assert.equal(request.url.href.includes('token-prueba'), false);
    assert.equal(request.options.headers.Authorization, 'Bearer token-prueba');
    await c.responder(c.requests.length - 1, 'ID;Descripción\n1;Evento', 200, 'text/csv; charset=utf-8');
    assert.equal(c.descargas.length, 1);
    assert.equal(c.descargas[0].nombre, 'auditoria-prueba.csv');
    assert.match(await c.blobs[0].text(), /ID;Descripción/);
    assert.match(c.el('estadoExportarAuditoria').textContent, /todos los resultados/);
    assert.equal(c.el('exportarAuditoria').disabled, false);
});

test('impresión carga el documento completo en su propio marco y no imprime la tabla paginada', async t => {
    const c = await pantalla(t);
    await c.iniciar();
    c.el('imprimirAuditoria').click();
    assert.equal(c.requests.at(-1).url.pathname, '/api/v1/auditoria/reporte/');
    assert.equal(c.requests.at(-1).url.searchParams.has('page'), false);
    const reporte = '<!doctype html><html><body><h1>55 eventos</h1><table><tr><td>Evento 55</td></tr></table></body></html>';
    await c.responder(c.requests.length - 1, reporte, 200, 'text/html; charset=utf-8');
    await tick();
    assert.deepEqual(c.impresiones, [reporte]);
    assert.equal(c.el('listaAuditoria').querySelectorAll('.ss-audit-row').length, 25);
    assert.equal(c.el('imprimirAuditoria').disabled, false);
    assert.match(c.el('estadoExportarAuditoria').textContent, /reporte completo/);
});

test('reportes rechazados o con formato incorrecto no descargan archivos ni abren impresión', async t => {
    const c = await pantalla(t);
    await c.iniciar();
    c.el('exportarAuditoria').click();
    await c.responder(c.requests.length - 1, '<html>Login</html>', 200, 'text/html');
    assert.equal(c.descargas.length, 0);
    assert.match(c.el('estadoExportarAuditoria').textContent, /reporte válido/);
    c.el('imprimirAuditoria').click();
    await c.responder(c.requests.length - 1, {}, 403);
    assert.equal(c.impresiones.length, 0);
    assert.match(c.el('estadoExportarAuditoria').textContent, /administradores activos/);
    assert.equal(c.el('imprimirAuditoria').disabled, false);
});

test('historial vacío informa cero y fallos posteriores retiran paginación y exportación', async t => {
    const c = await pantalla(t);
    await c.iniciar(paginaDatos(0));
    assert.equal(c.el('resumenAuditoria').textContent, '0 eventos');
    assert.equal(c.el('paginacionAuditoria').children.length, 0);
    c.campo('buscarAuditoria', 'Texto', 'input');
    await c.debounce();
    c.requests.at(-1).reject(new Error('Network'));
    await tick();
    assert.match(c.el('errorHistorialAuditoria').textContent, /conectar/);
    assert.equal(c.el('exportarAuditoria').disabled, true);
    assert.equal(c.el('listaAuditoria').getAttribute('aria-busy'), 'false');
});

test('paginación con teclado devuelve el foco al resumen y admite superusuario sin rol', async t => {
    const c = await pantalla(t, {is_superuser: true});
    await c.iniciar();
    const boton = c.el('paginacionAuditoria').querySelector('button[data-page="2"]');
    boton.focus();
    boton.click();
    await c.responder(c.requests.length - 1, paginaDatos(55, 2));
    assert.equal(c.w.document.activeElement, c.el('resumenAuditoria'));
});

test('desactivación, reactivación y eliminación definitiva tienen insignias distintas', async t => {
    const c = await pantalla(t);
    const acciones = [['DEACTIVATE', 'Desactivación', 'deactivate'], ['REACTIVATE', 'Reactivación', 'reactivate'], ['DELETE', 'Eliminación definitiva', 'delete']];
    await c.iniciar({count: 3, results: acciones.map(([accion, accion_etiqueta], i) => ({...evento(i + 1), accion, accion_etiqueta}))});
    for (const [, etiqueta, clase] of acciones) assert.equal(c.el('listaAuditoria').querySelector('.ss-audit-badge-' + clase).textContent, etiqueta);
    assert.equal(c.el('accionAuditoria').querySelector('[value="DEACTIVATE"]').textContent, 'Desactivación');
    assert.equal(c.el('accionAuditoria').querySelector('[value="DELETE"]').textContent, 'Eliminación definitiva');
});

test('detalle de una desactivación histórica muestra la clasificación y el código registrado', async t => {
    const c = await pantalla(t), e = {...evento(1), accion: 'DEACTIVATE', accion_etiqueta: 'Desactivación', accion_registrada: 'DELETE'};
    await c.iniciar({count: 1, results: [e]}); c.el('listaAuditoria').querySelector('button[data-detalle]').click(); await c.responder(c.requests.length - 1, {data: e});
    assert.equal(c.el('detalleAuditoriaCodigo').textContent, 'DEACTIVATE');
    assert.equal(c.el('detalleAuditoriaAccion').querySelector('.ss-audit-badge-deactivate').textContent, 'Desactivación');
    assert.equal(c.el('detalleAuditoriaRegistrada').textContent, 'DELETE'); assert.equal(c.el('detalleAuditoriaRegistrada').hidden, false);
    assert.equal(c.el('detalleAuditoriaRegistradaEtiqueta').hidden, false);
});

test('un evento nuevo oculta el código histórico anterior y usa la insignia de reactivación', async t => {
    const c = await pantalla(t), antiguo = {...evento(1), accion: 'DEACTIVATE', accion_etiqueta: 'Desactivación', accion_registrada: 'DELETE'}, nuevo = {...evento(2), accion: 'REACTIVATE', accion_etiqueta: 'Reactivación', accion_registrada: 'REACTIVATE'};
    await c.iniciar({count: 2, results: [antiguo, nuevo]}); const botones = c.el('listaAuditoria').querySelectorAll('button[data-detalle]');
    botones[0].click(); await c.responder(c.requests.length - 1, {data: antiguo}); c.modelos.get(c.el('modalDetalleAuditoria')).hide();
    botones[1].click(); await c.responder(c.requests.length - 1, {data: nuevo});
    assert.equal(c.el('detalleAuditoriaRegistrada').hidden, true); assert.equal(c.el('detalleAuditoriaRegistrada').textContent, '');
    assert.equal(c.el('detalleAuditoriaAccion').querySelector('.ss-audit-badge-reactivate').textContent, 'Reactivación');
});

test('las tres acciones conservan su filtro al cambiar de página', async t => {
    const c = await pantalla(t); await c.iniciar();
    for (const accion of ['DEACTIVATE', 'REACTIVATE', 'DELETE']) {
        c.campo('accionAuditoria', accion); assert.equal(c.requests.at(-1).url.searchParams.get('accion'), accion);
        await c.responder(c.requests.length - 1, paginaDatos()); c.el('paginacionAuditoria').querySelector('button[data-page="2"]').click();
        assert.equal(c.requests.at(-1).url.searchParams.get('accion'), accion); assert.equal(c.requests.at(-1).url.searchParams.get('page'), '2');
        await c.responder(c.requests.length - 1, paginaDatos(55, 2));
    }
});

test('CSV y reporte imprimible reciben el filtro de desactivación sin limitarse a la página', async t => {
    const c = await pantalla(t); await c.iniciar(); c.campo('accionAuditoria', 'DEACTIVATE'); await c.responder(c.requests.length - 1, paginaDatos());
    c.el('exportarAuditoria').click(); assert.equal(c.requests.at(-1).url.searchParams.get('accion'), 'DEACTIVATE');
    assert.equal(c.requests.at(-1).url.searchParams.has('page'), false);
    await c.responder(c.requests.length - 1, 'ID;Acción;Código registrado\n1;Desactivación;DELETE', 200, 'text/csv; charset=utf-8');
    assert.match(await c.blobs[0].text(), /Desactivación;DELETE/); c.el('imprimirAuditoria').click();
    assert.equal(c.requests.at(-1).url.pathname, '/api/v1/auditoria/reporte/');
    assert.equal(c.requests.at(-1).url.searchParams.get('accion'), 'DEACTIVATE'); assert.equal(c.requests.at(-1).url.searchParams.has('page'), false);
});

test('el código registrado de un evento histórico se presenta como texto', async t => {
    const c = await pantalla(t), e = {...evento(1), accion: 'DEACTIVATE', accion_etiqueta: 'Desactivación', accion_registrada: '<img src=x>'};
    await c.iniciar({count: 1, results: [e]}); c.el('listaAuditoria').querySelector('button[data-detalle]').click(); await c.responder(c.requests.length - 1, {data: e});
    assert.equal(c.el('detalleAuditoriaRegistrada').textContent, '<img src=x>'); assert.equal(c.el('detalleAuditoriaRegistrada').querySelector('img'), null);
});
