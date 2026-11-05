// Ejecuta el JavaScript real sobre la plantilla del catálogo, sin servidor ni BD.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');

const root = path.resolve(__dirname, '../..');
const html = readFileSync(path.join(root, 'templates/productos.html'), 'utf8')
    .replace(/{%[\s\S]*?%}/g, '');
const codigo = readFileSync(path.join(root, 'static/js/productos.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

function producto(id) {
    return {
        id, sku: `CAT-${id}`, nombre: `Producto ${id}`, activo: true,
        precio_referencia: '1000.00', stock_actual: 3, stock_minimo: 2, estado_stock: 'suficiente',
    };
}

function datos(count = 55, pagina = 1) {
    const inicio = (pagina - 1) * 25;
    return {
        count,
        results: Array.from({length: Math.max(0, Math.min(25, count - inicio))},
            (_, i) => producto(inicio + i + 1)),
    };
}

async function catalogo(t, query = '', config = {}) {
    const dom = new JSDOM(html, {
        url: `http://localhost/productos/${query}`,
        runScripts: 'outside-only', pretendToBeVisual: true,
    });
    t.after(() => dom.window.close());
    const w = dom.window;
    const requests = [];
    const timers = new Map();
    let timerId = 0;
    w.localStorage.setItem('access_token', 'token-de-prueba');
    w.localStorage.setItem('usuario', JSON.stringify({rol_nombre: 'Administrador'}));
    w.HTMLElement.prototype.scrollIntoView = () => {};
    w.matchMedia = () => ({matches: true});
    w.scrollTo = () => {};
    w.console.error = () => {};
    w.smartstockClearSession = () => { w.localStorage.removeItem('access_token'); w.localStorage.removeItem('refresh_token'); };
    w.localStorage.setItem('refresh_token', 'refresh');
    w.alert = w.confirm = () => { throw new Error('No usar diálogos nativos'); };
    const modelos = new Map();
    w.bootstrap = {Modal: {getOrCreateInstance(elemento) {
        if (!modelos.has(elemento)) modelos.set(elemento, {
            show() { elemento.dispatchEvent(new w.Event('show.bs.modal')); elemento.classList.add('show'); elemento.dispatchEvent(new w.Event('shown.bs.modal')); },
            hide() { if (!elemento.dispatchEvent(new w.Event('hide.bs.modal', {cancelable: true}))) return; elemento.classList.remove('show'); elemento.dispatchEvent(new w.Event('hidden.bs.modal')); },
        }); return modelos.get(elemento);
    }}};
    let lector;
    w.Html5QrcodeSupportedFormats = {EAN_13: 1, EAN_8: 2, UPC_A: 3, UPC_E: 4, CODE_128: 5, CODE_39: 6, QR_CODE: 7};
    w.Html5Qrcode = class { constructor() { lector = this; } async start(cam, opts, callback) { this.scan = callback; } async stop() { this.detener = true; } clear() {} };

    w.setTimeout = fn => { timers.set(++timerId, fn); return timerId; };
    w.clearTimeout = id => timers.delete(id);
    w.fetch = (url, options) => {
        if (String(url).includes('/opciones/') && !config.opcionesManual) return Promise.resolve({ok: true, status: 200, json: async () => ({data: {bodegas: [{id: 1, nombre: 'Bodega Central'}, {id: 2, nombre: 'Anexo'}], bodega_predeterminada: 1, permisos: config.permisos || {crear: true, editar: true, configurar_minimo: true, desactivar: true, reactivar: true, eliminar_definitivamente: true, usuarios: true, auditoria: true, configuracion: false}}})});
        return new Promise((resolve, reject) => {
        requests.push({url: new URL(url, w.location.href), options, resolve, reject});
    });
    };
    const avisos = []; w.addEventListener('smartstock:notifications-changed', () => avisos.push(true));
    w.eval(codigo);
    if (config.scanner) w.eval(readFileSync(path.join(root, 'static/js/escaneo_camara.js'), 'utf8'));
    await tick();

    const el = id => w.document.getElementById(id);
    const responder = async (index, data = datos(), status = 200) => {
        requests[index].resolve({ok: status >= 200 && status < 300, status,
            json: async () => data});
        await tick();
    };
    const buscar = texto => {
        el('buscadorProductos').value = texto;
        el('buscadorProductos').dispatchEvent(new w.Event('input'));
    };
    const ordenar = orden => {
        el('ordenarProductos').value = orden;
        el('ordenarProductos').dispatchEvent(new w.Event('change'));
    };
    const debounce = async () => {
        const pendientes = [...timers.values()];
        timers.clear();
        pendientes.forEach(fn => fn());
        await tick();
    };
    const paginar = (numero, superior = false) => {
        const nav = el(superior ? 'paginacionProductosSuperior' : 'paginacionProductos');
        const boton = nav.querySelector(`button[data-page="${numero}"]:not(:disabled)`);
        assert.ok(boton, `Existe el botón de página ${numero}`);
        boton.focus();
        boton.click();
    };
    const paginasActuales = () => ['paginacionProductosSuperior', 'paginacionProductos']
        .map(id => el(id).querySelector('[aria-current="page"]')?.textContent);
    const campo = (id, value, type = 'input') => { el(id).value = value; el(id).dispatchEvent(new w.Event(type, {bubbles: true})); };
    const enviar = id => el(id).dispatchEvent(new w.Event('submit', {cancelable: true}));
    const completarNuevo = () => { el('btnNuevoProducto').click(); campo('inputSku', 'fer-nuevo'); campo('inputNombre', 'Producto nuevo'); campo('inputPrecio', '1234.50'); campo('inputDescripcion', 'Descripción nueva'); };
    return {w, el, avisos, requests, modelos, campo, enviar, completarNuevo, responder, buscar, ordenar, debounce, paginar, paginasActuales, get lector() { return lector; }};
}

const codigoConsulta = '3017620422003';
const resultadoExterno = (extra = {}) => ({
    success: true, mensaje: 'Encontramos información. Revisa los datos antes de guardar.',
    data: {estado: 'externo', codigo: codigoConsulta, gtin: codigoConsulta, ficha_externa_id: 12,
        sugerencia: {nombre: 'Crema de avellanas 350 g', descripcion: 'Marca: Ejemplo\nContenido: 350 g', marca: 'Ejemplo', presentacion: '350 g', imagen_url: 'https://images.openfoodfacts.org/images/products/301/762/042/2003/front_es.200.jpg'},
        fuente: {nombre: 'Open Food Facts', url: 'https://world.openfoodfacts.org/product/03017620422003', licencia: 'ODbL'}, ...extra},
});
function consultarCodigo(c, codigo = codigoConsulta) { c.campo('consultaCodigoProducto', codigo); c.el('buscarDatosProducto').click(); }

test('buscar desde nuevo producto completa vacíos y asocia código, sin guardar ni cambiar SKU o precio', async t => {
    const c = await catalogo(t); await c.responder(0); c.el('btnNuevoProducto').click();
    c.campo('inputSku', 'MI-SKU'); c.campo('inputPrecio', '2300'); consultarCodigo(c);
    assert.equal(c.requests[1].url.pathname, '/api/v1/productos/consultar-codigo/');
    assert.equal(c.requests[1].url.searchParams.get('codigo'), codigoConsulta);
    assert.equal(c.el('guardarNuevoProducto').disabled, true);
    c.enviar('formCrearProducto'); assert.equal(c.requests.length, 2);
    await c.responder(1, resultadoExterno());
    assert.equal(c.el('inputNombre').value, 'Crema de avellanas 350 g');
    assert.equal(c.el('inputDescripcion').value, 'Marca: Ejemplo\nContenido: 350 g');
    assert.equal(c.el('inputSku').value, 'MI-SKU'); assert.equal(c.el('inputPrecio').value, '2300');
    assert.equal(c.el('listaCodigosNuevo').querySelector('input').value, codigoConsulta);
    assert.match(c.el('resultadoConsultaCodigo').textContent, /Open Food Facts.*ODbL/);
    assert.equal(c.el('resultadoConsultaCodigo').querySelector('img').referrerPolicy, 'no-referrer');
    assert.equal(c.el('guardarNuevoProducto').disabled, false); assert.equal(c.requests.length, 2);
    c.enviar('formCrearProducto');
    const payload = JSON.parse(c.requests[2].options.body);
    assert.equal(payload.ficha_externa_id, 12); assert.equal(payload.precio_referencia, '2300');
    assert.deepEqual(payload.codigos_barra, [{codigo: codigoConsulta, tipo: 'BARRA', es_principal: true}]);
});

test('una respuesta externa no pisa lo que la persona escribe durante la consulta', async t => {
    const c = await catalogo(t); await c.responder(0); c.el('btnNuevoProducto').click(); consultarCodigo(c);
    c.campo('inputNombre', 'Mi nombre revisado'); c.campo('inputDescripcion', 'Mi descripción');
    await c.responder(1, resultadoExterno());
    assert.equal(c.el('inputNombre').value, 'Mi nombre revisado'); assert.equal(c.el('inputDescripcion').value, 'Mi descripción');
    c.el('usarDatosProducto').click();
    assert.equal(c.el('inputNombre').value, 'Crema de avellanas 350 g');
    assert.equal(c.el('listaCodigosNuevo').querySelectorAll('.ss-code-row').length, 1);
});

test('un producto ya registrado se muestra sin asociar código ni copiarlo como nuevo', async t => {
    const c = await catalogo(t); await c.responder(0); c.el('btnNuevoProducto').click(); consultarCodigo(c);
    await c.responder(1, {success: true, mensaje: 'Este producto ya está registrado en SmartStock.', data: {estado: 'existente', codigo: codigoConsulta, producto: {id: 1, nombre: 'Ya existe', sku: 'FER-1', activo: false}}});
    assert.equal(c.el('inputNombre').value, ''); assert.equal(c.el('listaCodigosNuevo').querySelectorAll('.ss-code-row').length, 0);
    assert.match(c.el('resultadoConsultaCodigo').textContent, /Ya existe.*Inactivo/);
    c.el('verProductoEncontrado').click();
    assert.equal(c.el('modalNuevoProducto').classList.contains('show'), false);
    assert.equal(c.el('modalDetalleProducto').classList.contains('show'), true);
    assert.equal(c.requests[2].url.pathname, '/api/v1/productos/1/');
    await c.responder(2, detalleProducto());
    assert.equal(c.el('detalleProductoFuente').hidden, true);
});

for (const estado of ['no_encontrado', 'no_compatible', 'indisponible', 'limite']) {
    test('la consulta ' + estado + ' conserva el código y permite crear manualmente', async t => {
        const c = await catalogo(t); await c.responder(0); c.el('btnNuevoProducto').click(); consultarCodigo(c);
        await c.responder(1, {success: true, mensaje: 'Puedes completar el producto manualmente.', data: {estado, codigo: codigoConsulta}});
        assert.equal(c.el('resultadoConsultaCodigo').hidden, true); assert.equal(c.el('guardarNuevoProducto').disabled, false);
        c.campo('inputSku', 'MANUAL-1'); c.campo('inputNombre', 'Nombre manual'); c.campo('inputPrecio', '500'); c.enviar('formCrearProducto');
        const payload = JSON.parse(c.requests[2].options.body);
        assert.equal(payload.codigos_barra[0].codigo, codigoConsulta); assert.equal(payload.ficha_externa_id, undefined);
    });
}

test('Enter en el lector físico consulta el código y evita enviar el formulario', async t => {
    const c = await catalogo(t); await c.responder(0); c.el('btnNuevoProducto').click();
    c.campo('consultaCodigoProducto', codigoConsulta);
    const evento = new c.w.KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true}); c.el('consultaCodigoProducto').dispatchEvent(evento);
    assert.equal(evento.defaultPrevented, true); assert.equal(c.requests.length, 2);
    assert.equal(c.requests[1].options.method, undefined); await c.responder(1, resultadoExterno());
});

