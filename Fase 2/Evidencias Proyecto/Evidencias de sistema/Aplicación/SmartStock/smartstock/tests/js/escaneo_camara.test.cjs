const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {JSDOM} = require('jsdom');

const fuente = readFileSync(join(__dirname, '../../static/js/escaneo_camara.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

async function pantalla(t, {inicio = async () => {}, enfoque = []} = {}) {
    const dom = new JSDOM(`
        <button class="ss-scan-code" data-target="inputEscaner"></button>
        <input id="inputEscaner" data-codigos-editor="true">
        <div id="ssModalCamara"><div id="ssLectorCamara"></div><p id="ssCamaraEstado"></p></div>
    `, {runScripts: 'outside-only'});
    t.after(() => dom.window.close());
    const w = dom.window;
    const llamadas = [];
    const eventos = [];
    const modal = w.document.getElementById('ssModalCamara');
    const campo = w.document.getElementById('inputEscaner');
    const botones = w.document.querySelector('button');
    w.bootstrap = {Modal: {getOrCreateInstance: nodo => ({
        show() { nodo.dispatchEvent(new w.Event('shown.bs.modal')); },
        hide() {
            nodo.dispatchEvent(new w.Event('hide.bs.modal'));
            nodo.dispatchEvent(new w.Event('hidden.bs.modal'));
        },
    })}};
    w.Html5QrcodeSupportedFormats = Object.fromEntries(
        ['EAN_13', 'EAN_8', 'UPC_A', 'UPC_E', 'CODE_128', 'CODE_39', 'QR_CODE'].map((f, i) => [f, i])
    );
    let scan;
    let detenidos = 0;
    w.Html5Qrcode = class {
        async start(dispositivo, opciones, callback) {
            scan = callback;
            llamadas.push({dispositivo, opciones});
            return inicio(llamadas.length);
        }
        getRunningTrackCapabilities() { return {focusMode: enfoque}; }
        async applyVideoConstraints(valor) { llamadas.push({valor}); }
        async stop() { detenidos++; }
        clear() {}
    };
    w.addEventListener('smartstock:barcode-scanned', e => eventos.push(e.detail.codigo));
    campo.addEventListener('smartstock:product-barcode-scanned', e => eventos.push(e.detail.tipo));
    w.eval(fuente);
    await tick();
    botones.click();
    await tick();
    return {
        llamadas, campo, eventos, detenidos: () => detenidos,
        leer: (codigo, formato) => scan(codigo, {result: {format: {formatName: formato}}}),
        cerrar: () => w.bootstrap.Modal.getOrCreateInstance(modal).hide(),
    };
}

test('mantiene un marco horizontal en video vertical y activa el enfoque continuo disponible', async t => {
    const c = await pantalla(t, {enfoque: ['continuous']});
    const {opciones} = c.llamadas[0];
    for (const [ancho, alto] of [[320, 570], [320, 180], [500, 280], [320, 100]]) {
        const area = opciones.qrbox(ancho, alto);
        assert.ok(area.width > 240 && area.width < ancho);
        assert.ok(area.height < alto && area.height < area.width && area.height <= 145);
    }
    assert.equal(opciones.videoConstraints.facingMode.ideal, 'environment');
    assert.equal(c.llamadas[1].valor.advanced[0].focusMode, 'continuous');
});

test('acepta el primer EAN o UPC válido y descarta dígitos incorrectos', async t => {
    for (const [formato, valido, invalido] of [
        ['EAN_13', '4006381333931', '4006381333932'],
        ['EAN_8', '96385074', '96385075'],
        ['UPC_A', '036000291452', '036000291453'],
    ]) {
        const c = await pantalla(t);
        c.leer(invalido, formato);
        c.leer(invalido, formato);
        assert.equal(c.campo.value, '');
        c.leer(valido, formato);
        c.leer(valido, formato);
        assert.equal(c.campo.value, valido);
        assert.deepEqual(c.eventos, ['BARRA', valido]);
    }
});

test('QR conserva la confirmación y el tipo de código', async t => {
    const c = await pantalla(t);
    c.leer('https://example.com/p', 'QR_CODE');
    assert.equal(c.campo.value, '');
    c.leer('https://example.com/p', 'QR_CODE');
    assert.deepEqual(c.eventos, ['QR', 'https://example.com/p']);
});

test('vuelve a la configuración básica si la cámara rechaza las preferencias', async t => {
    const c = await pantalla(t, {inicio: async intento => {
        if (intento === 1) throw new Error('OverconstrainedError');
    }});
    assert.equal(c.llamadas.length, 2);
    assert.equal(c.llamadas[1].opciones.videoConstraints, undefined);
    c.leer('4006381333931', 'EAN_13');
    assert.equal(c.campo.value, '4006381333931');
});

test('cerrar durante la apertura libera la cámara y descarta una lectura tardía', async t => {
    let abrir;
    const pendiente = new Promise(resolve => { abrir = resolve; });
    const c = await pantalla(t, {inicio: () => pendiente});
    c.cerrar();
    c.leer('4006381333931', 'EAN_13');
    abrir();
    await tick();
    assert.equal(c.detenidos(), 1);
    assert.equal(c.campo.value, '');
    assert.deepEqual(c.eventos, []);
});
