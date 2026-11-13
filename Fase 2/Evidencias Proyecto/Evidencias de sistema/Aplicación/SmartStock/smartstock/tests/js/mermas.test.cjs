const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const root = path.resolve(__dirname, '../..');
const html = readFileSync(path.join(root, 'templates/mermas.html'), 'utf8').replace(/{%[\s\S]*?%}/g, '');
const fuente = readFileSync(path.join(root, 'static/js/mermas.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
const merma = id => ({id, fecha: '27/10/2026 12:30', producto: 'Bebida Cherry', sku: 'BEBIDA', cantidad: 3,
    motivo: 'Daño en Bodega', motivo_codigo: 'DAÑO', observacion: 'Envase roto.\nObservación completa.',
    responsable: 'Persona Prueba', bodega: 'Bodega Central', estado: 'Registrada'});
const producto = id => ({id, nombre: 'Bebida ' + id, sku: 'SKU-' + id, stock_disponible: 10, bodega: 'Bodega Central'});
function paginaDatos(crear, count = 55, pagina = 1) {
    return {count, results: Array.from({length: Math.max(0, Math.min(25, count - (pagina - 1) * 25))},
        (_, i) => crear((pagina - 1) * 25 + i + 1))};
}
async function pantalla(t, opcionesIniciales = true) {
    const dom = new JSDOM(html, {url: 'http://localhost/mermas/', runScripts: 'outside-only', pretendToBeVisual: true});
    t.after(() => dom.window.close());
    const w = dom.window;
    const requests = [];
    const timers = new Map();
    let timer = 0;
    const modelos = new Map();
    w.localStorage.setItem('access_token', 'test');
    w.localStorage.setItem('usuario', JSON.stringify({rol_nombre: 'Administrador'}));
    w.matchMedia = () => ({matches: false});
    w.HTMLElement.prototype.scrollIntoView = () => {};
    w.bootstrap = {Modal: {getOrCreateInstance(elemento) {
        if (!modelos.has(elemento)) modelos.set(elemento, {
            show() {
                if (!elemento.dispatchEvent(new w.Event('show.bs.modal', {cancelable: true}))) return;
                elemento.classList.add('show');
                elemento.dispatchEvent(new w.Event('shown.bs.modal'));
            },
            hide() {
                if (!elemento.dispatchEvent(new w.Event('hide.bs.modal', {cancelable: true}))) return;
                elemento.classList.remove('show');
                elemento.dispatchEvent(new w.Event('hidden.bs.modal'));
            },
        });
        return modelos.get(elemento);
    }}};
    w.setTimeout = fn => { timers.set(++timer, fn); return timer; };
    w.clearTimeout = id => timers.delete(id);
    w.fetch = (url, options) => opcionesIniciales && new URL(url, w.location.href).pathname === '/api/v1/bodegas/opciones/' ?
        Promise.resolve({ok: true, status: 200, json: async () => require('./bodegas-fixture.cjs')()}) : new Promise((resolve, reject) => requests.push({
        url: new URL(url, w.location.href), options, resolve, reject,
    }));
    const avisos = []; w.addEventListener('smartstock:notifications-changed', () => avisos.push(true));
    w.eval(fuente);
    await tick();
    const el = id => w.document.getElementById(id);
    const campo = (id, value, evento = 'input') => {
        el(id).value = value;
        el(id).dispatchEvent(new w.Event(evento));
    };
    const responder = async (index, data, status = 200) => {
        requests[index].resolve({ok: status >= 200 && status < 300, status, json: async () => data});
        await tick();
    };
    const debounce = async () => {
        const callbacks = [...timers.values()];
        timers.clear();
        callbacks.forEach(fn => fn());
        await tick();
    };
    const abrir = () => modelos.get(el('modalNuevaMerma')).show();
    const enviar = () => el('formNuevaMerma').dispatchEvent(new w.Event('submit', {cancelable: true}));
    const completar = async () => {
        abrir();
        await responder(requests.length - 1, paginaDatos(producto));
        campo('mermaProducto', '1', 'change');
        campo('mermaCantidad', '3');
        campo('mermaObservacion', 'Envase roto.');
    };
    return {w, el, avisos, requests, modelos, campo, responder, debounce, abrir, enviar, completar};
}

test('mermas usa historial completo y conserva búsqueda, motivo y fechas entre páginas', async t => {
    const c = await pantalla(t);
    assert.equal(c.requests[0].url.pathname, '/api/v1/productos/mermas/historial/');
    await c.responder(0, paginaDatos(merma));
    c.campo('buscarMermas', 'Bebida');
    c.campo('motivoMermas', 'DAÑO', 'change');
    await c.debounce();
    assert.equal(c.requests.length, 2);
    await c.responder(1, paginaDatos(merma));
    c.el('desdeMermas').value = '2026-10-01';
    c.campo('hastaMermas', '2026-10-27', 'change');
    await c.responder(2, paginaDatos(merma));
    c.el('paginacionMermas').querySelector('button[data-page="2"]').click();
    const params = c.requests[3].url.searchParams;
    for (const [key, value] of Object.entries({page: '2', search: 'Bebida', motivo: 'DAÑO', desde: '2026-10-01', hasta: '2026-10-27'})) assert.equal(params.get(key), value);
    await c.responder(3, paginaDatos(merma, 55, 2));
    assert.match(c.el('resumenMermas').textContent, /26–50 de 55/);
});

test('respuesta anterior al debounce no restaura resultados de otra búsqueda', async t => {
    const c = await pantalla(t);
    c.campo('buscarMermas', 'Nueva');
    await c.responder(0, paginaDatos(merma));
    assert.equal(c.el('listaMermas').querySelectorAll('.ss-loss-row').length, 0);
    await c.debounce();
    await c.responder(1, {count: 0, results: []});
    assert.equal(c.el('resumenMermas').textContent, '0 mermas');
    assert.equal(c.el('paginacionMermas').childElementCount, 0);
});

test('filtros móviles indican su estado y el rango inválido no consulta al servidor', async t => {
    const c = await pantalla(t);
    await c.responder(0, paginaDatos(merma));
    c.el('mostrarFiltrosMermas').click();
    assert.equal(c.el('mostrarFiltrosMermas').getAttribute('aria-expanded'), 'true');
    c.el('desdeMermas').value = '2026-10-28';
    c.campo('hastaMermas', '2026-10-27', 'change');
    assert.equal(c.requests.length, 1);
    assert.match(c.el('errorHistorialMermas').textContent, /fecha inicial/);
    c.el('limpiarFiltrosMermas').click();
    assert.equal(c.requests.length, 2);
    assert.equal(c.requests[1].url.searchParams.has('desde'), false);
    assert.equal(c.el('mostrarFiltrosMermas').textContent, 'Filtros');
});

test('recupera una página eliminada mediante last sin un ciclo de reintentos', async t => {
    const c = await pantalla(t);
    await c.responder(0, paginaDatos(merma));
    c.el('paginacionMermas').querySelector('button[data-page="3"]').click();
    await c.responder(1, {detail: 'Página inválida'}, 404);
    assert.equal(c.requests[2].url.searchParams.get('page'), 'last');
    await c.responder(2, {detail: 'No disponible'}, 404);
    assert.equal(c.requests.length, 3);
    assert.equal(c.el('listaMermas').getAttribute('aria-busy'), 'false');
});

test('detalle y observación completa son texto seguro, incluso con etiquetas HTML', async t => {
    const c = await pantalla(t);
    const m = {...merma(1), producto: '<img src=x onerror=alert(1)>', observacion: 'Primera línea.\n' + 'Detalle completo. '.repeat(70)};
    await c.responder(0, {count: 1, results: [m]});
    assert.equal(c.el('listaMermas').querySelector('img'), null);
    c.el('listaMermas').querySelector('[data-detalle]').click();
    await c.responder(1, {data: m});
    assert.equal(c.el('detalleMermaObservacion').textContent, m.observacion);
    assert.equal(c.el('detalleMermaProducto').textContent, m.producto);
    assert.equal(c.el('detalleMermaEstado').textContent, 'Registrada');
});

test('selección de productos recorre todas las páginas y muestra stock de Bodega Central', async t => {
    const c = await pantalla(t);
    await c.responder(0, paginaDatos(merma));
    c.abrir();
    assert.equal(c.requests[1].url.pathname, '/api/v1/productos/mermas/productos/');
    await c.responder(1, paginaDatos(producto));
    c.el('mermaProductosSiguiente').click();
    assert.equal(c.requests[2].url.searchParams.get('page'), '2');
    await c.responder(2, paginaDatos(producto, 55, 2));
    c.campo('mermaProducto', '26', 'change');
    assert.match(c.el('mermaStockDisponible').textContent, /Bodega Central: 10/);
    assert.match(c.el('resumenProductosMerma').textContent, /26–50 de 55/);
});

test('escribir una búsqueda de producto invalida inmediatamente la selección anterior', async t => {
    const c = await pantalla(t);
    await c.responder(0, paginaDatos(merma));
    await c.completar();
    assert.equal(c.el('btnGuardarMerma').disabled, false);
    c.campo('mermaBuscarProducto', 'COD/99');
    assert.equal(c.el('btnGuardarMerma').disabled, true);
    assert.equal(c.el('mermaProducto').value, '');
    c.enviar();
    assert.equal(c.requests.length, 2);
    await c.debounce();
    assert.equal(c.requests[2].url.searchParams.get('search'), 'COD/99');
    await c.responder(2, {count: 1, results: [producto(99)]});
    c.campo('mermaProducto', '99', 'change');
    assert.match(c.el('mermaResumenConfirmacion').textContent, /Bebida 99/);
});

test('una respuesta atrasada del catálogo no permite seleccionar un producto anterior', async t => {
    const c = await pantalla(t);
    await c.responder(0, paginaDatos(merma));
    c.abrir();
    c.campo('mermaBuscarProducto', 'Nueva');
    await c.responder(1, paginaDatos(producto));
    assert.equal(c.el('mermaProducto').disabled, true);
    await c.debounce();
    await c.responder(2, {count: 0, results: []});
    assert.equal(c.el('mermaProducto').disabled, true);
    assert.equal(c.el('btnGuardarMerma').disabled, true);
});

test('no confirma cantidades inválidas, observación vacía ni stock insuficiente', async t => {
    const c = await pantalla(t);
    await c.responder(0, paginaDatos(merma));
    await c.completar();
    for (const value of ['11', '0', '-1', '1.5']) {
        c.campo('mermaCantidad', value);
        c.enviar();
        assert.equal(c.el('btnGuardarMerma').disabled, true);
    }
    assert.equal(c.requests.length, 2);
    c.campo('mermaCantidad', '3');
    c.campo('mermaObservacion', '   ');
    assert.equal(c.el('btnGuardarMerma').disabled, true);
    c.campo('mermaObservacion', 'Daño comprobado');
    assert.equal(c.el('btnGuardarMerma').disabled, false);
    assert.match(c.el('mermaResumenConfirmacion').textContent, /Stock restante estimado: 7/);
});

test('doble envío y clic tras guardar producen una sola baja y una recarga real', async t => {
    const c = await pantalla(t);
    await c.responder(0, paginaDatos(merma));
    await c.completar();
    c.enviar();
    c.enviar();
    assert.equal(c.requests.length, 3);
    assert.equal(c.requests[2].options.method, 'POST');
    assert.equal(JSON.parse(c.requests[2].options.body).cantidad, 3);
    c.modelos.get(c.el('modalNuevaMerma')).hide();
    assert.ok(c.el('modalNuevaMerma').classList.contains('show'));
    await c.responder(2, {success: true, data: {...merma(99), stock_restante: 7}}, 201);
    c.enviar();
    assert.equal(c.requests.length, 4);
    assert.equal(c.requests[3].url.pathname, '/api/v1/productos/mermas/historial/');
    assert.equal(c.el('modalNuevaMerma').classList.contains('show'), false);
    assert.equal(c.el('avisoResultadoMerma'), null); assert.equal(c.avisos.length, 1);
});

test('rechazo de servidor conserva el formulario y actualiza el stock disponible', async t => {
    const c = await pantalla(t);
    await c.responder(0, paginaDatos(merma));
    await c.completar();
    c.enviar();
    await c.responder(2, {mensaje: 'Stock insuficiente.', errores: {stock_disponible: 2}}, 400);
    assert.ok(c.el('modalNuevaMerma').classList.contains('show'));
    assert.equal(c.el('mermaCantidad').value, '3');
    assert.equal(c.el('btnGuardarMerma').disabled, true);
    assert.match(c.el('mermaStockDisponible').textContent, /2 unidades/);
    assert.match(c.el('mermaProducto').selectedOptions[0].textContent, /Disponible: 2/);
    c.campo('mermaCantidad', '2');
    assert.equal(c.el('btnGuardarMerma').disabled, false);
});

test('cambiar bodega invalida el producto y descarta la respuesta anterior', async t => {
    const c = await pantalla(t);
    await c.responder(0, paginaDatos(merma)); c.abrir();
    assert.equal(c.requests[1].url.searchParams.get('bodega'), '1');
    c.campo('mermaBodega', '2', 'change');
    assert.equal(c.requests[2].url.searchParams.get('bodega'), '2');
    await c.responder(1, paginaDatos(producto));
    assert.equal(c.el('mermaProducto').disabled, true);
    await c.responder(2, {count:1,results:[{...producto(1), bodega_id:2, bodega:'Bodega Norte', stock_disponible:4}]});
    c.campo('mermaProducto','1','change'); c.campo('mermaCantidad','3'); c.campo('mermaObservacion','Envase roto.');
    assert.match(c.el('mermaStockDisponible').textContent, /Bodega Norte: 4/);
    c.enviar();
    assert.equal(JSON.parse(c.requests[3].options.body).bodega_id, 2);
});

test('no utiliza catálogo con existencias de otra bodega', async t => {
    const c = await pantalla(t); await c.responder(0, paginaDatos(merma)); c.abrir();
    await c.responder(1, {count:1,results:[{...producto(1), bodega_id:2}]});
    assert.equal(c.el('mermaProducto').disabled, true);
    assert.equal(c.el('btnGuardarMerma').disabled, true);
    assert.match(c.el('errorNuevaMerma').textContent, /otra bodega/);
});

test('historial de bodega selecciona el contexto del formulario y conserva inactivas en la consulta', async t => {
    const c = await pantalla(t); await c.responder(0, paginaDatos(merma));
    c.campo('bodegaHistorialMermas','2','change');
    assert.equal(c.requests[1].url.searchParams.get('bodega'),'2');
    c.abrir(); assert.equal(c.el('mermaBodega').value,'2');
    assert.equal(c.requests[2].url.searchParams.get('bodega'),'2');
    c.modelos.get(c.el('modalNuevaMerma')).hide();
    c.campo('bodegaHistorialMermas','3','change');
    assert.match(c.el('bodegaHistorialMermas').selectedOptions[0].textContent,/inactiva/);
    assert.equal(c.requests[3].url.searchParams.get('bodega'),'3');
    c.abrir(); assert.equal(c.el('mermaBodega').value,'1');
});

test('carga fallida o sin bodegas activas no permite registrar mermas', async t => {
    const c = await pantalla(t, false);
    assert.equal(c.el('btnNuevaMerma').disabled,true);
    await c.responder(1, {mensaje:'No disponible'}, 503);
    assert.equal(c.el('reintentarBodegasMermas').hidden,false);
    c.abrir(); assert.equal(c.el('modalNuevaMerma').classList.contains('show'),false);
    c.el('reintentarBodegasMermas').click();
    const vacias = require('./bodegas-fixture.cjs')(); vacias.data.bodegas=[];
    await c.responder(2,vacias);
    assert.equal(c.el('btnNuevaMerma').disabled,true);
    assert.match(c.el('estadoBodegasMermas').textContent,/Crea o reactiva/);
});