test('dos Enter seguidos del lector no duplican una consulta en curso', async t => {
    const c = await catalogo(t); await c.responder(0); c.el('btnNuevoProducto').click(); consultarCodigo(c);
    c.el('consultaCodigoProducto').dispatchEvent(new c.w.KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true}));
    assert.equal(c.requests.length, 2); await c.responder(1, resultadoExterno());
});

test('cambiar el código invalida una respuesta anterior aunque el servidor termine después', async t => {
    const c = await catalogo(t); await c.responder(0); c.el('btnNuevoProducto').click(); consultarCodigo(c);
    c.campo('consultaCodigoProducto', '5449000000996');
    assert.equal(c.el('guardarNuevoProducto').disabled, false);
    await c.responder(1, resultadoExterno());
    assert.equal(c.el('inputNombre').value, ''); assert.equal(c.el('resultadoConsultaCodigo').hidden, true);
    assert.equal(c.el('listaCodigosNuevo').querySelectorAll('.ss-code-row').length, 0);
});

test('cerrar y abrir nuevo producto descarta la consulta pendiente y su resultado', async t => {
    const c = await catalogo(t); await c.responder(0); c.el('btnNuevoProducto').click(); consultarCodigo(c);
    c.modelos.get(c.el('modalNuevoProducto')).hide(); c.el('btnNuevoProducto').click();
    c.campo('inputNombre', 'Otro producto'); await c.responder(1, resultadoExterno());
    assert.equal(c.el('inputNombre').value, 'Otro producto'); assert.equal(c.el('consultaCodigoProducto').value, '');
    assert.equal(c.el('resultadoConsultaCodigo').hidden, true);
});

