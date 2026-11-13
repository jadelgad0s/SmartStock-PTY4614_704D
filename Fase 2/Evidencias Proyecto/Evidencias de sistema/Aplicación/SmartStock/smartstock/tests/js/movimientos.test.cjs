const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const root = path.resolve(__dirname, '../..');
const html = readFileSync(path.join(root, 'templates/movimientos.html'), 'utf8').replace(/{%[\s\S]*?%}/g, '');
const codigo = readFileSync(path.join(root, 'static/js/movimientos.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
const movimiento = (id = 1) => ({
    id, movimiento_id: id, fecha: '27/10/2026 12:30', tipo: 'ENTRADA',
    producto: 'Bebida Cherry', sku: 'BEBIDA', cantidad: 24, usuario: 'Operador Prueba',
    bodega: 'Bodega Central', documento_referencia: 'Guía 123',
});
const datos = (count = 55, pagina = 1) => ({count, results: Array.from({
    length: Math.max(0, Math.min(25, count - (pagina - 1) * 25)),
}, (_, i) => movimiento(i + 1 + (pagina - 1) * 25))});
const producto = {id: 99, sku: 'FUERA-PAGINA', nombre: 'Bebida Cherry', bodega_id: 1, bodega: 'Bodega Central', stock_disponible: 10};

async function pantalla(t, opcionesIniciales = true) {
    const dom = new JSDOM(html, {url: 'http://localhost/movimientos/', runScripts: 'outside-only', pretendToBeVisual: true});
    t.after(() => dom.window.close());
    const w = dom.window;
    const requests = [];
    const timers = new Map();
    let timer = 0;
    w.localStorage.setItem('access_token', 'test');
    w.localStorage.setItem('usuario', JSON.stringify({rol_nombre: 'Administrador'}));
    w.matchMedia = () => ({matches: false});
    w.HTMLElement.prototype.scrollIntoView = () => {};
    const modales = new Map();
    w.bootstrap = {Modal: {getOrCreateInstance(elemento) {
        if (!modales.has(elemento)) modales.set(elemento, {
            show() {
                elemento.classList.add('show');
                elemento.dispatchEvent(new w.Event('shown.bs.modal'));
            },
            hide() {
                const evento = new w.Event('hide.bs.modal', {cancelable: true});
                if (!elemento.dispatchEvent(evento)) return;
                elemento.classList.remove('show');
                elemento.dispatchEvent(new w.Event('hidden.bs.modal'));
            },
        });
        return modales.get(elemento);
    }}};
    w.setTimeout = fn => { timers.set(++timer, fn); return timer; };
    w.clearTimeout = id => timers.delete(id);
    w.fetch = (url, options) => opcionesIniciales && new URL(url, w.location.href).pathname === '/api/v1/bodegas/opciones/' ?
        Promise.resolve({ok: true, status: 200, json: async () => require('./bodegas-fixture.cjs')()}) : new Promise((resolve, reject) => requests.push({
        url: new URL(url, w.location.href), options, resolve, reject,
    }));
    const avisos = []; w.addEventListener('smartstock:notifications-changed', () => avisos.push(true));
    w.eval(codigo);
    await tick();
    const el = id => w.document.getElementById(id);
    const responder = async (index, data, status = 200) => {
        requests[index].resolve({ok: status >= 200 && status < 300, status, json: async () => data});
        await tick();
    };
    const campo = (id, valor, evento = 'input') => {
        el(id).value = valor;
        el(id).dispatchEvent(new w.Event(evento));
    };
    const enviar = id => el(id).dispatchEvent(new w.Event('submit', {cancelable: true}));
    const debounce = async () => {
        const pendientes = [...timers.values()];
        timers.clear();
        pendientes.forEach(fn => fn());
        await tick();
    };
    const escanear = codigo => w.dispatchEvent(new w.CustomEvent('smartstock:barcode-scanned', {detail: {codigo}}));
    const abrirProducto = async () => {
        escanear('COD/99');
        await responder(requests.length - 1, {data: producto});
    };
    return {w, el, avisos, campo, enviar, responder, requests, debounce, escanear, abrirProducto, modales};
}

test('historial paginado conserva búsqueda, tipo y fechas al navegar', async t => {
    const c = await pantalla(t);
    await c.responder(0, datos());
    c.campo('buscarMovimientos', 'Bebida');
    c.campo('tipoMovimientos', 'ENTRADA', 'change');
    await c.debounce();
    assert.equal(c.requests.length, 2);
    await c.responder(1, datos());
    c.campo('desdeMovimientos', '2026-10-01', 'change');
    await c.responder(2, datos());
    c.campo('hastaMovimientos', '2026-10-27', 'change');
    await c.responder(3, datos());
    c.el('paginacionMovimientos').querySelector('button[data-page="2"]').click();
    const params = c.requests[4].url.searchParams;
    for (const [key, value] of Object.entries({page: '2', search: 'Bebida', tipo: 'ENTRADA', desde: '2026-10-01', hasta: '2026-10-27'})) assert.equal(params.get(key), value);
    await c.responder(4, datos(55, 2));
    assert.match(c.el('resumenMovimientos').textContent, /26–50 de 55/);
});

test('buscar invalida de inmediato una respuesta anterior y vaciar reinicia el historial', async t => {
    const c = await pantalla(t);
    c.campo('buscarMovimientos', 'Bebida');
    await c.responder(0, datos());
    assert.equal(c.el('listaMovimientos').querySelectorAll('.ss-mov-row').length, 0);
    await c.debounce();
    await c.responder(1, datos());
    c.el('paginacionMovimientos').querySelector('button[data-page="3"]').click();
    await c.responder(2, datos(55, 3));
    c.campo('buscarMovimientos', '');
    await c.debounce();
    assert.equal(c.requests[3].url.searchParams.get('page'), '1');
    assert.equal(c.requests[3].url.searchParams.has('search'), false);
});

test('rango de fechas inválido no envía peticiones y limpiar restaura la consulta', async t => {
    const c = await pantalla(t);
    await c.responder(0, datos());
    c.el('desdeMovimientos').value = '2026-10-28';
    c.campo('hastaMovimientos', '2026-10-27', 'change');
    assert.equal(c.requests.length, 1);
    assert.match(c.el('errorHistorialMovimientos').textContent, /fecha inicial/);
    assert.equal(c.el('listaMovimientos').getAttribute('aria-busy'), 'false');
    c.el('limpiarFiltrosMovimientos').click();
    assert.equal(c.requests.length, 2);
    assert.equal(c.requests[1].url.searchParams.has('desde'), false);
});

test('página eliminada recupera last y termina si el servidor sigue respondiendo 404', async t => {
    const c = await pantalla(t);
    await c.responder(0, datos());
    c.el('paginacionMovimientos').querySelector('button[data-page="3"]').click();
    await c.responder(1, {detail: 'Página inválida'}, 404);
    assert.equal(c.requests[2].url.searchParams.get('page'), 'last');
    await c.responder(2, {detail: 'No disponible'}, 404);
    assert.equal(c.requests.length, 3);
    assert.equal(c.el('listaMovimientos').getAttribute('aria-busy'), 'false');
});

test('los nombres del historial se insertan como texto y el detalle muestra datos del servidor', async t => {
    const c = await pantalla(t);
    const mov = {...movimiento(), producto: '<img src=x onerror=alert(1)>'};
    await c.responder(0, {count: 1, results: [mov]});
    assert.equal(c.el('listaMovimientos').querySelector('img'), null);
    c.el('listaMovimientos').querySelector('button[data-detalle]').click();
    assert.equal(c.requests[1].url.pathname, '/api/v1/productos/movimientos/1/');
    await c.responder(1, {data: mov});
    assert.equal(c.el('detalleMovProducto').textContent, mov.producto);
    assert.equal(c.el('detalleMovReferencia').textContent, 'Guía 123');
});

test('escaneo resuelve códigos exactos y bloquea lecturas repetidas pendientes', async t => {
    const c = await pantalla(t);
    await c.responder(0, datos());
    c.escanear('COD/99');
    c.escanear('COD/99');
    assert.equal(c.requests.length, 2);
    assert.equal(c.requests[1].url.pathname, '/api/v1/productos/resolver-movimiento/');
    assert.equal(c.requests[1].url.searchParams.get('codigo'), 'COD/99');
    await c.responder(1, {data: producto});
    assert.equal(c.el('movProductoId').value, '99');
    assert.match(c.el('movStockDisponible').textContent, /10 unidades/);
    assert.equal(c.el('modalAccionMovimiento').classList.contains('show'), true);
    assert.equal(c.w.document.activeElement, c.el('movTipo'));
});

test('registro manual abre un solo modal de acción tras resolver el producto', async t => {
    const c = await pantalla(t);
    await c.responder(0, datos());
    c.el('btn-movimiento-manual').click();
    c.campo('inputSkuManual', 'FUERA-PAGINA');
    c.enviar('formIngresoManual');
    c.enviar('formIngresoManual');
    assert.equal(c.requests.length, 2);
    await c.responder(1, {data: producto});
    assert.equal(c.el('modalIngresoManual').classList.contains('show'), false);
    assert.equal(c.el('modalAccionMovimiento').classList.contains('show'), true);
    assert.equal(c.el('movSkuProducto').textContent, 'SKU: FUERA-PAGINA');
});

test('salida insuficiente o fraccionaria no se confirma y el resumen muestra el stock estimado', async t => {
    const c = await pantalla(t);
    await c.responder(0, datos());
    await c.abrirProducto();
    c.campo('movTipo', 'SALIDA');
    c.campo('movCantidad', '11');
    assert.equal(c.el('confirmarMovimiento').disabled, true);
    c.enviar('formRegistrarMovimiento');
    assert.equal(c.requests.length, 2);
    c.campo('movCantidad', '1.5');
    assert.equal(c.el('confirmarMovimiento').disabled, true);
    c.campo('movCantidad', '3');
    assert.equal(c.el('confirmarMovimiento').disabled, false);
    assert.match(c.el('movResumenConfirmacion').textContent, /Bebida Cherry/);
    assert.match(c.el('movResumenConfirmacion').textContent, /Bodega Central: 7 unidades/);
});

test('la confirmación conserva el nodo de texto al salir del campo Cantidad', async t => {
    const c = await pantalla(t);
    await c.responder(0, datos());
    await c.abrirProducto();
    c.campo('movCantidad', '24');
    const boton = c.el('confirmarMovimiento');
    const etiqueta = boton.firstChild;
    c.campo('movCantidad', '24', 'change');
    assert.ok(boton.firstChild === etiqueta, 'El clic necesita el mismo nodo de texto al salir del campo.');
});

test('doble envío registra una sola petición y recarga el historial real tras confirmar', async t => {
    const c = await pantalla(t);
    await c.responder(0, datos());
    await c.abrirProducto();
    c.campo('movTipo', 'SALIDA');
    c.campo('movCantidad', '3');
    c.enviar('formRegistrarMovimiento');
    c.enviar('formRegistrarMovimiento');
    assert.equal(c.requests.length, 3);
    assert.equal(c.requests[2].options.method, 'POST');
    assert.equal(JSON.parse(c.requests[2].options.body).cantidad, 3);
    assert.equal(c.el('confirmarMovimiento').disabled, true);
    c.modales.get(c.el('modalAccionMovimiento')).hide();
    assert.equal(c.el('modalAccionMovimiento').classList.contains('show'), true);
    await c.responder(2, {data: {...movimiento(), tipo: 'SALIDA', cantidad: 3, stock_restante: 7}}, 201);
    c.enviar('formRegistrarMovimiento');
    assert.equal(c.requests.length, 4);
    assert.equal(c.el('modalAccionMovimiento').classList.contains('show'), false);
    assert.equal(c.requests[3].url.pathname, '/api/v1/productos/movimientos/');
    assert.equal(c.el('estadoRegistroMovimiento'), null); assert.equal(c.avisos.length, 1);
    await c.responder(3, datos());
});

test('se puede volver a escanear cuando el formulario termina de cerrarse', async t => {
    const c = await pantalla(t);
    await c.responder(0, datos());
    await c.abrirProducto();
    const modal = c.el('modalAccionMovimiento');
    c.modales.get(modal).hide = () => modal.classList.remove('show');
    c.enviar('formRegistrarMovimiento');
    await c.responder(2, {data: {...movimiento(), stock_restante: 11}}, 201);
    assert.equal(c.el('inputEscaner').disabled, true);
    c.escanear('FUERA-PAGINA');
    assert.equal(c.requests.length, 4);

    modal.dispatchEvent(new c.w.Event('hidden.bs.modal'));
    assert.equal(c.el('inputEscaner').disabled, false);
    c.escanear('FUERA-PAGINA');
    assert.equal(c.requests[4].url.pathname, '/api/v1/productos/resolver-movimiento/');
});

test('filtros móviles se despliegan y muestran cuántos están activos', async t => {
    const c = await pantalla(t);
    await c.responder(0, datos());
    c.el('mostrarFiltrosMovimientos').click();
    assert.equal(c.el('mostrarFiltrosMovimientos').getAttribute('aria-expanded'), 'true');
    assert.ok(c.el('controlesFiltrosMovimientos').classList.contains('is-open'));
    c.campo('tipoMovimientos', 'SALIDA', 'change');
    assert.equal(c.el('mostrarFiltrosMovimientos').textContent, 'Filtros (1)');
    c.el('mostrarFiltrosMovimientos').click();
    assert.equal(c.el('mostrarFiltrosMovimientos').getAttribute('aria-expanded'), 'false');
    c.el('limpiarFiltrosMovimientos').click();
    assert.equal(c.el('mostrarFiltrosMovimientos').textContent, 'Filtros');
});

test('un stock cambiado en servidor mantiene el formulario y actualiza la validación', async t => {
    const c = await pantalla(t);
    await c.responder(0, datos());
    await c.abrirProducto();
    c.campo('movTipo', 'SALIDA');
    c.campo('movCantidad', '3');
    c.enviar('formRegistrarMovimiento');
    await c.responder(2, {mensaje: 'Stock insuficiente. Disponible: 2 unidades.', errores: {stock_disponible: 2}}, 409);
    assert.equal(c.el('modalAccionMovimiento').classList.contains('show'), true);
    assert.equal(c.el('confirmarMovimiento').disabled, true);
    assert.equal(c.el('movCantidad').disabled, false);
    assert.match(c.el('movErrorRegistro').textContent, /Disponible: 2/);
    c.campo('movCantidad', '2');
    assert.equal(c.el('confirmarMovimiento').disabled, false);
});

test('selección de bodega se consulta y queda fijada en el movimiento a confirmar', async t => {
    const c = await pantalla(t);
    await c.responder(0, datos());
    c.campo('bodegaMovimiento', '2', 'change');
    await c.responder(1, {count: 0, results: []});
    c.escanear('MULTI-1');
    assert.equal(c.requests[2].url.searchParams.get('bodega'), '2');
    assert.equal(c.el('bodegaMovimiento').disabled, true);
    await c.responder(2, {data: {...producto, bodega_id: 2, bodega: 'Bodega Norte', stock_disponible: 4}});
    assert.match(c.el('movStockDisponible').textContent, /Bodega Norte: 4/);
    assert.equal(c.el('bodegaMovimiento').disabled, true);
    c.campo('movTipo', 'SALIDA'); c.campo('movCantidad', '3');
    c.enviar('formRegistrarMovimiento');
    assert.equal(JSON.parse(c.requests[3].options.body).bodega_id, 2);
    c.modales.get(c.el('modalAccionMovimiento')).hide();
    assert.equal(c.el('bodegaMovimiento').disabled, true);
    await c.responder(3, {mensaje:'La bodega está desactivada.'}, 400);
    assert.ok(c.el('modalAccionMovimiento').classList.contains('show'));
    assert.match(c.el('movErrorRegistro').textContent, /desactivada/);
    c.modales.get(c.el('modalAccionMovimiento')).hide();
    assert.equal(c.el('bodegaMovimiento').disabled, false);
});

test('no abre confirmación con stock de otra bodega', async t => {
    const c = await pantalla(t);
    await c.responder(0, datos()); c.escanear('MULTI-1');
    await c.responder(1, {data: {...producto, bodega_id:2}});
    assert.equal(c.el('modalAccionMovimiento').classList.contains('show'), false);
    assert.match(c.el('errorEscaner').textContent, /bodega cambió/);
});

test('sin opciones o sin bodegas activas bloquea operaciones y permite reintentar', async t => {
    const c = await pantalla(t, false);
    assert.equal(c.requests[1].url.pathname, '/api/v1/bodegas/opciones/');
    assert.equal(c.el('btn-movimiento-manual').disabled, true);
    await c.responder(1, {mensaje:'Servicio temporalmente no disponible'}, 503);
    assert.equal(c.el('reintentarBodegasMovimiento').hidden, false);
    c.el('reintentarBodegasMovimiento').click();
    const vacias = require('./bodegas-fixture.cjs')(); vacias.data.bodegas = []; vacias.data.bodega_predeterminada = null;
    await c.responder(2, vacias);
    assert.equal(c.el('bodegaMovimiento').disabled, true);
    assert.equal(c.el('btn-movimiento-manual').disabled, true);
    assert.match(c.el('estadoBodegasMovimiento').textContent, /Crea o reactiva/);
});

test('cambiar la bodega preseleccionada actualiza el historial y el escáner', async t => {
    const c = await pantalla(t);
    await c.responder(0, datos());
    c.campo('tipoMovimientos', 'ENTRADA', 'change');
    await c.responder(1, datos());
    c.el('paginacionMovimientos').querySelector('button[data-page="2"]').click();

    c.campo('bodegaMovimiento', '2', 'change');
    assert.equal(c.el('bodegaHistorialMovimientos').value, '2');
    const params = c.requests[3].url.searchParams;
    assert.equal(params.get('bodega'), '2');
    assert.equal(params.get('page'), '1');
    assert.equal(params.get('tipo'), 'ENTRADA');
    await c.responder(3, {count: 1, results: [{...movimiento(), bodega: 'Bodega Norte'}]});
    await c.responder(2, datos(55, 2));
    assert.match(c.el('listaMovimientos').textContent, /Bodega Norte/);
    assert.doesNotMatch(c.el('listaMovimientos').textContent, /Bodega Central/);

    c.campo('bodegaHistorialMovimientos', '', 'change');
    assert.equal(c.requests[4].url.searchParams.has('bodega'), false);
    assert.equal(c.el('bodegaMovimiento').value, '2');
    c.escanear('COD/99');
    assert.equal(c.requests[5].url.searchParams.get('bodega'), '2');
});

test('historial filtra también bodegas inactivas y muestra su nombre', async t => {
    const c = await pantalla(t);
    await c.responder(0, datos()); c.campo('bodegaHistorialMovimientos', '3', 'change');
    assert.equal(c.requests[1].url.searchParams.get('bodega'), '3');
    assert.match(c.el('bodegaHistorialMovimientos').selectedOptions[0].textContent, /inactiva/);
    await c.responder(1, {count:1,results:[{...movimiento(), bodega:'Antigua'}]});
    assert.match(c.el('listaMovimientos').textContent, /Antigua/);
});

test('el formulario distingue bodega de recepción y salida y conserva la preselección', async t => {
    const c=await pantalla(t);await c.responder(0,datos());await c.abrirProducto();
    assert.equal(c.el('movBodega').value,'1');assert.equal(c.el('movBodega').disabled,false);
    assert.equal(c.el('movEtiquetaBodega').textContent,'Bodega de recepción');assert.match(c.el('movAyudaBodega').textContent,/ingresarán/);
    assert.equal(c.el('movBodega').options.length,2);assert.doesNotMatch(c.el('movBodega').textContent,/Antigua/);
    c.campo('movTipo','SALIDA','change');assert.equal(c.el('movEtiquetaBodega').textContent,'Bodega de salida');assert.match(c.el('movAyudaBodega').textContent,/descontarán/);
    c.campo('movTipo','ENTRADA','change');assert.equal(c.el('movEtiquetaBodega').textContent,'Bodega de recepción');assert.equal(c.requests.length,2);
});

test('cambiar bodega conserva los datos y consulta existencias antes de permitir confirmar', async t => {
    const c=await pantalla(t);await c.responder(0,datos());await c.abrirProducto();c.campo('movCantidad','3');c.campo('movObservacion','Guía de recepción');c.campo('movBodega','2','change');
    assert.equal(c.requests[2].url.searchParams.get('bodega'),'2');assert.equal(c.requests[2].url.searchParams.get('codigo'),producto.sku);assert.equal(c.requests[2].options.cache,'no-store');
    assert.equal(c.el('confirmarMovimiento').disabled,true);assert.doesNotMatch(c.el('movStockDisponible').textContent,/10 unidades/);c.enviar('formRegistrarMovimiento');assert.equal(c.requests.length,3);
    c.campo('movTipo','SALIDA','change');assert.equal(c.el('confirmarMovimiento').disabled,true);
    await c.responder(2,{data:{...producto,bodega_id:2,bodega:'Bodega Norte',stock_disponible:4}});
    assert.equal(c.el('movCantidad').value,'3');assert.equal(c.el('movObservacion').value,'Guía de recepción');assert.equal(c.el('movTipo').value,'SALIDA');assert.equal(c.el('movBodega').value,'2');
    assert.match(c.el('movStockDisponible').textContent,/Bodega Norte: 4/);assert.match(c.el('movResumenConfirmacion').textContent,/Bodega Norte: 1 unidades/);assert.equal(c.el('confirmarMovimiento').disabled,false);
    c.enviar('formRegistrarMovimiento');const p=JSON.parse(c.requests[3].options.body);assert.equal(p.bodega_id,2);assert.equal(p.producto_id,99);assert.equal(p.tipo_movimiento,'SALIDA');assert.equal(p.cantidad,3);assert.equal(p.observacion,'Guía de recepción');
    assert.equal(c.el('movBodega').disabled,true);
});

test('una bodega sin existencias permite recibir y bloquea retirar unidades', async t => {
    const c=await pantalla(t);await c.responder(0,datos());await c.abrirProducto();c.campo('movBodega','2','change');await c.responder(2,{data:{...producto,bodega_id:2,bodega:'Bodega Norte',stock_disponible:0}});
    assert.equal(c.el('confirmarMovimiento').disabled,false);assert.match(c.el('movResumenConfirmacion').textContent,/Bodega Norte: 1 unidades/);
    c.campo('movTipo','SALIDA','change');assert.equal(c.el('confirmarMovimiento').disabled,true);assert.match(c.el('movResumenConfirmacion').textContent,/Stock insuficiente/);c.enviar('formRegistrarMovimiento');assert.equal(c.requests.length,3);
});

test('un error de stock exige reintentar y no usa las existencias de la bodega anterior', async t => {
    const c=await pantalla(t);await c.responder(0,datos());await c.abrirProducto();c.campo('movCantidad','7');c.campo('movBodega','2','change');await c.responder(2,{mensaje:'No disponible'},503);
    assert.equal(c.el('confirmarMovimiento').disabled,true);assert.equal(c.el('reintentarStockMovimiento').hidden,false);assert.match(c.el('movErrorRegistro').textContent,/No disponible/);
    c.campo('movCantidad','2');c.enviar('formRegistrarMovimiento');assert.equal(c.requests.length,3);assert.equal(c.el('confirmarMovimiento').disabled,true);
    c.el('reintentarStockMovimiento').click();c.el('reintentarStockMovimiento').click();assert.equal(c.requests.length,4);await c.responder(3,{data:{...producto,bodega_id:2,bodega:'Bodega Norte',stock_disponible:4}});
    assert.equal(c.el('confirmarMovimiento').disabled,false);assert.equal(c.el('reintentarStockMovimiento').hidden,true);assert.equal(c.el('movCantidad').value,'2');
});

test('un cambio rápido entre bodegas descarta respuestas anteriores aunque lleguen al final', async t => {
    const c=await pantalla(t);await c.responder(0,datos());await c.abrirProducto();c.campo('movBodega','2','change');c.campo('movBodega','1','change');
    await c.responder(3,{data:{...producto,stock_disponible:8}});assert.match(c.el('movStockDisponible').textContent,/Bodega Central: 8/);
    await c.responder(2,{data:{...producto,bodega_id:2,bodega:'Bodega Norte',stock_disponible:100}});assert.match(c.el('movStockDisponible').textContent,/Bodega Central: 8/);assert.doesNotMatch(c.el('movStockDisponible').textContent,/100/);
    c.enviar('formRegistrarMovimiento');assert.equal(JSON.parse(c.requests[4].options.body).bodega_id,1);
});

test('no se confirma si la respuesta tiene otra bodega, otro producto o stock inválido', async t => {
    for(const extra of [{bodega_id:1},{id:100},{stock_disponible:'4'},{bodega_id:null}]){
        const c=await pantalla(t);await c.responder(0,datos());await c.abrirProducto();c.campo('movBodega','2','change');await c.responder(2,{data:{...producto,bodega_id:2,bodega:'Norte',...extra}});
        c.enviar('formRegistrarMovimiento');assert.equal(c.requests.length,3);assert.equal(c.el('confirmarMovimiento').disabled,true);assert.equal(c.el('reintentarStockMovimiento').hidden,false);
    }
});

test('cerrar durante una consulta de bodega descarta el resultado y conserva la nueva preselección', async t => {
    const c=await pantalla(t);await c.responder(0,datos());await c.abrirProducto();c.campo('movBodega','2','change');c.modales.get(c.el('modalAccionMovimiento')).hide();
    assert.equal(c.el('bodegaMovimiento').value,'2');assert.equal(c.el('bodegaMovimiento').disabled,false);await c.responder(2,{data:{...producto,bodega_id:2,bodega:'Norte',stock_disponible:9}});c.enviar('formRegistrarMovimiento');assert.equal(c.requests.length,3);
    c.escanear('OTRO');assert.equal(c.requests[3].url.searchParams.get('bodega'),'2');await c.responder(3,{data:{...producto,bodega_id:2,bodega:'Norte',stock_disponible:9}});assert.equal(c.el('movBodega').value,'2');assert.equal(c.el('movCantidad').value,'1');assert.equal(c.el('movObservacion').value,'');
});

test('al abrir otro producto no se aplica la respuesta de stock del formulario cerrado', async t => {
    const c=await pantalla(t);await c.responder(0,datos());await c.abrirProducto();c.campo('movBodega','2','change');c.modales.get(c.el('modalAccionMovimiento')).hide();
    c.escanear('NUEVO');await c.responder(3,{data:{...producto,id:100,nombre:'Otro producto',bodega_id:2,bodega:'Norte',stock_disponible:7}});await c.responder(2,{data:{...producto,bodega_id:2,bodega:'Norte',stock_disponible:100}});
    assert.equal(c.el('movProductoId').value,'100');assert.equal(c.el('movNombreProducto').textContent,'Otro producto');assert.match(c.el('movStockDisponible').textContent,/7 unidades/);c.enviar('formRegistrarMovimiento');assert.equal(JSON.parse(c.requests[4].options.body).producto_id,100);
});

test('vaciar la bodega bloquea la confirmación y no reutiliza la selección anterior', async t => {
    const c=await pantalla(t);await c.responder(0,datos());await c.abrirProducto();c.campo('movBodega','','change');c.enviar('formRegistrarMovimiento');
    assert.equal(c.el('confirmarMovimiento').disabled,true);assert.match(c.el('movResumenConfirmacion').textContent,/Selecciona una bodega activa/);assert.equal(c.requests.length,2);
});

