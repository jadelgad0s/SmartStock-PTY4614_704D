const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const root = path.resolve(__dirname, '../..');
const html = readFileSync(path.join(root, 'templates/usuarios/listar.html'), 'utf8').replace(/{%[\s\S]*?%}/g, '');
const fuente = readFileSync(path.join(root, 'static/js/usuarios_api.js'), 'utf8');
const passwordJS = readFileSync(path.join(root, 'static/js/password_visibility.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
const rol = (id = 2) => ({id, nombre: id === 1 ? 'Administrador' : id === 3 ? 'Histórico' : 'Operador', codigo: id === 1 ? 'administrador' : 'operador', descripcion: 'Registra entradas y salidas.', activo: id !== 3});
const opciones = {success: true, data: {roles: [rol(1), rol(2), rol(3)], password_requisitos: ['Al menos 8 caracteres.', 'No usar contraseñas comunes.']}};
const persona = (id = 2, extra = {}) => ({id, nombre_completo: 'Persona ' + id + ' Prueba', nombres: 'Persona ' + id, apellidos: 'Prueba', email: 'persona' + id + '@example.com', telefono: '+56 9 1234 5678', rol: 2, rol_nombre: 'Operador', cuenta_protegida: false, activo: true, ultimo_login: '2026-10-28T02:30:00Z', fecha_creacion: '2026-10-20T14:00:00Z', ...extra});
const detalle = (id = 2, extra = {}) => persona(id, {rol: rol(), ...extra});
const paginaDatos = (count = 55, page = 1) => ({count, next: page < Math.ceil(count / 25) ? '/api/v1/usuarios/?page=' + (page + 1) : null, results: Array.from({length: Math.max(0, Math.min(25, count - (page - 1) * 25))}, (_, i) => persona((page - 1) * 25 + i + 2))});

async function pantalla(t) {
    const dom = new JSDOM(html, {url: 'http://localhost/usuarios/', runScripts: 'outside-only', pretendToBeVisual: true});
    t.after(() => dom.window.close());
    const w = dom.window, requests = [], modelos = new Map(), timers = new Map();
    let timer = 0;
    w.localStorage.setItem('access_token', 'test');
    w.localStorage.setItem('usuario', JSON.stringify({id: 1, rol_nombre: 'Administrador', nombre_completo: 'Admin Prueba'}));
    w.matchMedia = () => ({matches: false});
    w.HTMLElement.prototype.scrollIntoView = () => {};
    w.alert = w.confirm = () => { throw new Error('No deben usarse confirmaciones nativas'); };
    w.bootstrap = {Modal: {getOrCreateInstance(elemento) {
        if (!modelos.has(elemento)) modelos.set(elemento, {
            show() {
                if (!elemento.dispatchEvent(new w.Event('show.bs.modal', {cancelable: true}))) return;
                elemento.classList.add('show'); elemento.dispatchEvent(new w.Event('shown.bs.modal'));
            },
            hide() {
                if (!elemento.dispatchEvent(new w.Event('hide.bs.modal', {cancelable: true}))) return;
                elemento.classList.remove('show'); elemento.dispatchEvent(new w.Event('hidden.bs.modal'));
            },
        });
        return modelos.get(elemento);
    }}};
    w.setTimeout = (fn, delay) => { timers.set(++timer, {fn, delay}); return timer; };
    w.clearTimeout = id => timers.delete(id);
    w.fetch = (url, options) => new Promise((resolve, reject) => requests.push({url: new URL(url, w.location.href), options, resolve, reject}));
    const avisos = []; w.addEventListener('smartstock:notifications-changed', () => avisos.push(true));
    w.eval(passwordJS); w.eval(fuente); await tick();
    const el = id => w.document.getElementById(id);
    const campo = (id, value, evento = 'input') => { el(id).value = value; el(id).dispatchEvent(new w.Event(evento)); };
    const responder = async (index, data, status = 200) => { requests[index].resolve({ok: status >= 200 && status < 300, status, json: async () => data}); await tick(); };
    const iniciar = async (datos = paginaDatos()) => { await responder(1, opciones); await responder(0, datos); };
    const debounce = async () => { [...timers.entries()].filter(([, x]) => x.delay === 300).forEach(([id, x]) => { timers.delete(id); x.fn(); }); await tick(); };
    const enviar = id => el(id).dispatchEvent(new w.Event('submit', {cancelable: true}));
    const abrirCrear = () => modelos.get(el('modalNuevoUsuario')).show();
    const completarCrear = () => {
        abrirCrear(); campo('inputNombres', 'Nueva'); campo('inputApellidos', 'Persona'); campo('inputEmail', 'nueva@example.com'); campo('inputRol', '2', 'change');
        campo('inputPassword', 'ClaveFuerte-82!'); campo('inputPasswordConfirmacion', 'ClaveFuerte-82!');
    };
    const accion = (tipo, id = 2) => el('listaUsuarios').querySelector('button[data-accion="' + tipo + '"][data-id="' + id + '"]').click();
    return {w, el, avisos, requests, modelos, campo, responder, iniciar, debounce, enviar, abrirCrear, completarCrear, accion};
}

test('usuarios carga solo la página visible y conserva búsqueda, rol, estado y orden', async t => {
    const c = await pantalla(t); await c.iniciar();
    assert.equal(c.requests.length, 2);
    assert.equal(c.el('listaUsuarios').querySelectorAll('.ss-user-row').length, 25);
    c.campo('buscarUsuarios', 'Persona', 'input'); c.campo('rolUsuarios', '2', 'change'); c.campo('estadoUsuarios', 'false', 'change'); c.campo('ordenUsuarios', '-nombres,-apellidos,-id', 'change');
    await c.responder(c.requests.length - 1, paginaDatos());
    c.el('paginacionUsuarios').querySelector('button[data-page="2"]').click();
    const p = c.requests.at(-1).url.searchParams;
    for (const [k, v] of Object.entries({page: '2', search: 'Persona', rol: '2', activo: 'false', ordering: '-nombres,-apellidos,-id'})) assert.equal(p.get(k), v);
    await c.responder(c.requests.length - 1, paginaDatos(55, 2));
    assert.match(c.el('resumenUsuarios').textContent, /26–50 de 55 usuarios/);
});

test('búsqueda invalida inmediatamente respuestas viejas durante el debounce', async t => {
    const c = await pantalla(t); await c.iniciar();
    c.el('paginacionUsuarios').querySelector('button[data-page="2"]').click(); const vieja = c.requests.length - 1;
    c.campo('buscarUsuarios', 'Nueva', 'input');
    assert.equal(c.el('paginacionUsuarios').children.length, 0);
    await c.responder(vieja, paginaDatos(55, 2)); assert.match(c.el('resumenUsuarios').textContent, /Cargando/);
    await c.debounce(); assert.equal(c.requests.at(-1).url.searchParams.get('page'), '1');
    await c.responder(c.requests.length - 1, paginaDatos(0)); assert.equal(c.el('resumenUsuarios').textContent, '0 usuarios');
});

test('recupera una página desaparecida mediante last sin reintentos infinitos', async t => {
    const c = await pantalla(t); await c.iniciar();
    c.el('paginacionUsuarios').querySelector('button[data-page="3"]').click(); await c.responder(c.requests.length - 1, {}, 404);
    assert.equal(c.requests.at(-1).url.searchParams.get('page'), 'last');
    const cantidad = c.requests.length; await c.responder(cantidad - 1, {}, 404);
    assert.equal(c.requests.length, cantidad); assert.match(c.el('resumenUsuarios').textContent, /Error/);
});

test('nombres y correos se presentan como texto y las cuentas protegidas explican sus acciones', async t => {
    const c = await pantalla(t);
    await c.iniciar({count: 3, results: [persona(2, {nombre_completo: '<img src=x onerror=alert(1)>', email: '<script>x</script>'}), persona(1, {cuenta_protegida: true}), persona(3, {cuenta_protegida: true})]});
    assert.equal(c.el('listaUsuarios').querySelector('img'), null); assert.equal(c.el('listaUsuarios').querySelector('script'), null);
    assert.match(c.el('listaUsuarios').textContent, /Tu cuenta/); assert.match(c.el('listaUsuarios').textContent, /Cuenta protegida/);
    assert.equal(c.el('listaUsuarios').querySelector('button[data-accion="eliminar"][data-id="3"]'), null);
    assert.equal(c.el('listaUsuarios').querySelector('button[data-accion="desactivar"][data-id="1"]'), null);
});

test('detalle muestra teléfono y fechas de Chile y descarta una respuesta tras cerrar', async t => {
    const c = await pantalla(t); await c.iniciar(); c.accion('detalle');
    await c.responder(c.requests.length - 1, detalle());
    assert.equal(c.el('detalleUsuarioTelefono').textContent, '+56 9 1234 5678');
    assert.equal(c.el('detalleUsuarioUltimoLogin').textContent, '27/10/2026 23:30:00');
    c.modelos.get(c.el('modalDetalleUsuario')).hide();
    c.accion('detalle', 3); const vieja = c.requests.length - 1; c.modelos.get(c.el('modalDetalleUsuario')).hide();
    await c.responder(vieja, {data: detalle(3)});
    assert.equal(c.el('datosDetalleUsuario').classList.contains('d-none'), true);
});

test('crear requiere una confirmación independiente y permite mostrar y ocultar la contraseña', async t => {
    const c = await pantalla(t); await c.iniciar(); c.completarCrear();
    c.el('modalNuevoUsuario').querySelector('[data-password-toggle="inputPassword"]').click(); assert.equal(c.el('inputPassword').type, 'text');
    c.campo('inputPasswordConfirmacion', 'Otra clave'); const cantidad = c.requests.length; c.enviar('formCrearUsuario');
    assert.equal(c.requests.length, cantidad); assert.match(c.el('inputPasswordConfirmacionError').textContent, /coincidir/);
    assert.equal(c.el('inputNombres').value, 'Nueva');
    c.campo('inputPasswordConfirmacion', 'ClaveFuerte-82!'); c.enviar('formCrearUsuario');
    const payload = JSON.parse(c.requests.at(-1).options.body); assert.equal(payload.password, 'ClaveFuerte-82!'); assert.equal(payload.password_confirmacion, 'ClaveFuerte-82!');
});

test('errores por campo conservan el formulario y un reintento mantiene los valores', async t => {
    const c = await pantalla(t); await c.iniciar(); c.completarCrear(); c.enviar('formCrearUsuario');
    await c.responder(c.requests.length - 1, {mensaje: 'Datos inválidos.', errores: {email: ['Ya existe este correo.']}}, 400);
    assert.equal(c.el('inputEmail').getAttribute('aria-invalid'), 'true'); assert.match(c.el('inputEmailError').textContent, /Ya existe/);
    assert.equal(c.el('inputPassword').value, 'ClaveFuerte-82!'); assert.equal(c.el('guardarNuevoUsuario').disabled, false);
    assert.ok(c.el('modalNuevoUsuario').classList.contains('show'));
    c.campo('inputEmail', 'otra@example.com'); c.enviar('formCrearUsuario');
    assert.equal(JSON.parse(c.requests.at(-1).options.body).email, 'otra@example.com');
});

test('doble envío no duplica creación, impide cerrar pendiente y bloquea clic tras guardar', async t => {
    const c = await pantalla(t); await c.iniciar(); c.completarCrear(); const antes = c.requests.length;
    c.enviar('formCrearUsuario'); c.enviar('formCrearUsuario'); assert.equal(c.requests.length, antes + 1);
    c.modelos.get(c.el('modalNuevoUsuario')).hide(); assert.ok(c.el('modalNuevoUsuario').classList.contains('show'));
    await c.responder(antes, {success: true, data: detalle(99, {nombre_completo: 'Nueva Persona'})}, 201);
    const despues = c.requests.length; c.enviar('formCrearUsuario'); assert.equal(c.requests.length, despues);
    assert.equal(c.el('modalNuevoUsuario').classList.contains('show'), false); assert.equal(c.el('avisoResultadoUsuarios'), null); assert.equal(c.avisos.length, 1);
    assert.equal(c.requests.at(-1).url.searchParams.get('page'), '1');
});

test('edición obtiene datos recientes y omite el rol de una cuenta protegida', async t => {
    const c = await pantalla(t); await c.iniciar({count: 1, results: [persona(1, {cuenta_protegida: true})]}); c.accion('editar', 1);
    await c.responder(c.requests.length - 1, detalle(1, {rol: rol(1), cuenta_protegida: true}));
    assert.equal(c.el('editRol').disabled, true); assert.equal(c.el('editRolProtegido').classList.contains('d-none'), false);
    c.campo('editNombres', 'Nombre actualizado'); c.el('editRol').value = '2'; c.enviar('formEditarUsuario');
    const payload = JSON.parse(c.requests.at(-1).options.body); assert.equal(Object.hasOwn(payload, 'rol_id'), false);
    await c.responder(c.requests.length - 1, {data: detalle(1, {nombre_completo: 'Nombre actualizado Prueba', nombres: 'Nombre actualizado', cuenta_protegida: true})});
    assert.match(c.el('user-name-sidebar').textContent, /Nombre actualizado/);
});

test('usuario con rol histórico puede editar teléfono sin reenviar un rol inactivo', async t => {
    const c = await pantalla(t); await c.iniciar(); c.accion('editar');
    await c.responder(c.requests.length - 1, {data: detalle(2, {rol: rol(3)})});
    assert.equal(c.el('editRol').value, '3'); c.campo('editTelefono', '+56 9 0000 9999'); c.enviar('formEditarUsuario');
    const payload = JSON.parse(c.requests.at(-1).options.body); assert.equal(Object.hasOwn(payload, 'rol_id'), false); assert.equal(payload.telefono, '+56 9 0000 9999');
});

test('confirmación identifica al usuario y evita desactivaciones duplicadas', async t => {
    const c = await pantalla(t); await c.iniciar(); c.accion('desactivar');
    await c.responder(c.requests.length - 1, {data: detalle()});
    assert.equal(c.el('nombreAccionUsuario').textContent, 'Persona 2 Prueba'); assert.equal(c.el('correoAccionUsuario').textContent, 'persona2@example.com');
    const antes = c.requests.length; c.enviar('formAccionUsuario'); c.enviar('formAccionUsuario'); assert.equal(c.requests.length, antes + 1);
    assert.equal(c.requests.at(-1).options.method, 'DELETE'); assert.equal(c.requests.at(-1).url.pathname, '/api/v1/usuarios/2/');
    c.modelos.get(c.el('modalAccionUsuario')).hide(); assert.ok(c.el('modalAccionUsuario').classList.contains('show'));
    await c.responder(antes, {success: true, mensaje: 'Desactivado.'}); const despues = c.requests.length; c.enviar('formAccionUsuario'); assert.equal(c.requests.length, despues);
    assert.equal(c.el('avisoResultadoUsuarios'), null); assert.equal(c.avisos.length, 1);
});

test('reactivación usa su propia confirmación y el endpoint activar', async t => {
    const c = await pantalla(t); await c.iniciar({count: 1, results: [persona(2, {activo: false})]}); c.accion('reactivar');
    await c.responder(c.requests.length - 1, {data: detalle(2, {activo: false})}); c.enviar('formAccionUsuario');
    assert.equal(c.requests.at(-1).options.method, 'POST'); assert.equal(c.requests.at(-1).url.pathname, '/api/v1/usuarios/2/activar/');
});

test('eliminación queda en Más acciones y un rechazo por historial conserva el modal', async t => {
    const c = await pantalla(t); await c.iniciar();
    const boton = c.el('listaUsuarios').querySelector('button[data-accion="eliminar"]'); assert.equal(boton.closest('details').open, false);
    boton.closest('details').open = true; boton.click(); await c.responder(c.requests.length - 1, {data: detalle()}); c.enviar('formAccionUsuario');
    assert.equal(c.requests.at(-1).url.pathname, '/api/v1/usuarios/2/eliminar-definitivamente/');
    await c.responder(c.requests.length - 1, {mensaje: 'El usuario tiene historial asociado; solo puedes desactivarlo.'}, 409);
    assert.ok(c.el('modalAccionUsuario').classList.contains('show')); assert.match(c.el('errorAccionUsuario').textContent, /historial/); assert.equal(c.el('confirmarAccionUsuario').disabled, false);
});

test('revalidar una cuenta recién protegida impide ofrecer confirmación destructiva', async t => {
    const c = await pantalla(t); await c.iniciar(); c.accion('desactivar');
    await c.responder(c.requests.length - 1, {data: detalle(2, {cuenta_protegida: true, rol: rol(1)})});
    assert.equal(c.el('confirmarAccionUsuario').disabled, true); const antes = c.requests.length; c.enviar('formAccionUsuario'); assert.equal(c.requests.length, antes);
    assert.match(c.el('errorAccionUsuario').textContent, /protegida/);
});

test('carga de opciones fallida se reintenta y solo ofrece roles activos al crear', async t => {
    const c = await pantalla(t); await c.responder(0, paginaDatos()); await c.responder(1, {}, 500);
    c.abrirCrear(); assert.equal(c.el('guardarNuevoUsuario').disabled, true);
    c.modelos.get(c.el('modalNuevoUsuario')).hide(); c.el('reintentarOpcionesUsuarios').click(); await c.responder(c.requests.length - 1, opciones);
    assert.equal(c.el('guardarNuevoUsuario').disabled, false); assert.ok([...c.el('rolUsuarios').options].some(o => o.value === '3'));
    assert.equal([...c.el('inputRol').options].some(o => o.value === '3'), false);
    c.campo('inputRol', '2', 'change'); assert.match(c.el('inputRolAyuda').textContent, /entradas y salidas/);
});

test('edición cerrada ignora su respuesta y conserva los datos de otra cuenta', async t => {
    const c = await pantalla(t); await c.iniciar(); c.accion('editar'); const vieja = c.requests.length - 1;
    c.modelos.get(c.el('modalEditarUsuario')).hide(); c.accion('editar', 3);
    await c.responder(c.requests.length - 1, {data: detalle(3)}); await c.responder(vieja, {data: detalle(2)});
    assert.equal(c.el('editUserId').value, '3'); assert.match(c.el('editCorreo').textContent, /persona3/);
});

test('dos consultas con JWT vencido comparten renovación y reintentan con el token nuevo', async t => {
    const c = await pantalla(t); c.w.localStorage.setItem('refresh_token', 'refresh-vigente');
    await c.responder(0, {}, 401); await c.responder(1, {}, 401);
    assert.equal(c.requests.filter(r => r.url.pathname === '/api/v1/auth/refresh/').length, 1);
    await c.responder(2, {access: 'token-nuevo', refresh: 'refresh-nuevo'});
    assert.equal(c.requests.length, 5);
    for (const [i, request] of c.requests.entries()) if (i >= 3) {
        assert.equal(request.options.headers.Authorization, 'Bearer token-nuevo');
        await c.responder(i, request.url.pathname.endsWith('/opciones/') ? opciones : paginaDatos());
    }
    assert.equal(c.w.localStorage.getItem('access_token'), 'token-nuevo'); assert.equal(c.w.localStorage.getItem('refresh_token'), 'refresh-nuevo');
    assert.equal(c.el('listaUsuarios').querySelectorAll('.ss-user-row').length, 25);
});

test('fallo de red al guardar conserva datos, explica incertidumbre y refresca la lista', async t => {
    const c = await pantalla(t); await c.iniciar(); c.completarCrear(); c.enviar('formCrearUsuario');
    c.requests.at(-1).reject(new Error('Red')); await tick();
    assert.match(c.el('errorCrearUsuario').textContent, /Revisa la lista/); assert.equal(c.el('inputEmail').value, 'nueva@example.com');
    assert.equal(c.requests.at(-1).url.pathname, '/api/v1/usuarios/'); assert.equal(c.requests.at(-1).options.method, undefined);
});