test('una segunda consulta retira solo los datos automáticos anteriores y conserva los editados', async t => {
    const c = await catalogo(t); await c.responder(0); c.el('btnNuevoProducto').click(); consultarCodigo(c); await c.responder(1, resultadoExterno());
    c.campo('inputDescripcion', 'Descripción ajustada por mí'); consultarCodigo(c, '5449000000996');
    assert.equal(c.el('inputNombre').value, ''); assert.equal(c.el('inputDescripcion').value, 'Descripción ajustada por mí');
    await c.responder(2, resultadoExterno({codigo: '5449000000996', ficha_externa_id: 13, sugerencia: {nombre: 'Bebida 330 ml', descripcion: 'Descripción externa'}}));
    assert.equal(c.el('inputNombre').value, 'Bebida 330 ml'); assert.equal(c.el('inputDescripcion').value, 'Descripción ajustada por mí');
    const codigos = [...c.el('listaCodigosNuevo').querySelectorAll('[data-campo-codigo="codigo"]')].map(n => n.value);
    assert.deepEqual(codigos, ['5449000000996']);
});

test('cámara de autocompletado consulta después de volver al modal y conserva el tipo QR', async t => {
    const c = await catalogo(t, '', {scanner: true}); await c.responder(0); c.el('btnNuevoProducto').click();
    c.el('modalNuevoProducto').querySelector('[data-target="consultaCodigoProducto"]').click(); await tick();
    const qr = 'https://marca.example/01/03017620422003';
    c.lector.scan(qr, {result: {format: {formatName: 'QR_CODE'}}}); assert.equal(c.requests.length, 1);
    c.lector.scan(qr, {result: {format: {formatName: 'QR_CODE'}}}); await tick();
    assert.equal(c.el('modalNuevoProducto').classList.contains('show'), true);
    assert.equal(c.requests[1].url.searchParams.get('codigo'), qr);
    await c.responder(1, resultadoExterno({codigo: qr}));
    assert.equal(c.el('listaCodigosNuevo').querySelector('select').value, 'QR');
    assert.equal(c.el('inputNombre').value, 'Crema de avellanas 350 g');
});

test('cancelar cámara de consulta no agrega un código ni borra campos escritos', async t => {
    const c = await catalogo(t, '', {scanner: true}); await c.responder(0); c.completarNuevo();
    c.el('modalNuevoProducto').querySelector('[data-target="consultaCodigoProducto"]').click(); await tick();
    c.modelos.get(c.el('ssModalCamara')).hide(); await tick();
    assert.equal(c.requests.length, 1); assert.equal(c.el('inputNombre').value, 'Producto nuevo');
    assert.equal(c.el('listaCodigosNuevo').querySelectorAll('.ss-code-row').length, 0);
});

test('texto e imagen externa no ejecutan HTML ni URLs no permitidas', async t => {
    const c = await catalogo(t); await c.responder(0); c.el('btnNuevoProducto').click(); consultarCodigo(c);
    await c.responder(1, resultadoExterno({sugerencia: {nombre: '<img src=x onerror=alert(1)>', descripcion: '<script>alert(1)</script>', imagen_url: 'javascript:alert(1)'}, fuente: {url: 'javascript:alert(1)'}}));
    assert.equal(c.el('resultadoConsultaCodigo').querySelectorAll('img,script').length, 0);
    assert.match(c.el('resultadoConsultaCodigo').textContent, /<img/);
    assert.equal(c.el('resultadoConsultaCodigo').querySelector('a').hasAttribute('href'), false);
});

test('fallo de red y respuestas inválidas liberan el formulario y permiten reintentar', async t => {
    const c = await catalogo(t); await c.responder(0); c.el('btnNuevoProducto').click(); consultarCodigo(c);
    c.requests[1].reject(new c.w.TypeError('Sin conexión')); await tick();
    assert.equal(c.el('guardarNuevoProducto').disabled, false); assert.match(c.el('estadoConsultaCodigo').textContent, /conectar/);
    c.el('buscarDatosProducto').click(); await c.responder(2, {data: {estado: 'externo', codigo: 'OTRO'}});
    assert.equal(c.el('inputNombre').value, ''); assert.match(c.el('estadoConsultaCodigo').textContent, /leer/);
});

test('el detalle conserva la atribución de la ficha importada', async t => {
    const c = await catalogo(t); await c.responder(0);
    c.el('listaProductos').querySelector('[data-accion="detalle"]').click();
    await c.responder(1, detalleProducto({fuente_externa: resultadoExterno().data.fuente}));
    assert.equal(c.el('detalleProductoFuente').hidden, false); assert.match(c.el('detalleProductoFuente').textContent, /Open Food Facts.*ODbL/);
    assert.equal(c.el('detalleProductoFuente').querySelector('a').rel, 'noopener noreferrer');
});

test('ambos paginadores cambian de página y retiran controles durante la carga', async t => {
    const c = await catalogo(t);
    await c.responder(0);
    assert.equal(c.el('listaProductos').querySelectorAll('tr.ss-product-row').length, 25);
    assert.deepEqual(c.paginasActuales(), ['1', '1']);
    c.paginar(2, true);
    assert.equal(c.el('paginacionProductos').childElementCount, 0);
    assert.equal(c.el('paginacionProductosSuperior').childElementCount, 0);
    assert.equal(c.el('listaProductos').getAttribute('aria-busy'), 'true');
    assert.equal(c.requests[1].url.searchParams.get('page'), '2');
    await c.responder(1, datos(55, 2));
    assert.deepEqual(c.paginasActuales(), ['2', '2']);
    assert.match(c.el('resumenPaginacionProductos').textContent, /26–50 de 55/);
    assert.equal(c.w.document.activeElement, c.el('totalProductos'));
});

test('una respuesta anterior no aparece durante los 300 ms del debounce', async t => {
    const c = await catalogo(t);
    c.buscar('  CAT-55  ');
    await c.responder(0);
    assert.equal(c.el('listaProductos').querySelectorAll('.ss-product-row').length, 0);
    assert.equal(c.el('listaProductos').getAttribute('aria-busy'), 'true');
    await c.debounce();
    assert.equal(c.requests[1].url.searchParams.get('search'), 'CAT-55');
    assert.equal(c.requests[1].url.searchParams.get('page'), '1');
    await c.responder(1, {count: 1, results: [producto(55)]});
    assert.match(c.el('listaProductos').textContent, /Producto 55/);
    assert.equal(c.el('listaProductos').querySelectorAll('.ss-product-row').length, 1);
});

test('ordenar durante el debounce conserva la búsqueda y cancela el temporizador', async t => {
    const c = await catalogo(t);
    await c.responder(0);
    c.buscar('Producto');
    c.ordenar('-precio_referencia,-id');
    await c.debounce();
    assert.equal(c.requests.length, 2);
    assert.equal(c.requests[1].url.searchParams.get('search'), 'Producto');
    assert.equal(c.requests[1].url.searchParams.get('ordering'), '-precio_referencia,-id');
    await c.responder(1);
    c.paginar(2);
    assert.equal(c.requests[2].url.searchParams.get('search'), 'Producto');
    assert.equal(c.requests[2].url.searchParams.get('ordering'), '-precio_referencia,-id');
});

test('las seis opciones envían su orden a la API y reinician la página', async t => {
    const c = await catalogo(t);
    await c.responder(0);
    const ordenes = ['nombre,id', '-nombre,-id', 'precio_referencia,id',
        '-precio_referencia,-id', 'fecha_creacion,id', '-fecha_creacion,-id'];
    for (const orden of ordenes) {
        c.paginar(2);
        await c.responder(c.requests.length - 1, datos(55, 2));
        c.ordenar(orden);
        const i = c.requests.length - 1;
        assert.equal(c.requests[i].url.searchParams.get('ordering'), orden);
        assert.equal(c.requests[i].url.searchParams.get('page'), '1');
        await c.responder(i);
        assert.deepEqual(c.paginasActuales(), ['1', '1']);
    }
});

test('un JSON atrasado no reemplaza una búsqueda más reciente', async t => {
    const c = await catalogo(t);
    let terminarJSON;
    c.requests[0].resolve({ok: true, status: 200,
        json: () => new Promise(resolve => { terminarJSON = resolve; })});
    await tick();
    c.buscar('CAT-55');
    await c.debounce();
    await c.responder(1, {count: 1, results: [producto(55)]});
    terminarJSON(datos());
    await tick();
    assert.equal(c.el('listaProductos').querySelectorAll('.ss-product-row').length, 1);
    assert.match(c.el('listaProductos').textContent, /Producto 55/);
    assert.equal(c.el('listaProductos').getAttribute('aria-busy'), 'false');
});

test('una página eliminada recupera la última válida sin perder búsqueda u orden', async t => {
    const c = await catalogo(t, '?q=Producto');
    await c.responder(0);
    c.ordenar('-nombre,-id');
    await c.responder(1);
    c.paginar(3);
    await c.responder(2, {}, 404);
    assert.equal(c.requests[3].url.searchParams.get('page'), 'last');
    assert.equal(c.requests[3].url.searchParams.get('search'), 'Producto');
    assert.equal(c.requests[3].url.searchParams.get('ordering'), '-nombre,-id');
    await c.responder(3, datos(50, 2));
    assert.deepEqual(c.paginasActuales(), ['2', '2']);
    assert.match(c.el('resumenPaginacionProductos').textContent, /26–50 de 50/);
});

test('el catálogo vacío tras recuperar una página no deja botones antiguos', async t => {
    const c = await catalogo(t);
    await c.responder(0);
    c.paginar(3);
    await c.responder(1, {}, 404);
    await c.responder(2, datos(0));
    assert.deepEqual(c.paginasActuales(), [undefined, undefined]);
    assert.equal(c.el('resumenPaginacionProductos').textContent, 'No hay productos para mostrar.');
    assert.equal(c.el('listaProductos').getAttribute('aria-busy'), 'false');
});

test('un segundo 404 termina con error sin reintentos infinitos', async t => {
    const c = await catalogo(t);
    await c.responder(0);
    c.paginar(3);
    await c.responder(1, {}, 404);
    await c.responder(2, {}, 404);
    assert.equal(c.requests.length, 3);
    assert.equal(c.el('totalProductos').textContent, 'Error de carga');
    assert.equal(c.el('listaProductos').getAttribute('aria-busy'), 'false');
});

test('la navegación pendiente no roba el foco si el usuario pasa al buscador', async t => {
    const c = await catalogo(t);
    await c.responder(0);
    c.paginar(2);
    c.el('buscadorProductos').focus();
    await c.responder(1, datos(55, 2));
    assert.equal(c.w.document.activeElement, c.el('buscadorProductos'));
});

test('vaciar la búsqueda desde otra página vuelve a la primera sin search', async t => {
    const c = await catalogo(t, '?q=Producto');
    await c.responder(0);
    c.paginar(3);
    await c.responder(1, datos(55, 3));
    c.buscar('');
    await c.debounce();
    assert.equal(c.requests[2].url.searchParams.get('page'), '1');
    assert.equal(c.requests[2].url.searchParams.has('search'), false);
    await c.responder(2);
    assert.deepEqual(c.paginasActuales(), ['1', '1']);
});

const detalleProducto = (extra = {}) => ({id: 1, sku: 'CAT-1', nombre: 'Producto completo', descripcion: 'Descripción que debe conservarse.\nSegunda línea.', precio_referencia: '1000.00', activo: true, fecha_creacion: '2026-10-28T02:30:00Z', fecha_modificacion: '2026-10-28T02:30:00Z', codigos_barra: [{id: 10, codigo: '7801234567890', tipo: 'BARRA', es_principal: true}, {id: 11, codigo: 'https://ejemplo.cl/p?x=1,2', tipo: 'QR', es_principal: false}], existencias: [{id: 1, nombre: 'Bodega Central', stock: 3, minimo: 5, estado: 'bajo'}], ...extra});
const editarPrimero = c => c.el('listaProductos').querySelector('.btn-editar').click();
const minimoProducto = (extra = {}) => ({data: {producto_id: 1, sku: 'CAT-1', nombre: 'Producto completo', bodega_id: 1, bodega: 'Bodega Central', stock_actual: 3, cantidad_minima: 0, configurado: false, alerta_stock_bajo_activa: false, estado_stock: 'suficiente', ...extra}});
const configurarPrimero = c => c.el('listaProductos').querySelector('[data-accion="minimo"]').click();

test('configurar mínimo carga datos actuales de la bodega antes de permitir guardar', async t => {
    const c = await catalogo(t); await c.responder(0); configurarPrimero(c);
    assert.equal(c.requests[1].url.pathname, '/api/v1/productos/1/stock-minimo/');
    assert.equal(c.requests[1].url.searchParams.get('bodega'), '1');
    assert.equal(c.el('guardarStockMinimo').disabled, true); c.enviar('formStockMinimo'); assert.equal(c.requests.length, 2);
    await c.responder(1, minimoProducto({cantidad_minima: 7, stock_actual: 6}));
    assert.equal(c.el('guardarStockMinimo').disabled, false); assert.equal(c.el('inputStockMinimo').value, '7');
    assert.equal(c.el('bodegaStockMinimo').textContent, 'Bodega Central'); assert.equal(c.el('cantidadStockMinimo').textContent, '6 unid.');
    assert.match(c.el('previsionStockMinimo').textContent, /Stock bajo/);
    assert.match(c.el('alcanceStockProductos').textContent, /Mínimo 0: aviso de stock bajo desactivado/);
});

test('el mínimo espera a que termine la apertura del modal antes de aceptar el envío', async t => {
    const c = await catalogo(t); await c.responder(0);
    const elemento = c.el('modalStockMinimo'), modal = c.w.bootstrap.Modal.getOrCreateInstance(elemento);
    modal.show = () => { elemento.classList.add('show'); };
    configurarPrimero(c); await c.responder(1, minimoProducto()); c.campo('inputStockMinimo', '5');
    assert.equal(c.el('guardarStockMinimo').disabled, true); c.enviar('formStockMinimo'); assert.equal(c.requests.length, 2);
    elemento.dispatchEvent(new c.w.Event('shown.bs.modal')); assert.equal(c.el('guardarStockMinimo').disabled, false);
    c.enviar('formStockMinimo'); assert.equal(c.requests.length, 3);
});

test('guardar mínimo envía solo el umbral y la bodega elegida y conserva los filtros al recargar', async t => {
    const c = await catalogo(t, '?bodega=2&q=Producto&activo=true&disponibilidad=bajo&ordering=-nombre,-id');
    await c.responder(0); configurarPrimero(c);
    await c.responder(1, minimoProducto({bodega_id: 2, bodega: 'Anexo'})); c.campo('inputStockMinimo', '5'); c.enviar('formStockMinimo');
    assert.equal(c.requests[2].options.method, 'PATCH');
    assert.deepEqual(JSON.parse(c.requests[2].options.body), {bodega: 2, cantidad_minima: 5});
    assert.equal(c.requests[2].url.pathname, '/api/v1/productos/1/stock-minimo/');
    await c.responder(2, minimoProducto({bodega_id: 2, bodega: 'Anexo', cantidad_minima: 5}));
    assert.equal(c.el('avisoResultadoProductos'), null); assert.equal(c.avisos.length, 1);
    for (const [k, v] of Object.entries({bodega: '2', search: 'Producto', activo: 'true', disponibilidad: 'bajo', ordering: '-nombre,-id'})) assert.equal(c.requests[3].url.searchParams.get(k), v);
    await c.responder(3, {count: 0, results: []}); assert.match(c.el('listaProductos').textContent, /mínimo mayor que 0/);
});

test('la previsión del mínimo distingue umbral inclusivo, suficiente y aviso desactivado', async t => {
    const c = await catalogo(t); await c.responder(0); configurarPrimero(c); await c.responder(1, minimoProducto());
    for (const [valor, estado] of [['3', 'Stock bajo'], ['2', 'Stock suficiente'], ['0', 'Aviso de stock bajo desactivado']]) {
        c.campo('inputStockMinimo', valor); assert.match(c.el('previsionStockMinimo').textContent, new RegExp(estado));
    }
    assert.equal(c.requests.length, 2);
});

test('mínimo cero se guarda explícitamente y la previsión mantiene agotados', async t => {
    const c = await catalogo(t); await c.responder(0); configurarPrimero(c); await c.responder(1, minimoProducto({stock_actual: 0, cantidad_minima: 5}));
    c.campo('inputStockMinimo', '0'); assert.match(c.el('previsionStockMinimo').textContent, /Agotado/); c.enviar('formStockMinimo');
    assert.deepEqual(JSON.parse(c.requests[2].options.body), {bodega: 1, cantidad_minima: 0});
    await c.responder(2, minimoProducto({cantidad_minima: 0})); assert.equal(c.el('avisoResultadoProductos'), null); assert.equal(c.avisos.length, 1);
});

test('rechaza mínimo vacío, negativo, fraccionario o fuera del rango sin enviarlo', async t => {
    const c = await catalogo(t); await c.responder(0); configurarPrimero(c); await c.responder(1, minimoProducto());
    for (const valor of ['', '-1', '1.5', '2147483648']) {
        c.campo('inputStockMinimo', valor); c.enviar('formStockMinimo');
        assert.equal(c.requests.length, 2); assert.equal(c.el('inputStockMinimo').getAttribute('aria-invalid'), 'true');
        assert.match(c.el('errorCampoStockMinimo').textContent, /número entero/);
    }
    c.campo('inputStockMinimo', '5'); assert.equal(c.el('inputStockMinimo').hasAttribute('aria-invalid'), false);
});

test('mínimo bloquea doble envío y cierre pendiente y no repite al terminar durante el fade', async t => {
    const c = await catalogo(t); await c.responder(0); configurarPrimero(c); await c.responder(1, minimoProducto());
    c.campo('inputStockMinimo', '5'); c.enviar('formStockMinimo'); c.enviar('formStockMinimo'); assert.equal(c.requests.length, 3);
    assert.equal(c.el('inputStockMinimo').disabled, true); assert.equal(c.el('formStockMinimo').getAttribute('aria-busy'), 'true');
    const modal = c.modelos.get(c.el('modalStockMinimo')); modal.hide(); assert.equal(c.el('modalStockMinimo').classList.contains('show'), true);
    modal.hide = () => {}; await c.responder(2, minimoProducto({cantidad_minima: 5}));
    c.enviar('formStockMinimo'); assert.equal(c.requests.length, 4); assert.equal(c.el('guardarStockMinimo').disabled, true);
});

test('errores del servidor conservan el mínimo escrito y permiten corregirlo', async t => {
    const c = await catalogo(t); await c.responder(0); configurarPrimero(c); await c.responder(1, minimoProducto());
    c.campo('inputStockMinimo', '5'); c.enviar('formStockMinimo'); await c.responder(2, {errores: {cantidad_minima: ['Mínimo rechazado.']}}, 400);
    assert.equal(c.el('inputStockMinimo').value, '5'); assert.equal(c.el('guardarStockMinimo').disabled, false);
    assert.match(c.el('errorCampoStockMinimo').textContent, /Mínimo rechazado/);
    c.campo('inputStockMinimo', '4'); c.enviar('formStockMinimo'); assert.equal(JSON.parse(c.requests[3].options.body).cantidad_minima, 4);
});

test('la carga del mínimo permite reintentar y no habilita guardar ante un error', async t => {
    const c = await catalogo(t); await c.responder(0); configurarPrimero(c); await c.responder(1, {detail: 'Servidor temporalmente no disponible'}, 500);
    assert.equal(c.el('guardarStockMinimo').disabled, true); assert.equal(c.el('reintentarStockMinimo').hidden, false);
    c.el('reintentarStockMinimo').click(); await c.responder(2, minimoProducto({cantidad_minima: 4}));
    assert.equal(c.el('inputStockMinimo').value, '4'); assert.equal(c.el('guardarStockMinimo').disabled, false);
});

test('una bodega desactivada durante la edición informa el motivo sin perder el valor', async t => {
    const c = await catalogo(t); await c.responder(0); configurarPrimero(c); await c.responder(1, minimoProducto());
    c.campo('inputStockMinimo', '5'); c.enviar('formStockMinimo'); await c.responder(2, {bodega: ['Selecciona una bodega activa.']}, 400);
    assert.match(c.el('errorStockMinimo').textContent, /bodega activa/); assert.equal(c.el('inputStockMinimo').value, '5');
});

test('una respuesta atrasada del mínimo cerrado no reemplaza otro producto', async t => {
    const c = await catalogo(t); await c.responder(0); configurarPrimero(c);
    c.modelos.get(c.el('modalStockMinimo')).hide(); c.el('listaProductos').querySelectorAll('[data-accion="minimo"]')[1].click();
    await c.responder(2, minimoProducto({producto_id: 2, sku: 'CAT-2', nombre: 'Segundo producto', cantidad_minima: 8}));
    await c.responder(1, minimoProducto({cantidad_minima: 1}));
    assert.equal(c.el('nombreStockMinimo').textContent, 'Segundo producto'); assert.equal(c.el('inputStockMinimo').value, '8');
    c.enviar('formStockMinimo'); assert.equal(c.requests[3].url.pathname, '/api/v1/productos/2/stock-minimo/');
});

test('una respuesta del mínimo con bodega incorrecta no puede guardarse', async t => {
    const c = await catalogo(t); await c.responder(0); configurarPrimero(c); await c.responder(1, minimoProducto({bodega_id: 2}));
    assert.equal(c.el('guardarStockMinimo').disabled, true); assert.equal(c.el('datosStockMinimo').hidden, true);
    assert.match(c.el('estadoStockMinimo').textContent, /esta bodega/);
});

test('sin permiso configurar mínimo conserva los valores como texto de lectura', async t => {
    const c = await catalogo(t, '', {permisos: {editar: false, configurar_minimo: false}}); await c.responder(0);
    assert.equal(c.el('listaProductos').querySelectorAll('[data-accion="minimo"]').length, 0); assert.match(c.el('listaProductos').textContent, /Mínimo: 2/);
    c.el('listaProductos').querySelector('[data-accion="detalle"]').click(); await c.responder(1, detalleProducto());
    assert.equal(c.el('detalleProductoStock').querySelectorAll('button').length, 0);
});

test('configurar desde detalle abre la bodega indicada y vuelve a cargar el detalle al cancelar', async t => {
    const c = await catalogo(t); await c.responder(0); c.el('listaProductos').querySelector('[data-accion="detalle"]').click();
    await c.responder(1, detalleProducto({existencias: [{id: 2, nombre: 'Anexo', stock: 3, minimo: 0, estado: 'suficiente'}]}));
    c.el('detalleProductoStock').querySelector('[data-accion="minimo"]').click();
    assert.equal(c.el('modalDetalleProducto').classList.contains('show'), false); assert.equal(c.el('modalStockMinimo').classList.contains('show'), true);
    assert.equal(c.requests[2].url.searchParams.get('bodega'), '2'); await c.responder(2, minimoProducto({bodega_id: 2, bodega: 'Anexo'}));
    c.modelos.get(c.el('modalStockMinimo')).hide(); assert.equal(c.el('modalDetalleProducto').classList.contains('show'), true);
    assert.equal(c.requests[3].url.pathname, '/api/v1/productos/1/');
});

test('mínimo muestra nombre y bodega como texto y bloquea guardar si se revoca el permiso', async t => {
    const c = await catalogo(t); await c.responder(0); configurarPrimero(c);
    await c.responder(1, minimoProducto({nombre: '<img src=x onerror=alert(1)>', bodega: '<svg onload=alert(1)>'}));
    assert.equal(c.el('nombreStockMinimo').querySelector('img'), null); assert.equal(c.el('bodegaStockMinimo').querySelector('svg'), null);
    c.campo('inputStockMinimo', '5'); c.enviar('formStockMinimo'); await c.responder(2, {detail: 'Permiso revocado'}, 403);
    assert.equal(c.el('inputStockMinimo').value, '5'); assert.equal(c.el('guardarStockMinimo').disabled, true);
    assert.match(c.el('errorStockMinimo').textContent, /Permiso revocado/);
});

test('combina estado, bodega y disponibilidad con búsqueda y conserva todo al paginar', async t => {
    const c = await catalogo(t); await c.responder(0);
    c.buscar('Producto'); c.campo('bodegaProductos', '2', 'change'); c.campo('estadoProductos', 'false', 'change'); c.campo('stockProductos', 'bajo', 'change');
    await c.responder(c.requests.length - 1); c.paginar(2);
    const p = c.requests.at(-1).url.searchParams;
    for (const [k, v] of Object.entries({page: '2', bodega: '2', activo: 'false', disponibilidad: 'bajo', search: 'Producto'})) assert.equal(p.get(k), v);
    c.el('limpiarFiltrosProductos').click(); const limpios = c.requests.at(-1).url.searchParams;
    assert.equal(limpios.get('bodega'), '1'); assert.equal(limpios.get('page'), '1'); assert.equal(limpios.has('search'), false); assert.equal(limpios.has('activo'), false); assert.equal(limpios.has('disponibilidad'), false);
});

test('un enlace del Dashboard conserva la bodega y el SKU al entrar al catálogo', async t => {
    const c = await catalogo(t, '?q=CAT-55&bodega=2');
    assert.equal(c.requests[0].url.searchParams.get('bodega'), '2'); assert.equal(c.requests[0].url.searchParams.get('search'), 'CAT-55');
    await c.responder(0, {count: 1, results: [producto(55)]}); assert.match(c.el('alcanceStockProductos').textContent, /Anexo/);
});

test('edición carga el detalle crudo antes de permitir guardar y omite descripción y códigos sin cambios', async t => {
    const c = await catalogo(t); await c.responder(0); editarPrimero(c);
    assert.equal(c.el('guardarEditarProducto').disabled, true); assert.equal(c.requests[1].url.pathname, '/api/v1/productos/1/');
    await c.responder(1, detalleProducto());
    assert.equal(c.el('editDescripcion').value, detalleProducto().descripcion);
    const filas = [...c.el('listaCodigosEditar').querySelectorAll('.ss-code-row')];
    assert.equal(filas[1].querySelector('input').value, 'https://ejemplo.cl/p?x=1,2'); assert.equal(filas[1].querySelector('select').value, 'QR');
    assert.equal(filas[0].querySelector('[type=radio]').checked, true);
    c.campo('editPrecio', '1234.50'); c.enviar('formEditarProducto');
    assert.deepEqual(JSON.parse(c.requests[2].options.body), {precio_referencia: '1234.50'});
    assert.equal(c.requests[2].options.method, 'PATCH');
});

test('detalle envuelto también funciona y guardar sin cambios no escribe', async t => {
    const c = await catalogo(t); await c.responder(0); editarPrimero(c); await c.responder(1, {data: detalleProducto()});
    c.enviar('formEditarProducto'); assert.equal(c.requests.length, 2); assert.equal(c.el('avisoResultadoProductos'), null); assert.equal(c.avisos.length, 0);
});

test('un error al cargar edición mantiene guardar bloqueado y permite reintentar sin vaciar datos del servidor', async t => {
    const c = await catalogo(t); await c.responder(0); editarPrimero(c); await c.responder(1, {}, 503);
    assert.equal(c.el('guardarEditarProducto').disabled, true); assert.equal(c.el('reintentarDetalleEdicion').hidden, false);
    c.enviar('formEditarProducto'); assert.equal(c.requests.length, 2);
    c.el('reintentarDetalleEdicion').click(); await c.responder(2, detalleProducto());
    assert.equal(c.el('guardarEditarProducto').disabled, false); assert.equal(c.el('editDescripcion').value, detalleProducto().descripcion);
});

test('una respuesta de edición tras cerrar no vuelve a poblar el formulario', async t => {
    const c = await catalogo(t); await c.responder(0); editarPrimero(c); c.modelos.get(c.el('modalEditarProducto')).hide();
    await c.responder(1, detalleProducto()); assert.equal(c.el('editDescripcion').value, ''); assert.equal(c.el('guardarEditarProducto').disabled, true);
});

test('alta permite filas individuales, tipos y principal explícito sin separar un QR por comas', async t => {
    const c = await catalogo(t); await c.responder(0); c.completarNuevo();
    c.campo('inputCodigoBarra', 'https://ejemplo.cl/p?x=1,2'); c.campo('tipoCodigoNuevo', 'QR', 'change'); c.el('agregarCodigoNuevo').click();
    c.campo('inputCodigoBarra', '7800000000001'); c.campo('tipoCodigoNuevo', 'BARRA', 'change'); c.el('agregarCodigoNuevo').click();
    const radios = [...c.el('listaCodigosNuevo').querySelectorAll('[type=radio]')]; radios[1].checked = true; radios[1].dispatchEvent(new c.w.Event('change', {bubbles: true}));
    c.enviar('formCrearProducto');
    const d = JSON.parse(c.requests[1].options.body);
    assert.equal(d.sku, 'FER-NUEVO'); assert.equal(d.precio_referencia, '1234.50');
    assert.deepEqual(d.codigos_barra, [{codigo: 'https://ejemplo.cl/p?x=1,2', tipo: 'QR', es_principal: false}, {codigo: '7800000000001', tipo: 'BARRA', es_principal: true}]);
});

test('código pendiente se incluye al guardar y quitar una fila elige un principal restante', async t => {
    const c = await catalogo(t); await c.responder(0); c.completarNuevo();
    c.campo('inputCodigoBarra', 'COD-A'); c.el('agregarCodigoNuevo').click(); c.campo('inputCodigoBarra', 'COD-B'); c.el('agregarCodigoNuevo').click();
    c.el('listaCodigosNuevo').querySelector('[data-quitar-codigo="0"]').click();
    assert.equal(c.el('listaCodigosNuevo').querySelector('[type=radio]').checked, true);
    c.campo('inputCodigoBarra', 'COD-C'); c.enviar('formCrearProducto');
    assert.deepEqual(JSON.parse(c.requests[1].options.body).codigos_barra.map(c => c.codigo), ['COD-B', 'COD-C']);
});

test('duplicados en filas e importes inválidos no generan solicitudes ni se convierten en cero', async t => {
    const c = await catalogo(t); await c.responder(0); c.completarNuevo(); c.campo('inputPrecio', ''); c.enviar('formCrearProducto');
    assert.equal(c.requests.length, 1); assert.equal(c.el('inputPrecio').classList.contains('is-invalid'), true);
    c.campo('inputPrecio', '1234.50'); c.campo('inputCodigoBarra', 'COD-A'); c.el('agregarCodigoNuevo').click(); c.campo('inputCodigoBarra', 'COD-A'); c.enviar('formCrearProducto');
    assert.equal(c.requests.length, 1); assert.match(c.el('errorCodigosNuevo').textContent, /ya está/);
});

test('errores por campo conservan nombre, descripción, precio y códigos del formulario', async t => {
    const c = await catalogo(t); await c.responder(0); c.completarNuevo(); c.campo('inputCodigoBarra', 'COD-A'); c.enviar('formCrearProducto');
    await c.responder(1, {mensaje: 'Revisa los datos.', errores: {sku: ['Ya existe.'], codigos_barra: ['Código de otro producto.']}}, 400);
    assert.equal(c.el('inputSku').value, 'fer-nuevo'); assert.equal(c.el('inputDescripcion').value, 'Descripción nueva'); assert.equal(c.el('inputPrecio').value, '1234.50');
    assert.equal(c.el('listaCodigosNuevo').querySelector('input').value, 'COD-A'); assert.equal(c.el('inputSku').getAttribute('aria-invalid'), 'true'); assert.match(c.el('errorCodigosNuevo').textContent, /otro producto/);
});

test('guardar bloquea duplicados y cierre, incluso si reaparece el modal durante la transición posterior', async t => {
    const c = await catalogo(t); await c.responder(0); c.completarNuevo(); c.enviar('formCrearProducto'); c.enviar('formCrearProducto');
    assert.equal(c.requests.length, 2); c.modelos.get(c.el('modalNuevoProducto')).hide(); assert.equal(c.el('modalNuevoProducto').classList.contains('show'), true);
    c.el('btnNuevoProducto').click(); assert.equal(c.el('inputNombre').value, 'Producto nuevo');
    await c.responder(1, {data: detalleProducto({nombre: 'Producto nuevo'})}, 201);
    const cantidad = c.requests.length; c.modelos.get(c.el('modalNuevoProducto')).show(); c.enviar('formCrearProducto'); assert.equal(c.requests.length, cantidad);
    assert.equal(c.requests.filter(r => r.options.method === 'POST').length, 1);
});

test('el listado conserva los centavos del precio de referencia y textos maliciosos se muestran como texto', async t => {
    const c = await catalogo(t); await c.responder(0, {count: 1, results: [{...producto(1), nombre: '<img src=x onerror=alert(1)>', sku: '<script>mal</script>', precio_referencia: '1234.50', estado_stock: 'bajo', stock_minimo: 5}]});
    assert.match(c.el('listaProductos').querySelector('.ss-product-price-value').textContent, /1\.234,50/);
    assert.equal(c.el('listaProductos').querySelector('img'), null); assert.equal(c.el('listaProductos').querySelector('script'), null);
    assert.match(c.el('listaProductos').textContent, /Stock bajo/);
});

test('detalle muestra descripción completa, códigos y existencias con fechas de Chile', async t => {
    const c = await catalogo(t); await c.responder(0); c.el('listaProductos').querySelector('[data-accion="detalle"]').click();
    await c.responder(1, detalleProducto());
    assert.equal(c.el('detalleProductoDescripcion').textContent, detalleProducto().descripcion); assert.match(c.el('detalleProductoCodigos').textContent, /QR/);
    assert.match(c.el('detalleProductoStock').textContent, /Bodega Central/); assert.match(c.el('detalleProductoStock').textContent, /Stock bajo/);
    assert.equal(c.el('detalleProductoCreado').textContent, '27/10/2026 23:30');
    c.modelos.get(c.el('modalDetalleProducto')).hide(); c.el('listaProductos').querySelector('[data-accion="detalle"]').click(); c.modelos.get(c.el('modalDetalleProducto')).hide();
    await c.responder(2, detalleProducto({descripcion: 'Respuesta atrasada'})); assert.notEqual(c.el('detalleProductoDescripcion').textContent, 'Respuesta atrasada');
});

test('acciones visibles respetan permisos de servidor y los productos inactivos también se editan', async t => {
    const c = await catalogo(t, '', {permisos: {editar: true}}); await c.responder(0, {count: 1, results: [{...producto(1), activo: false}]});
    assert.ok(c.el('listaProductos').querySelector('.btn-editar')); assert.equal(c.el('btnNuevoProducto').hidden, true);
    assert.equal(c.el('listaProductos').querySelector('.btn-activar'), null); assert.equal(c.el('listaProductos').querySelector('.btn-eliminar-definitivo'), null);
    assert.equal(c.el('menu-usuarios').hidden, true);
});

test('desactivar identifica nombre y SKU, bloquea doble envío y no usa confirmaciones nativas', async t => {
    const c = await catalogo(t); await c.responder(0); c.el('listaProductos').querySelector('.btn-borrar').click(); await c.responder(1, detalleProducto());
    assert.equal(c.el('nombreAccionProducto').textContent, 'Producto completo'); assert.equal(c.el('skuAccionProducto').textContent, 'SKU: CAT-1');
    assert.match(c.el('descripcionAccionProducto').textContent, /Se conservarán/);
    c.enviar('formAccionProducto'); c.enviar('formAccionProducto'); assert.equal(c.requests.length, 3); assert.equal(c.requests[2].options.method, 'DELETE');
    c.modelos.get(c.el('modalAccionProducto')).hide(); assert.equal(c.el('modalAccionProducto').classList.contains('show'), true);
    await c.responder(2, {success: true}); assert.equal(c.el('avisoResultadoProductos'), null); assert.equal(c.avisos.length, 1);
});

test('reactivar usa POST y una eliminación con historial conserva la confirmación y el error', async t => {
    const c = await catalogo(t); await c.responder(0, {count: 1, results: [{...producto(1), activo: false}]});
    c.el('listaProductos').querySelector('.btn-activar').click(); await c.responder(1, detalleProducto({activo: false})); c.enviar('formAccionProducto');
    assert.equal(c.requests[2].url.pathname, '/api/v1/productos/1/activar/'); assert.equal(c.requests[2].options.method, 'POST');
    await c.responder(2, {success: true}); await c.responder(3, datos());
    c.el('listaProductos').querySelector('.btn-eliminar-definitivo').click(); await c.responder(4, detalleProducto()); c.enviar('formAccionProducto');
    assert.equal(c.requests[5].url.pathname, '/api/v1/productos/1/eliminar-definitivamente/');
    await c.responder(5, {mensaje: 'Tiene historial relacionado.'}, 409); assert.match(c.el('errorAccionProducto').textContent, /historial/); assert.equal(c.el('modalAccionProducto').classList.contains('show'), true);
});

test('estado cambiado antes de confirmar impide una desactivación duplicada', async t => {
    const c = await catalogo(t); await c.responder(0); c.el('listaProductos').querySelector('.btn-borrar').click(); await c.responder(1, detalleProducto({activo: false}));
    assert.equal(c.el('confirmarAccionProducto').disabled, true); assert.match(c.el('errorAccionProducto').textContent, /ya cambió/);
    c.enviar('formAccionProducto'); assert.equal(c.requests.filter(r => r.options.method === 'DELETE').length, 0);
});

test('opciones fallidas permiten reintentar sin habilitar escrituras ni asumir stock', async t => {
    const c = await catalogo(t, '', {opcionesManual: true}); await c.responder(0, {}, 503);
    assert.equal(c.el('btnNuevoProducto').hidden, true); assert.equal(c.el('reintentarOpcionesProductos').hidden, false);
    c.el('reintentarOpcionesProductos').click(); await c.responder(1, {data: {bodegas: [], bodega_predeterminada: null, permisos: {crear: true}}});
    await c.responder(2, {count: 1, results: [producto(1)]});
    assert.equal(c.el('stockProductos').disabled, true); assert.match(c.el('listaProductos').textContent, /Sin bodega activa/);
    assert.equal(c.requests[2].url.searchParams.has('bodega'), false);
});

test('un fallo de conexión al escribir conserva el formulario y solicita revisar el catálogo', async t => {
    const c = await catalogo(t); await c.responder(0); c.completarNuevo(); c.enviar('formCrearProducto');
    c.requests[1].reject(new TypeError('Failed to fetch')); await tick();
    assert.match(c.el('errorCrearProducto').textContent, /Revisa el catálogo/); assert.equal(c.el('inputNombre').value, 'Producto nuevo'); assert.equal(c.requests.length, 3);
});

test('consultas simultáneas con JWT vencido comparten renovación y usan el nuevo token', async t => {
    const c = await catalogo(t); await c.responder(0); editarPrimero(c); c.buscar('Producto'); await c.debounce();
    await c.responder(1, {}, 401); await c.responder(2, {}, 401);
    assert.equal(c.requests.filter(r => r.url.pathname === '/api/v1/auth/refresh/').length, 1);
    await c.responder(3, {access: 'nuevo', refresh: 'rotado'});
    assert.equal(c.requests[4].options.headers.Authorization, 'Bearer nuevo'); assert.equal(c.requests[5].options.headers.Authorization, 'Bearer nuevo');
    await c.responder(4, detalleProducto()); await c.responder(5, datos()); assert.equal(c.w.localStorage.getItem('refresh_token'), 'rotado');
});

test('cámara exige dos lecturas, añade QR individual y vuelve al formulario sin perder descripción', async t => {
    const c = await catalogo(t, '', {scanner: true}); await c.responder(0); c.completarNuevo();
    c.el('modalNuevoProducto').querySelector('[data-target="inputCodigoBarra"]').click(); await tick();
    c.lector.scan('https://ejemplo.cl/p?x=1,2', {result: {format: {formatName: 'QR_CODE'}}});
    assert.equal(c.el('listaCodigosNuevo').querySelectorAll('.ss-code-row').length, 0);
    c.lector.scan('https://ejemplo.cl/p?x=1,2', {result: {format: {formatName: 'QR_CODE'}}}); await tick();
    assert.equal(c.el('listaCodigosNuevo').querySelectorAll('.ss-code-row').length, 1);
    assert.equal(c.el('listaCodigosNuevo').querySelector('select').value, 'QR'); assert.equal(c.el('inputDescripcion').value, 'Descripción nueva');
    assert.equal(c.el('modalNuevoProducto').classList.contains('show'), true);
    c.enviar('formCrearProducto'); assert.equal(JSON.parse(c.requests[1].options.body).codigos_barra[0].codigo, 'https://ejemplo.cl/p?x=1,2');
});

test('cancelar cámara en edición conserva descripción, códigos, tipos y principal', async t => {
    const c = await catalogo(t, '', {scanner: true}); await c.responder(0); editarPrimero(c); await c.responder(1, detalleProducto());
    c.el('modalEditarProducto').querySelector('.ss-scan-code').click(); await tick(); c.modelos.get(c.el('ssModalCamara')).hide(); await tick();
    assert.equal(c.el('editDescripcion').value, detalleProducto().descripcion); assert.equal(c.el('listaCodigosEditar').querySelectorAll('.ss-code-row').length, 2);
    c.campo('editNombre', 'Nombre cambiado'); c.enviar('formEditarProducto'); assert.deepEqual(JSON.parse(c.requests[2].options.body), {nombre: 'Nombre cambiado'});
});
