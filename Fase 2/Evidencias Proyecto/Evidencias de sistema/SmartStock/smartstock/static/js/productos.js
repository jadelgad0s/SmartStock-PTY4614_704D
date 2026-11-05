/* Catálogo paginado: edición completa, códigos independientes y stock por bodega. */
document.addEventListener('DOMContentLoaded', async () => {
    'use strict';
    if (window.SmartStockNavegacion && !await window.SmartStockNavegacion.lista) return;
    let token = localStorage.getItem('access_token');
    if (!token) { window.location.replace('/'); return; }
    let sesion;
    try { sesion = JSON.parse(localStorage.getItem('usuario') || '{}') || {}; } catch (_) { sesion = {}; }
    const el = id => document.getElementById(id);
    const nodo = (tag, clase, texto) => {
        const n = document.createElement(tag); if (clase) n.className = clase;
        if (texto !== undefined) n.textContent = String(texto ?? ''); return n;
    };
    const aviso = (id, texto) => { el(id).textContent = texto || ''; el(id).hidden = !texto; };
    const mensaje = v => Array.isArray(v) ? v.map(mensaje).join(' ') : v && typeof v === 'object' ? Object.values(v).map(mensaje).join(' ') : String(v || '');
    const precio = v => {
        const n = Number(v);
        return Number.isFinite(n) ? new Intl.NumberFormat('es-CL', {style: 'currency', currency: 'CLP', minimumFractionDigits: Number.isInteger(n) ? 0 : 2, maximumFractionDigits: 2}).format(n) : 'Precio no disponible';
    };
    function fecha(v) {
        if (!v || Number.isNaN(new Date(v).getTime())) return '—';
        const p = Object.fromEntries(new Intl.DateTimeFormat('es-CL', {timeZone: 'America/Santiago', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'}).formatToParts(new Date(v)).map(x => [x.type, x.value]));
        return p.day + '/' + p.month + '/' + p.year + ' ' + p.hour + ':' + p.minute;
    }
    el('user-name-sidebar').textContent = sesion.nombre_completo || 'Usuario';
    el('user-role-sidebar').textContent = sesion.rol_nombre || 'Sin rol';
    el('user-avatar').src = 'https://ui-avatars.com/api/?name=' + encodeURIComponent(sesion.nombre_completo || 'Usuario') + '&background=0f766e&color=fff';
    let renovacion = null;
    async function renovar() {
        if (!renovacion) renovacion = (async () => {
            const refresh = localStorage.getItem('refresh_token'); if (!refresh) return false;
            const res = await fetch('/api/v1/auth/refresh/', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({refresh})});
            if (res.status >= 500) throw new Error('No se pudo renovar la sesión. Vuelve a intentarlo.');
            if (!res.ok) return false;
            const json = await res.json(), d = json.data || json;
            if (!d.access) return false;
            token = d.access; localStorage.setItem('access_token', token);
            if (d.refresh) localStorage.setItem('refresh_token', d.refresh);
            return true;
        })().finally(() => { renovacion = null; });
        return renovacion;
    }
    async function api(url, options = {}) {
        const escritura = options.method && options.method !== 'GET', usado = token;
        const enviar = () => fetch(url, {...options, headers: {...(options.body ? {'Content-Type': 'application/json'} : {}), ...options.headers, Authorization: 'Bearer ' + token}, cache: 'no-store'});
        let res;
        try {
            res = await enviar();
            if (res.status === 401) {
                if (token !== usado || await renovar()) res = await enviar();
                else { window.smartstockClearSession(); window.location.replace('/'); throw new Error('La sesión expiró. Vuelve a iniciar sesión.'); }
            }
        } catch (e) {
            const error = new Error(escritura ? 'No pudimos confirmar el resultado. Revisa el catálogo antes de volver a intentarlo.' : e instanceof TypeError ? 'No se pudo conectar con el servidor. Vuelve a intentarlo.' : e.message || 'No se pudo conectar con el servidor.');
            error.incierto = Boolean(escritura); throw error;
        }
        let json;
        try { json = await res.json(); } catch (_) { const error = new Error(escritura ? 'No pudimos confirmar el resultado. Revisa el catálogo antes de volver a intentarlo.' : 'No se pudo leer la respuesta del servidor.'); error.incierto = Boolean(escritura); throw error; }
        if (!res.ok || !json || json.success === false) {
            const error = new Error(json?.mensaje || json?.detail || (res.status === 403 ? 'No tienes permiso para realizar esta operación.' : 'No se pudo completar la operación.'));
            error.status = res.status; error.datos = json; throw error;
        }
        return json;
    }
    let permisos = {}, bodegas = [], predeterminada = '', opcionesListas = false, opcionesPendientes = false;
    function aplicarPermisos(p = {}) {
        permisos = p;
        el('btnNuevoProducto').hidden = p.crear !== true;
        [['menu-auditoria', 'auditoria'], ['menu-usuarios', 'usuarios'], ['menu-config', 'configuracion']].forEach(([id, clave]) => { el(id).hidden = p[clave] !== true; });
        el('menu-sistema-title').hidden = !p.usuarios && !p.configuracion;
    }
    const inicial = new URLSearchParams(window.location.search);
    let productoInicial = /^[1-9]\d*$/.test(inicial.get('producto') || '') ? inicial.get('producto') : null;
    el('buscadorProductos').value = (inicial.get('q') || '').slice(0, 200);
    const ordenes = [...el('ordenarProductos').options].map(o => o.value);
    if (ordenes.includes(inicial.get('ordering'))) el('ordenarProductos').value = inicial.get('ordering');
    if (['true', 'false'].includes(inicial.get('activo'))) el('estadoProductos').value = inicial.get('activo');
    if (['suficiente', 'bajo', 'agotado'].includes(inicial.get('disponibilidad'))) el('stockProductos').value = inicial.get('disponibilidad');
    const tabla = el('listaProductos'), paginadores = [el('paginacionProductosSuperior'), el('paginacionProductos')];
    const TAMANO = 25; let pagina = 1, total = 0, versionLista = 0, timerBusqueda;
    function mensajeTabla(texto) { const tr = nodo('tr'), td = nodo('td', 'ss-product-empty text-center text-muted py-4', texto); td.colSpan = 6; tr.append(td); tabla.replaceChildren(tr); }
    function prepararLista() {
        paginadores.forEach(n => n.replaceChildren()); tabla.setAttribute('aria-busy', 'true');
        mensajeTabla('Cargando productos...'); el('totalProductos').textContent = 'Cargando productos...'; el('resumenPaginacionProductos').textContent = ''; el('reintentarProductos').hidden = true;
    }
    function alcance() {
        const b = bodegas.find(b => String(b.id) === el('bodegaProductos').value);
        el('alcanceStockProductos').textContent = b ? 'Stock de ' + b.nombre + ' · Bajo: entre 1 unidad y el mínimo configurado. Mínimo 0: aviso de stock bajo desactivado. Sin registro: 0 unidades.' + (permisos.configurar_minimo ? ' Pulsa «Mínimo» para configurarlo.' : '') : 'Sin bodegas activas. Puedes consultar los datos del catálogo; la disponibilidad no está disponible.';
        el('stockProductos').disabled = !b;
        return b;
    }
    function guardarConsulta() {
        const p = new URLSearchParams();
        const campos = {q: el('buscadorProductos').value.trim(), bodega: el('bodegaProductos').value, activo: el('estadoProductos').value, disponibilidad: el('stockProductos').value};
        Object.entries(campos).forEach(([k, v]) => { if (v) p.set(k, v); });
        if (el('ordenarProductos').value !== 'nombre,id') p.set('ordering', el('ordenarProductos').value);
        window.history.replaceState(null, '', window.location.pathname + (p.size ? '?' + p : ''));
        const cantidad = [el('estadoProductos').value, el('stockProductos').value, el('bodegaProductos').value !== predeterminada, el('ordenarProductos').value !== 'nombre,id'].filter(Boolean).length;
        el('mostrarFiltrosProductos').textContent = 'Filtros' + (cantidad ? ' (' + cantidad + ')' : '');
    }
    function boton(texto, accion, p, clase) {
        const b = nodo('button', clase, texto); b.type = 'button'; b.dataset.accion = accion; b.dataset.id = String(p.id);
        b.setAttribute('aria-label', texto + ' — ' + p.nombre + ', SKU ' + p.sku); return b;
    }
    function badgeEstado(activo) { return nodo('span', 'ss-product-badge ' + (activo ? 'ss-product-active' : 'ss-product-inactive'), activo ? 'Activo' : 'Inactivo'); }
    const nombresStock = {suficiente: 'Stock suficiente', bajo: 'Stock bajo', agotado: 'Agotado'};
    function controlMinimo(p, bodega, cantidad) {
        const b = boton('Mínimo: ' + Number(cantidad || 0).toLocaleString('es-CL'), 'minimo', p, 'ss-product-min-link');
        b.dataset.bodega = String(bodega); b.setAttribute('aria-label', 'Configurar mínimo de ' + p.nombre + ', SKU ' + p.sku);
        return b;
    }
    function filaProducto(p) {
        const fila = nodo('tr', 'ss-product-row');
        const sku = nodo('td', 'ss-product-sku', p.sku), nombre = nodo('td', 'ss-product-name');
        const header = nodo('div', 'ss-product-header'), info = nodo('div', 'ss-product-header-info');
        const titulo = nodo('strong', 'ss-product-title', p.nombre); titulo.title = p.nombre; info.append(titulo);
        const meta = nodo('div', 'ss-product-meta'); meta.append(nodo('span', 'ss-product-mobile-sku', 'SKU: ' + p.sku)); const estadoMovil = nodo('span', 'ss-product-mobile-status'); estadoMovil.append(badgeEstado(p.activo)); meta.append(estadoMovil);
        meta.append(boton('Ver detalle', 'detalle', p, 'ss-product-detail-link'));
        if (el('bodegaProductos').value) {
            const ubicaciones = nodo('a', 'ss-product-detail-link', 'Ubicaciones');
            ubicaciones.href = '/ubicaciones/?' + new URLSearchParams({bodega: el('bodegaProductos').value, producto: p.id});
            ubicaciones.setAttribute('aria-label', 'Ver ubicaciones de ' + p.nombre);
            meta.append(ubicaciones);
        }
        info.append(meta); header.append(info); nombre.append(header);
        const stock = nodo('td', 'ss-product-stock');
        if (el('bodegaProductos').value) {
            stock.append(nodo('span', 'ss-product-stock-value ss-stock-' + p.estado_stock, Number(p.stock_actual).toLocaleString('es-CL') + ' unid.'));
            const minimo = nodo('span', 'ss-product-subtle', (nombresStock[p.estado_stock] || 'Stock sin clasificar') + ' · ');
            if (permisos.configurar_minimo) minimo.append(controlMinimo(p, el('bodegaProductos').value, p.stock_minimo));
            else minimo.append(document.createTextNode('Mínimo: ' + Number(p.stock_minimo || 0).toLocaleString('es-CL')));
            stock.append(minimo);
        } else stock.append(nodo('span', 'ss-product-subtle', 'Sin bodega activa'));
        const valor = nodo('td', 'ss-product-price'); valor.append(nodo('span', 'ss-product-price-value', precio(p.precio_referencia)));
        const estado = nodo('td', 'ss-product-status'); estado.append(badgeEstado(p.activo));
        const acciones = nodo('td', 'ss-product-action-cell'), grupo = nodo('div', 'ss-product-actions');
        if (permisos.editar) grupo.append(boton('Editar', 'editar', p, 'btn btn-sm btn-outline-primary btn-editar'));
        if (p.activo && permisos.desactivar) grupo.append(boton('Desactivar', 'desactivar', p, 'btn btn-sm btn-outline-warning btn-borrar'));
        if (!p.activo && permisos.reactivar) grupo.append(boton('Reactivar', 'reactivar', p, 'btn btn-sm btn-outline-success btn-activar'));
        if (permisos.eliminar_definitivamente) {
            const mas = nodo('details', 'ss-product-more'), summary = nodo('summary', 'btn btn-sm btn-outline-secondary', 'Más acciones');
            const icono = nodo('i', 'fa-solid fa-chevron-down ms-2'); icono.setAttribute('aria-hidden', 'true'); summary.append(icono);
            mas.append(summary, boton('Eliminar definitivamente', 'eliminar_definitivamente', p, 'btn btn-sm btn-outline-danger btn-eliminar-definitivo')); grupo.append(mas);
        }
        if (!grupo.children.length) grupo.append(nodo('span', 'ss-product-subtle', 'Solo lectura'));
        acciones.append(grupo); fila.append(sku, nombre, stock, valor, estado, acciones); return fila;
    }
    function paginar(paginas) {
        paginadores.forEach(nav => {
            nav.replaceChildren(); if (paginas <= 1) return;
            const ul = nodo('ul', 'pagination');
            const agregar = (texto, n, disabled = false, actual = false) => {
                const li = nodo('li', 'page-item' + (actual ? ' active' : '') + (disabled ? ' disabled' : ''));
                const b = nodo('button', 'page-link', texto); b.type = 'button'; b.disabled = disabled || actual; b.dataset.page = String(n);
                b.setAttribute('aria-label', texto === 'Anterior' ? 'Página anterior' : texto === 'Siguiente' ? 'Página siguiente' : 'Ir a página ' + n);
                if (actual) b.setAttribute('aria-current', 'page'); li.append(b); ul.append(li);
            };
            agregar('Anterior', pagina - 1, pagina === 1);
            const numeros = new Set([1, paginas]);
            for (let n = Math.max(1, pagina - 1); n <= Math.min(paginas, pagina + 1); n++) numeros.add(n);
            if (pagina <= 3) [2, 3].forEach(n => { if (n <= paginas) numeros.add(n); });
            if (pagina >= paginas - 2) [paginas - 2, paginas - 1].forEach(n => { if (n > 0) numeros.add(n); });
            let previo = 0;
            [...numeros].sort((a, b) => a - b).forEach(n => { if (previo && n > previo + 1) { const li = nodo('li'); li.append(nodo('span', 'ss-page-ellipsis', '…')); ul.append(li); } agregar(String(n), n, false, n === pagina); previo = n; });
            agregar('Siguiente', pagina + 1, pagina === paginas); nav.append(ul);
        });
    }
    async function cargarProductos({ultimaPagina = false, enfocarResumen = false} = {}) {
        clearTimeout(timerBusqueda); if (!opcionesListas) return;
        const v = ++versionLista; prepararLista(); guardarConsulta(); alcance();
        const p = new URLSearchParams({page: ultimaPagina ? 'last' : String(pagina), ordering: el('ordenarProductos').value});
        const filtros = {search: el('buscadorProductos').value.trim(), bodega: el('bodegaProductos').value, activo: el('estadoProductos').value, disponibilidad: el('stockProductos').value};
        Object.entries(filtros).forEach(([k, valor]) => { if (valor) p.set(k, valor); });
        aviso('avisoCatalogo', '');
        try {
            const json = await api('/api/v1/productos/?' + p);
            if (v !== versionLista) return;
            if (!Array.isArray(json.results) || !Number.isInteger(json.count) || json.count < 0) throw new Error('El listado de productos tiene un formato inválido.');
            total = json.count; const paginas = Math.ceil(total / TAMANO); if (ultimaPagina) pagina = Math.max(1, paginas);
            const primero = json.results.length ? (pagina - 1) * TAMANO + 1 : 0;
            el('totalProductos').textContent = total + (el('buscadorProductos').value.trim() || el('estadoProductos').value || el('stockProductos').value ? ' resultados' : ' productos en total');
            el('resumenPaginacionProductos').textContent = total ? 'Mostrando ' + primero + '–' + (primero + json.results.length - 1) + ' de ' + total + ' productos' : 'No hay productos para mostrar.';
            if (json.results.length) tabla.replaceChildren(...json.results.map(filaProducto));
            else mensajeTabla(el('stockProductos').value === 'bajo' ? 'No hay productos con stock bajo para estos filtros. Esta categoría requiere existencias positivas y un mínimo mayor que 0. Selecciona «Todas» en disponibilidad para revisar los mínimos.' : 'No se encontraron productos con estos filtros.');
            paginar(paginas);
        } catch (error) {
            if (v !== versionLista) return;
            if (error.status === 404 && pagina > 1 && !ultimaPagina) return cargarProductos({ultimaPagina: true, enfocarResumen});
            mensajeTabla('No se pudieron cargar los productos.'); el('resumenPaginacionProductos').textContent = 'No se pudieron cargar los productos.'; el('totalProductos').textContent = 'Error de carga';
            aviso('avisoCatalogo', error.message); el('reintentarProductos').hidden = false;
            if (error.status === 403) aplicarPermisos();
        } finally {
            if (v === versionLista) { tabla.setAttribute('aria-busy', 'false'); if (enfocarResumen && document.activeElement === document.body) el('totalProductos').focus({preventScroll: true}); }
        }
    }
    paginadores.forEach(nav => nav.addEventListener('click', e => {
        const b = e.target.closest('button[data-page]'); if (!b || b.disabled) return;
        const n = Number(b.dataset.page); if (!Number.isInteger(n) || n < 1 || n > Math.ceil(total / TAMANO)) return;
        pagina = n; cargarProductos({enfocarResumen: e.detail === 0}); document.querySelector('.ss-products-toolbar').scrollIntoView({block: 'start', behavior: 'auto'});
    }));
    el('buscadorProductos').addEventListener('input', () => { versionLista++; pagina = 1; clearTimeout(timerBusqueda); if (!opcionesListas && !opcionesPendientes) return; prepararLista(); timerBusqueda = setTimeout(() => cargarProductos(), 300); });
    ['estadoProductos', 'stockProductos', 'bodegaProductos', 'ordenarProductos'].forEach(id => el(id).addEventListener('change', () => { pagina = 1; cargarProductos(); }));
    el('limpiarFiltrosProductos').addEventListener('click', () => { el('buscadorProductos').value = ''; el('estadoProductos').value = ''; el('stockProductos').value = ''; el('ordenarProductos').value = 'nombre,id'; el('bodegaProductos').value = predeterminada; pagina = 1; cargarProductos(); });
    el('mostrarFiltrosProductos').addEventListener('click', () => { const abierto = el('mostrarFiltrosProductos').getAttribute('aria-expanded') !== 'true'; el('mostrarFiltrosProductos').setAttribute('aria-expanded', String(abierto)); el('filtrosProductos').classList.toggle('ss-filters-open', abierto); });
    el('reintentarProductos').addEventListener('click', () => opcionesListas ? cargarProductos() : cargarOpciones());
    const volverArriba = el('ssVolverArriba');
    function actualizarArriba() { volverArriba.hidden = window.scrollY < 500; }
    window.addEventListener('scroll', actualizarArriba, {passive: true});
    volverArriba.addEventListener('click', () => window.scrollTo({top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'})); actualizarArriba();
    async function cargarOpciones() {
        if (opcionesPendientes) return; opcionesPendientes = true; aviso('avisoCatalogo', ''); el('reintentarOpcionesProductos').hidden = true;
        try {
            const json = await api('/api/v1/productos/opciones/'), d = json.data;
            if (!d || !Array.isArray(d.bodegas) || !d.permisos) throw new Error('No se pudieron leer las opciones del catálogo.');
            bodegas = d.bodegas; predeterminada = d.bodega_predeterminada ? String(d.bodega_predeterminada) : '';
            const previa = el('bodegaProductos').value || inicial.get('bodega') || predeterminada;
            el('bodegaProductos').replaceChildren(...bodegas.map(b => new Option(b.etiqueta || b.nombre, String(b.id))));
            if (!bodegas.length) el('bodegaProductos').append(new Option('Sin bodegas activas', ''));
            el('bodegaProductos').value = bodegas.some(b => String(b.id) === previa) ? previa : predeterminada;
            el('bodegaProductos').disabled = !bodegas.length; if (!bodegas.length) el('stockProductos').value = '';
            aplicarPermisos(d.permisos); opcionesListas = true; alcance(); cargarProductos();
            if (productoInicial) {
                abrirDetalle(productoInicial);
                productoInicial = null;
            }
        } catch (error) {
            opcionesListas = false; aplicarPermisos(); aviso('avisoCatalogo', error.message); el('reintentarOpcionesProductos').hidden = false;
            mensajeTabla('No se pudo preparar el catálogo. Reintenta la carga de opciones.'); tabla.setAttribute('aria-busy', 'false'); el('totalProductos').textContent = 'Error de carga';
        } finally { opcionesPendientes = false; }
    }
    el('reintentarOpcionesProductos').addEventListener('click', cargarOpciones);
    function productoCompleto(json) {
        const d = json.data || json;
        if (!d || !Number.isInteger(d.id) || typeof d.nombre !== 'string' || typeof d.sku !== 'string' || !Array.isArray(d.codigos_barra)) throw new Error('No se pudo leer el detalle completo del producto.');
        return d;
    }
    const estadosForm = [true, false].map(nuevo => ({nuevo, suf: nuevo ? 'Nuevo' : 'Editar', pref: nuevo ? 'input' : 'edit', modal: el(nuevo ? 'modalNuevoProducto' : 'modalEditarProducto'), form: el(nuevo ? 'formCrearProducto' : 'formEditarProducto'), submit: el(nuevo ? 'guardarNuevoProducto' : 'guardarEditarProducto'), version: 0, abierto: false, pendiente: false, completo: false, cargando: false, producto: null, codigos: [], origen: null}));
    const consultaCodigo = {version: 0, pendiente: false, controlador: null, resultado: null, tipo: 'BARRA', escaneoPendiente: false, autocompletados: {}, codigoAgregado: null};
    const permisoFormulario = s => s.nuevo ? permisos.crear : permisos.editar;
    const campoCodigo = s => el(s.nuevo ? 'inputCodigoBarra' : 'editCodigosBarra');
    const limpiarCodigo = c => ({codigo: String(c.codigo || '').trim(), tipo: c.tipo || 'BARRA', es_principal: Boolean(c.es_principal)});
    function erroresLimpiar(s) {
        s.modal.querySelectorAll('.is-invalid').forEach(c => { c.classList.remove('is-invalid'); c.removeAttribute('aria-invalid'); });
        aviso(s.nuevo ? 'errorCrearProducto' : 'errorEditarProducto', ''); aviso('errorCodigos' + s.suf, '');
    }
    function bloquear(s) {
        s.modal.querySelectorAll('input,select,textarea,button').forEach(c => {
            if (c.hasAttribute('data-bs-dismiss')) c.disabled = s.pendiente;
            else if (c.id === 'reintentarDetalleEdicion') c.disabled = s.pendiente || s.cargando;
            else c.disabled = s.pendiente || s.completo || s.cargando || (!s.nuevo && !s.producto) || !permisoFormulario(s);
        });
        s.submit.textContent = s.pendiente ? 'Guardando...' : s.nuevo ? 'Crear producto' : 'Guardar cambios';
        if (s.nuevo) {
            s.submit.disabled ||= consultaCodigo.pendiente;
            el('buscarDatosProducto').disabled ||= consultaCodigo.pendiente;
            s.modal.querySelector('[data-target="consultaCodigoProducto"]').disabled ||= consultaCodigo.pendiente;
            el('buscarDatosProducto').textContent = consultaCodigo.pendiente ? 'Buscando...' : 'Buscar datos';
        }
        s.form.setAttribute('aria-busy', String(s.pendiente || s.cargando));
    }
    function cancelarConsulta() {
        consultaCodigo.version++; consultaCodigo.controlador?.abort(); consultaCodigo.controlador = null; consultaCodigo.pendiente = false;
    }
    function reiniciarConsulta() {
        cancelarConsulta(); consultaCodigo.resultado = null; consultaCodigo.tipo = 'BARRA'; consultaCodigo.escaneoPendiente = false;
        consultaCodigo.autocompletados = {}; consultaCodigo.codigoAgregado = null;
        el('resultadoConsultaCodigo').replaceChildren(); el('resultadoConsultaCodigo').hidden = true; aviso('estadoConsultaCodigo', '');
    }
    function urlFuente(valor, host) {
        try { const u = new URL(valor); return u.protocol === 'https:' && u.hostname === host && !u.username && !u.password && (!u.port || u.port === '443') ? u.href : ''; } catch (_) { return ''; }
    }
    function fuenteProducto(destino, fuente) {
        destino.replaceChildren(); destino.hidden = !fuente;
        if (!fuente) return;
        destino.append(document.createTextNode('Datos de '));
        const enlace = nodo('a', '', 'Open Food Facts'), href = urlFuente(fuente.url, 'world.openfoodfacts.org');
        if (href) { enlace.href = href; enlace.target = '_blank'; enlace.rel = 'noopener noreferrer'; }
        destino.append(enlace, document.createTextNode(' · '));
        const licencia = nodo('a', '', 'ODbL'); licencia.href = 'https://opendatacommons.org/licenses/odbl/1-0/'; licencia.target = '_blank'; licencia.rel = 'noopener noreferrer'; destino.append(licencia);
        if (fuente.imagen_url) {
            const imagen = nodo('a', '', 'Imagen: CC BY-SA 3.0'); imagen.href = 'https://creativecommons.org/licenses/by-sa/3.0/'; imagen.target = '_blank'; imagen.rel = 'noopener noreferrer';
            destino.append(document.createTextNode(' · '), imagen);
        }
    }
    function retirarSugerenciaAnterior(s) {
        Object.entries(consultaCodigo.autocompletados).forEach(([id, valor]) => { if (el(id).value === valor) el(id).value = ''; });
        if (consultaCodigo.codigoAgregado) {
            s.codigos = s.codigos.filter(c => c.codigo !== consultaCodigo.codigoAgregado);
            if (s.codigos.length && !s.codigos.some(c => c.es_principal)) s.codigos[0].es_principal = true;
        }
        s.fichaExterna = null; consultaCodigo.autocompletados = {}; consultaCodigo.codigoAgregado = null; renderCodigos(s);
    }
    function aplicarSugerencia(reemplazar = false) {
        const s = estadosForm[0], d = consultaCodigo.resultado;
        if (!d || d.estado !== 'externo' || !s.abierto || s.pendiente || s.completo) return;
        let aplicados = false;
        [['inputNombre', d.sugerencia.nombre], ['inputDescripcion', d.sugerencia.descripcion]].forEach(([id, valor]) => {
            if (typeof valor === 'string' && valor && (reemplazar || !el(id).value.trim())) {
                el(id).value = valor; consultaCodigo.autocompletados[id] = valor; aplicados = true;
                el(id).classList.remove('is-invalid'); el(id).removeAttribute('aria-invalid');
            }
        });
        asociarCodigoConsultado(d.codigo);
        if (aplicados) s.fichaExterna = d.ficha_externa_id;
        actualizarBotonSugerencia();
        aviso('estadoConsultaCodigo', 'Revisa los datos encontrados antes de guardar.');
    }
    function actualizarBotonSugerencia() {
        const boton = el('usarDatosProducto'), d = consultaCodigo.resultado;
        if (boton) boton.hidden = !d?.sugerencia || ![['inputNombre', d.sugerencia.nombre], ['inputDescripcion', d.sugerencia.descripcion]].some(([id, valor]) => valor && el(id).value !== valor);
    }
    ['inputNombre', 'inputDescripcion'].forEach(id => el(id).addEventListener('input', actualizarBotonSugerencia));
    function asociarCodigoConsultado(codigo) {
        const s = estadosForm[0];
        if (!s.codigos.some(c => c.codigo === codigo)) {
            s.codigos.push({codigo, tipo: consultaCodigo.tipo, es_principal: !s.codigos.some(c => c.es_principal)});
            consultaCodigo.codigoAgregado = codigo; renderCodigos(s);
        }
    }
    function mostrarConsulta(d) {
        const contenedor = el('resultadoConsultaCodigo'); contenedor.replaceChildren(); contenedor.hidden = true;
        if (d.estado === 'existente') {
            if (!Number.isInteger(d.producto?.id) || typeof d.producto?.nombre !== 'string') throw new Error('No se pudo leer el producto encontrado.');
            const info = nodo('div'); info.append(nodo('strong', '', d.producto.nombre), nodo('p', '', 'SKU: ' + d.producto.sku + (d.producto.activo ? ' · Activo' : ' · Inactivo')));
            const ver = nodo('button', 'btn btn-outline-primary', 'Ver producto registrado'); ver.id = 'verProductoEncontrado'; ver.type = 'button';
            ver.addEventListener('click', () => {
                const s = estadosForm[0];
                s.modal.addEventListener('hidden.bs.modal', () => { idDetalle = d.producto.id; origenDetalle = el('btnNuevoProducto'); bootstrap.Modal.getOrCreateInstance(el('modalDetalleProducto')).show(); cargarDetalle(); }, {once: true});
                bootstrap.Modal.getOrCreateInstance(s.modal).hide();
            });
            info.append(ver); contenedor.append(info); contenedor.hidden = false;
        } else if (d.estado === 'externo') {
            if (!Number.isInteger(d.ficha_externa_id) || typeof d.sugerencia?.nombre !== 'string' || !d.sugerencia.nombre || !d.fuente) throw new Error('No se pudo leer la información externa.');
            const imagen = urlFuente(d.sugerencia.imagen_url, 'images.openfoodfacts.org');
            if (imagen) { const img = nodo('img'); img.src = imagen; img.alt = 'Imagen de referencia de ' + d.sugerencia.nombre; img.loading = 'lazy'; img.referrerPolicy = 'no-referrer'; img.addEventListener('error', () => img.remove(), {once: true}); contenedor.append(img); }
            const info = nodo('div'); info.append(nodo('strong', '', d.sugerencia.nombre), nodo('p', '', [d.sugerencia.marca, d.sugerencia.presentacion].filter(Boolean).join(' · ')));
            const fuente = nodo('p'); fuenteProducto(fuente, {...d.fuente, imagen_url: imagen}); info.append(fuente);
            const usar = nodo('button', 'btn btn-outline-primary', 'Usar nombre y descripción sugeridos'); usar.id = 'usarDatosProducto'; usar.type = 'button'; usar.addEventListener('click', () => aplicarSugerencia(true));
            info.append(usar); contenedor.append(info); contenedor.hidden = false; aplicarSugerencia();
        } else asociarCodigoConsultado(d.codigo);
    }
    async function buscarDatosProducto() {
        const s = estadosForm[0], codigo = el('consultaCodigoProducto').value.trim();
        if (!s.abierto || s.pendiente || s.completo || consultaCodigo.pendiente || !permisos.crear) return;
        if (!codigo || codigo.length > 100) { aviso('estadoConsultaCodigo', 'Escribe o escanea un código de hasta 100 caracteres.'); el('consultaCodigoProducto').focus(); return; }
        cancelarConsulta(); retirarSugerenciaAnterior(s); consultaCodigo.resultado = null;
        const version = consultaCodigo.version; consultaCodigo.pendiente = true; consultaCodigo.controlador = new AbortController();
        el('resultadoConsultaCodigo').hidden = true; aviso('estadoConsultaCodigo', 'Buscando el producto...'); bloquear(s);
        try {
            const json = await api('/api/v1/productos/consultar-codigo/?' + new URLSearchParams({codigo}), {signal: consultaCodigo.controlador.signal});
            if (version !== consultaCodigo.version || !s.abierto || el('consultaCodigoProducto').value.trim() !== codigo) return;
            const d = json.data;
            if (!d || d.codigo !== codigo || !['existente', 'externo', 'no_compatible', 'no_encontrado', 'indisponible', 'limite'].includes(d.estado)) throw new Error('No se pudo leer el resultado de la consulta.');
            consultaCodigo.resultado = d; aviso('estadoConsultaCodigo', json.mensaje); mostrarConsulta(d);
        } catch (error) { if (version === consultaCodigo.version && s.abierto) aviso('estadoConsultaCodigo', error.message); }
        finally { if (version === consultaCodigo.version) { consultaCodigo.pendiente = false; bloquear(s); } }
    }
    el('buscarDatosProducto').addEventListener('click', buscarDatosProducto);
    el('consultaCodigoProducto').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); buscarDatosProducto(); } });
    el('consultaCodigoProducto').addEventListener('input', () => {
        cancelarConsulta(); consultaCodigo.resultado = null; consultaCodigo.tipo = /^https?:\/\//i.test(el('consultaCodigoProducto').value) ? 'QR' : 'BARRA';
        el('resultadoConsultaCodigo').hidden = true; aviso('estadoConsultaCodigo', ''); bloquear(estadosForm[0]);
    });
    el('consultaCodigoProducto').addEventListener('smartstock:product-barcode-scanned', e => {
        consultaCodigo.tipo = e.detail?.tipo === 'QR' ? 'QR' : 'BARRA'; consultaCodigo.escaneoPendiente = true;
    });
    function errorCampo(s, nombre, texto) {
        const control = el(s.pref + nombre); control.classList.add('is-invalid'); control.setAttribute('aria-invalid', 'true'); el(s.pref + nombre + 'Error').textContent = texto;
    }
    function renderCodigos(s) {
        const lista = el('listaCodigos' + s.suf); lista.replaceChildren();
        if (!s.codigos.length) lista.append(nodo('p', 'text-muted small mb-0', 'Sin códigos asociados.'));
        s.codigos.forEach((c, i) => {
            const fila = nodo('div', 'ss-code-row'); fila.dataset.index = String(i);
            const codigo = nodo('input', 'form-control'); codigo.type = 'text'; codigo.maxLength = 100; codigo.value = c.codigo; codigo.dataset.campoCodigo = 'codigo'; codigo.setAttribute('aria-label', 'Código ' + (i + 1));
            const tipo = nodo('select', 'form-select'); tipo.dataset.campoCodigo = 'tipo'; tipo.setAttribute('aria-label', 'Tipo del código ' + (i + 1)); tipo.append(new Option('Barras', 'BARRA'), new Option('QR', 'QR')); tipo.value = c.tipo;
            const principal = nodo('label', 'ss-code-principal'); const radio = nodo('input'); radio.type = 'radio'; radio.name = 'codigoPrincipal' + s.suf; radio.checked = c.es_principal; radio.dataset.campoCodigo = 'principal'; principal.append(radio, document.createTextNode('Principal'));
            const quitar = nodo('button', 'btn btn-outline-danger', 'Quitar'); quitar.type = 'button'; quitar.dataset.quitarCodigo = String(i); quitar.setAttribute('aria-label', 'Quitar código ' + (i + 1));
            fila.append(codigo, tipo, principal, quitar); lista.append(fila);
        }); bloquear(s);
    }
    function agregarCodigo(s) {
        const valor = campoCodigo(s).value.trim(); if (!valor) { aviso('errorCodigos' + s.suf, 'Ingresa un código para agregarlo.'); return false; }
        if (valor.length > 100 || s.codigos.some(c => c.codigo.trim() === valor)) { aviso('errorCodigos' + s.suf, valor.length > 100 ? 'El código admite hasta 100 caracteres.' : 'Este código ya está en la lista.'); return false; }
        s.codigos.push({codigo: valor, tipo: el('tipoCodigo' + s.suf).value, es_principal: !s.codigos.some(c => c.es_principal)});
        campoCodigo(s).value = ''; aviso('errorCodigos' + s.suf, ''); renderCodigos(s); return true;
    }
    function validarFormulario(s) {
        erroresLimpiar(s); let valido = true;
        const sku = el(s.pref + 'Sku').value.trim(), nombre = el(s.pref + 'Nombre').value.trim(), valor = el(s.pref + 'Precio').value;
        if (!sku || sku.length > 50 || !/^[A-Z0-9_-]+$/i.test(sku)) { errorCampo(s, 'Sku', 'Ingresa un SKU de hasta 50 caracteres: letras A–Z, números, guion o guion bajo.'); valido = false; }
        if (!nombre || nombre.length > 200) { errorCampo(s, 'Nombre', 'Ingresa un nombre de hasta 200 caracteres.'); valido = false; }
        if (!/^\d+(?:\.\d{1,2})?$/.test(valor) || !Number.isFinite(Number(valor)) || Number(valor) > 9999999999.99) { errorCampo(s, 'Precio', 'Ingresa un precio entre 0 y 9.999.999.999,99 con hasta dos decimales.'); valido = false; }
        if (campoCodigo(s).value.trim() && !agregarCodigo(s)) valido = false;
        const codigos = s.codigos.map(limpiarCodigo);
        if (codigos.some(c => !c.codigo || c.codigo.length > 100) || new Set(codigos.map(c => c.codigo)).size !== codigos.length) { aviso('errorCodigos' + s.suf, 'Revisa los códigos: cada fila debe contener un código único de hasta 100 caracteres.'); valido = false; }
        const cambiaron = JSON.stringify(codigos) !== s.codigosOriginales;
        if (codigos.length && (s.nuevo || cambiaron) && codigos.filter(c => c.es_principal).length !== 1) { aviso('errorCodigos' + s.suf, 'Selecciona un código principal.'); valido = false; }
        if (!valido) { s.modal.querySelector('.is-invalid')?.focus(); return null; }
        const campos = {sku: sku.toUpperCase(), nombre, descripcion: el(s.pref + 'Descripcion').value, precio_referencia: valor};
        const payload = {};
        Object.entries(campos).forEach(([k, v]) => {
            const original = s.producto?.[k];
            const mismo = k === 'precio_referencia' ? Number(v) === Number(original) : k === 'sku' ? sku === original : v === (original ?? '');
            if (s.nuevo || !mismo) payload[k] = v;
        });
        if (s.nuevo || cambiaron) payload.codigos_barra = codigos;
        if (s.nuevo && s.fichaExterna) payload.ficha_externa_id = s.fichaExterna;
        return payload;
    }
    function mostrarErrores(s, error) {
        aviso(s.nuevo ? 'errorCrearProducto' : 'errorEditarProducto', error.message);
        const campos = error.datos?.errores || error.datos || {};
        Object.entries({sku: 'Sku', nombre: 'Nombre', descripcion: 'Descripcion', precio_referencia: 'Precio'}).forEach(([k, nombre]) => { if (campos[k]) errorCampo(s, nombre, mensaje(campos[k])); });
        if (campos.codigos_barra) aviso('errorCodigos' + s.suf, mensaje(campos.codigos_barra));
        s.modal.querySelector('.is-invalid')?.focus();
    }
    function iniciarFormulario(s, origen) {
        s.version++; s.abierto = true; s.pendiente = false; s.completo = false; s.cargando = false; s.producto = null; s.codigos = []; s.codigosOriginales = '[]'; s.origen = origen;
        s.form.reset(); erroresLimpiar(s); aviso('estadoFormularioProducto' + s.suf, '');
        if (s.nuevo) { reiniciarConsulta(); s.fichaExterna = null; }
        s.enfocar = s.nuevo ? 'consultaCodigoProducto' : s.pref + 'Sku'; renderCodigos(s);
    }
    async function cargarEdicion(s, id) {
        const v = ++s.version; s.cargando = true; s.producto = null; erroresLimpiar(s); el('reintentarDetalleEdicion').hidden = true;
        aviso('estadoFormularioProductoEditar', 'Cargando el producto completo...'); bloquear(s);
        try {
            const d = productoCompleto(await api('/api/v1/productos/' + encodeURIComponent(id) + '/'));
            if (v !== s.version || !s.abierto) return;
            s.producto = d; s.codigos = d.codigos_barra.map(limpiarCodigo); s.codigosOriginales = JSON.stringify(s.codigos);
            ['Sku', 'Nombre', 'Descripcion', 'Precio'].forEach((nombre, i) => { el('edit' + nombre).value = d[['sku', 'nombre', 'descripcion', 'precio_referencia'][i]] ?? ''; });
            renderCodigos(s); aviso('estadoFormularioProductoEditar', 'SKU: ' + d.sku + (d.activo ? '' : ' · Producto inactivo'));
        } catch (error) {
            if (v !== s.version) return;
            aviso('errorEditarProducto', error.message); aviso('estadoFormularioProductoEditar', 'No se pudo cargar el producto.'); el('reintentarDetalleEdicion').hidden = false;
        } finally { if (v === s.version) { s.cargando = false; bloquear(s); } }
    }
    estadosForm.forEach(s => {
        s.modal.addEventListener('show.bs.modal', () => { s.abierto = true; });
        s.modal.addEventListener('shown.bs.modal', () => {
            if (s.nuevo && consultaCodigo.escaneoPendiente) { consultaCodigo.escaneoPendiente = false; buscarDatosProducto(); }
            if (s.enfocar) { el(s.enfocar)?.focus(); s.enfocar = null; }
        });
        s.modal.addEventListener('hide.bs.modal', e => { if (s.pendiente) { e.preventDefault(); return; } s.abierto = false; if (s.cargando) { s.version++; s.cargando = false; } });
        s.modal.addEventListener('hide.bs.modal', () => { if (s.nuevo && !s.pendiente) cancelarConsulta(); });
        s.modal.addEventListener('hidden.bs.modal', () => { if (!document.querySelector('.modal.show') && s.origen?.isConnected) s.origen.focus(); });
        el('agregarCodigo' + s.suf).addEventListener('click', () => { if (!s.pendiente && !s.cargando && !s.completo && agregarCodigo(s)) campoCodigo(s).focus(); });
        campoCodigo(s).addEventListener('smartstock:product-barcode-scanned', e => {
            if (s.pendiente || s.completo || s.cargando) return;
            if (['QR', 'BARRA'].includes(e.detail.tipo)) el('tipoCodigo' + s.suf).value = e.detail.tipo;
            agregarCodigo(s); s.enfocar = campoCodigo(s).id;
        });
        el('listaCodigos' + s.suf).addEventListener('input', e => {
            const fila = e.target.closest('[data-index]'); if (!fila || s.pendiente || s.cargando || s.completo) return;
            const i = Number(fila.dataset.index), campo = e.target.dataset.campoCodigo;
            if (campo === 'codigo') s.codigos[i].codigo = e.target.value;
        });
        el('listaCodigos' + s.suf).addEventListener('change', e => {
            const fila = e.target.closest('[data-index]'); if (!fila || s.pendiente || s.cargando || s.completo) return;
            const i = Number(fila.dataset.index);
            if (e.target.dataset.campoCodigo === 'tipo') s.codigos[i].tipo = e.target.value;
            if (e.target.dataset.campoCodigo === 'principal') s.codigos.forEach((c, j) => { c.es_principal = i === j; });
        });
        el('listaCodigos' + s.suf).addEventListener('click', e => {
            const b = e.target.closest('[data-quitar-codigo]'); if (!b || s.pendiente || s.cargando || s.completo) return;
            const i = Number(b.dataset.quitarCodigo), principal = s.codigos[i].es_principal; s.codigos.splice(i, 1);
            if (principal && s.codigos.length) s.codigos[0].es_principal = true; renderCodigos(s);
        });
        s.form.addEventListener('submit', async e => {
            e.preventDefault(); if (!s.abierto || s.pendiente || s.completo || s.cargando || (s.nuevo && consultaCodigo.pendiente) || (!s.nuevo && !s.producto) || !permisoFormulario(s)) return;
            const payload = validarFormulario(s); if (!payload) return;
            if (!s.nuevo && !Object.keys(payload).length) { s.completo = true; bootstrap.Modal.getOrCreateInstance(s.modal).hide(); return; }
            s.pendiente = true; bloquear(s);
            try {
                await api(s.nuevo ? '/api/v1/productos/' : '/api/v1/productos/' + s.producto.id + '/', {method: s.nuevo ? 'POST' : 'PATCH', body: JSON.stringify(payload)});
                s.completo = true; s.pendiente = false;
                bootstrap.Modal.getOrCreateInstance(s.modal).hide(); window.dispatchEvent(new Event('smartstock:notifications-changed'));
                if (s.nuevo) pagina = 1; cargarProductos();
            } catch (error) { mostrarErrores(s, error); if (error.incierto || error.status === 404) cargarProductos(); }
            finally { s.pendiente = false; bloquear(s); }
        });
    });
    el('btnNuevoProducto').addEventListener('click', e => { if (!opcionesListas || !permisos.crear || estadosForm.some(s => s.pendiente)) return; const s = estadosForm[0]; iniciarFormulario(s, e.currentTarget); bloquear(s); bootstrap.Modal.getOrCreateInstance(s.modal).show(); });
    el('reintentarDetalleEdicion').addEventListener('click', () => cargarEdicion(estadosForm[1], el('editProductoId').value));
    function abrirEdicion(id, origen) { const s = estadosForm[1]; if (!permisos.editar || estadosForm.some(s => s.pendiente)) return; iniciarFormulario(s, origen); el('editProductoId').value = id; bootstrap.Modal.getOrCreateInstance(s.modal).show(); cargarEdicion(s, id); }
    let versionDetalle = 0, idDetalle = null, origenDetalle, minimoDesdeDetalle = null;
    function abrirDetalle(id, origen = null) {
        idDetalle = id;
        origenDetalle = origen;
        bootstrap.Modal.getOrCreateInstance(el('modalDetalleProducto')).show();
        cargarDetalle();
    }
    async function cargarDetalle() {
        const v = ++versionDetalle; el('datosDetalleProducto').hidden = true; el('reintentarDetalleProducto').hidden = true; aviso('estadoDetalleProducto', 'Cargando producto...');
        try {
            const d = productoCompleto(await api('/api/v1/productos/' + encodeURIComponent(idDetalle) + '/'));
            if (v !== versionDetalle) return;
            const campos = {detalleProductoNombre: d.nombre, detalleProductoSku: d.sku, detalleProductoEstado: d.activo ? 'Activo' : 'Inactivo', detalleProductoPrecio: precio(d.precio_referencia), detalleProductoDescripcion: d.descripcion || 'Sin descripción.', detalleProductoCreado: fecha(d.fecha_creacion), detalleProductoModificado: fecha(d.fecha_modificacion)};
            Object.entries(campos).forEach(([id, v]) => { el(id).textContent = v; });
            fuenteProducto(el('detalleProductoFuente'), d.fuente_externa);
            el('detalleProductoCodigos').replaceChildren(...d.codigos_barra.map(c => nodo('li', '', c.codigo + ' · ' + (c.tipo === 'QR' ? 'QR' : 'Barras') + (c.es_principal ? ' · Principal' : ''))));
            if (!d.codigos_barra.length) el('detalleProductoCodigos').append(nodo('li', 'text-muted', 'Sin códigos asociados.'));
            const filas = (d.existencias || []).map(b => {
                const tr = nodo('tr'), minimo = nodo('td');
                if (permisos.configurar_minimo) minimo.append(controlMinimo(d, b.id, b.minimo));
                else minimo.textContent = String(b.minimo);
                const seleccionada = !origenDetalle && String(b.id) === el('bodegaProductos').value;
                if (seleccionada) tr.classList.add('table-active');
                const nombreBodega = (b.etiqueta || b.nombre) + (seleccionada ? ' (seleccionada)' : '');
                tr.append(nodo('td', '', nombreBodega), nodo('td', '', Number(b.stock).toLocaleString('es-CL') + ' unid.'), minimo, nodo('td', 'ss-stock-' + b.estado, nombresStock[b.estado])); return tr;
            });
            if (!filas.length) { const tr = nodo('tr'), td = nodo('td', 'text-muted', 'Sin bodegas activas.'); td.colSpan = 4; tr.append(td); filas.push(tr); }
            el('detalleProductoStock').replaceChildren(...filas); el('datosDetalleProducto').hidden = false; aviso('estadoDetalleProducto', '');
        } catch (error) { if (v === versionDetalle) { aviso('estadoDetalleProducto', error.message); el('reintentarDetalleProducto').hidden = false; } }
    }
    el('reintentarDetalleProducto').addEventListener('click', cargarDetalle);
    el('modalDetalleProducto').addEventListener('hide.bs.modal', () => { versionDetalle++; });
    el('modalDetalleProducto').addEventListener('hidden.bs.modal', () => {
        if (minimoDesdeDetalle) { const d = minimoDesdeDetalle; minimoDesdeDetalle = null; abrirMinimo(d.id, d.bodega, d.origen, true); }
        else if (origenDetalle?.isConnected) origenDetalle.focus();
    });
    el('detalleProductoStock').addEventListener('click', e => {
        const b = e.target.closest('button[data-accion="minimo"]'); if (!b || !permisos.configurar_minimo) return;
        minimoDesdeDetalle = {id: b.dataset.id, bodega: b.dataset.bodega, origen: b};
        bootstrap.Modal.getOrCreateInstance(el('modalDetalleProducto')).hide();
    });
    const minimo = {version: 0, abierto: false, listo: false, pendiente: false, completo: false, cargando: false, datos: null, id: null, bodega: null, origen: null, volverDetalle: false};
    function bloquearMinimo() {
        el('inputStockMinimo').disabled = !minimo.datos || minimo.pendiente || minimo.completo;
        el('guardarStockMinimo').disabled = !minimo.listo || !minimo.datos || minimo.pendiente || minimo.completo;
        el('guardarStockMinimo').textContent = minimo.pendiente ? 'Guardando...' : 'Guardar mínimo';
        el('reintentarStockMinimo').disabled = minimo.cargando || minimo.pendiente;
        el('modalStockMinimo').querySelectorAll('[data-bs-dismiss="modal"]').forEach(b => { b.disabled = minimo.pendiente; });
        el('formStockMinimo').setAttribute('aria-busy', String(minimo.cargando || minimo.pendiente));
    }
    function limpiarErrorMinimo() {
        el('inputStockMinimo').classList.remove('is-invalid'); el('inputStockMinimo').removeAttribute('aria-invalid'); el('errorCampoStockMinimo').textContent = '';
    }
    function valorMinimo() {
        const texto = el('inputStockMinimo').value.trim(), n = Number(texto);
        return /^\d+$/.test(texto) && Number.isSafeInteger(n) && n <= 2147483647 ? n : null;
    }
    function previsionMinimo() {
        const n = valorMinimo(), d = minimo.datos;
        aviso('previsionStockMinimo', n === null || !d ? '' : (n === 0 ? 'Aviso de stock bajo desactivado. ' : 'Mínimo: ' + n.toLocaleString('es-CL') + ' unidades. ') + 'Con las existencias actuales: ' + nombresStock[d.stock_actual <= 0 ? 'agotado' : n > 0 && d.stock_actual <= n ? 'bajo' : 'suficiente'] + '.');
    }
    async function cargarMinimo() {
        const v = ++minimo.version; minimo.datos = null; minimo.cargando = true;
        el('datosStockMinimo').hidden = true; el('reintentarStockMinimo').hidden = true; el('inputStockMinimo').value = '';
        limpiarErrorMinimo(); aviso('errorStockMinimo', ''); aviso('estadoStockMinimo', 'Cargando mínimo...'); bloquearMinimo();
        try {
            const json = await api('/api/v1/productos/' + encodeURIComponent(minimo.id) + '/stock-minimo/?bodega=' + encodeURIComponent(minimo.bodega)), d = json.data;
            if (v !== minimo.version || !minimo.abierto) return;
            if (!d || String(d.producto_id) !== String(minimo.id) || String(d.bodega_id) !== String(minimo.bodega) || !Number.isInteger(d.cantidad_minima) || d.cantidad_minima < 0 || !Number.isInteger(d.stock_actual) || typeof d.nombre !== 'string' || typeof d.sku !== 'string' || typeof d.bodega !== 'string') throw new Error('No se pudo leer el mínimo de esta bodega.');
            minimo.datos = d;
            el('nombreStockMinimo').textContent = d.nombre; el('skuStockMinimo').textContent = 'SKU: ' + d.sku; el('bodegaStockMinimo').textContent = d.bodega;
            el('cantidadStockMinimo').textContent = d.stock_actual.toLocaleString('es-CL') + ' unid.'; el('inputStockMinimo').value = String(d.cantidad_minima);
            el('datosStockMinimo').hidden = false; aviso('estadoStockMinimo', ''); previsionMinimo(); bloquearMinimo();
            if (document.activeElement === el('modalStockMinimo')) el('inputStockMinimo').focus();
        } catch (error) { if (v === minimo.version && minimo.abierto) { aviso('estadoStockMinimo', error.message); el('reintentarStockMinimo').hidden = false; } }
        finally { if (v === minimo.version) { minimo.cargando = false; bloquearMinimo(); } }
    }
    function abrirMinimo(id, bodega, origen, volverDetalle = false) {
        if (!permisos.configurar_minimo || minimo.pendiente || !bodega) return;
        Object.assign(minimo, {id, bodega, origen, volverDetalle, abierto: true, listo: false, completo: false});
        cargarMinimo(); bootstrap.Modal.getOrCreateInstance(el('modalStockMinimo')).show();
    }
    el('reintentarStockMinimo').addEventListener('click', cargarMinimo);
    el('inputStockMinimo').addEventListener('input', () => { limpiarErrorMinimo(); previsionMinimo(); });
    el('modalStockMinimo').addEventListener('shown.bs.modal', () => { minimo.listo = true; bloquearMinimo(); if (minimo.datos && !minimo.pendiente) el('inputStockMinimo').focus(); });
    el('modalStockMinimo').addEventListener('hide.bs.modal', e => { if (minimo.pendiente) e.preventDefault(); else { minimo.abierto = false; minimo.listo = false; minimo.version++; } });
    el('modalStockMinimo').addEventListener('hidden.bs.modal', () => {
        if (minimo.volverDetalle) { minimo.volverDetalle = false; bootstrap.Modal.getOrCreateInstance(el('modalDetalleProducto')).show(); cargarDetalle(); }
        else if (minimo.origen?.isConnected) minimo.origen.focus();
        else el('totalProductos').focus({preventScroll: true});
    });
    el('formStockMinimo').addEventListener('submit', async e => {
        e.preventDefault(); if (!minimo.abierto || !minimo.listo || minimo.pendiente || minimo.completo || !minimo.datos || !permisos.configurar_minimo) return;
        limpiarErrorMinimo(); aviso('errorStockMinimo', ''); const n = valorMinimo();
        if (n === null) {
            el('errorCampoStockMinimo').textContent = 'Escribe un número entero entre 0 y 2.147.483.647.';
            el('inputStockMinimo').classList.add('is-invalid'); el('inputStockMinimo').setAttribute('aria-invalid', 'true'); el('inputStockMinimo').focus(); return;
        }
        minimo.pendiente = true; bloquearMinimo(); const d = minimo.datos;
        try {
            await api('/api/v1/productos/' + d.producto_id + '/stock-minimo/', {method: 'PATCH', body: JSON.stringify({bodega: d.bodega_id, cantidad_minima: n})});
            minimo.pendiente = false; minimo.completo = true; bootstrap.Modal.getOrCreateInstance(el('modalStockMinimo')).hide();
            window.dispatchEvent(new Event('smartstock:notifications-changed')); cargarProductos();
        } catch (error) {
            const errores = error.datos?.errores || error.datos, campo = errores?.cantidad_minima;
            aviso('errorStockMinimo', campo ? mensaje(campo) : errores?.bodega ? mensaje(errores.bodega) : error.message);
            if (campo) { el('errorCampoStockMinimo').textContent = mensaje(campo); el('inputStockMinimo').classList.add('is-invalid'); el('inputStockMinimo').setAttribute('aria-invalid', 'true'); }
            if (error.status === 403 || error.status === 404) minimo.completo = true;
            if (error.incierto || error.status === 404) cargarProductos();
        } finally { minimo.pendiente = false; bloquearMinimo(); }
    });
    const accion = {version: 0, pendiente: false, completo: false, abierto: false, producto: null, tipo: '', origen: null};
    function bloquearAccion() {
        el('modalAccionProducto').querySelectorAll('button').forEach(b => { b.disabled = b.id === 'confirmarAccionProducto' ? accion.pendiente || accion.completo || !accion.producto : accion.pendiente; });
        if (accion.pendiente) el('confirmarAccionProducto').textContent = 'Procesando...';
    }
    async function abrirAccion(tipo, id, origen) {
        if (!permisos[tipo]) return;
        const v = ++accion.version; Object.assign(accion, {pendiente: false, completo: false, abierto: true, producto: null, tipo, origen});
        const titulos = {desactivar: 'Desactivar producto', reactivar: 'Reactivar producto', eliminar_definitivamente: 'Eliminar definitivamente'};
        el('tituloAccionProducto').textContent = titulos[tipo]; el('confirmarAccionProducto').textContent = titulos[tipo];
        el('confirmarAccionProducto').className = 'btn ' + (tipo === 'eliminar_definitivamente' ? 'btn-danger' : tipo === 'desactivar' ? 'btn-warning' : 'btn-primary');
        el('contenidoAccionProducto').hidden = true; aviso('errorAccionProducto', ''); aviso('estadoAccionProducto', 'Cargando producto...'); bloquearAccion(); bootstrap.Modal.getOrCreateInstance(el('modalAccionProducto')).show();
        try {
            const d = productoCompleto(await api('/api/v1/productos/' + encodeURIComponent(id) + '/'));
            if (v !== accion.version || !accion.abierto) return;
            el('nombreAccionProducto').textContent = d.nombre; el('skuAccionProducto').textContent = 'SKU: ' + d.sku;
            el('descripcionAccionProducto').textContent = tipo === 'desactivar' ? 'El producto no estará disponible para nuevos movimientos. Se conservarán sus existencias y su historial.' : tipo === 'reactivar' ? 'El producto volverá a estar disponible para registrar movimientos.' : 'Esta acción es permanente y no se puede deshacer. Si el producto tiene stock registrado o historial relacionado, el servidor impedirá eliminarlo. Puedes desactivarlo para conservar sus registros.';
            el('contenidoAccionProducto').hidden = false; aviso('estadoAccionProducto', '');
            if ((tipo === 'desactivar' && !d.activo) || (tipo === 'reactivar' && d.activo)) { aviso('errorAccionProducto', 'El estado del producto ya cambió. Cierra esta ventana para revisar el catálogo actualizado.'); cargarProductos(); }
            else accion.producto = d;
        } catch (error) { if (v === accion.version) aviso('estadoAccionProducto', error.message); }
        finally { if (v === accion.version) bloquearAccion(); }
    }
    el('modalAccionProducto').addEventListener('hide.bs.modal', e => { if (accion.pendiente) e.preventDefault(); else { accion.abierto = false; accion.version++; } });
    el('modalAccionProducto').addEventListener('hidden.bs.modal', () => { if (accion.origen?.isConnected) accion.origen.focus(); });
    el('formAccionProducto').addEventListener('submit', async e => {
        e.preventDefault(); if (!accion.abierto || accion.pendiente || accion.completo || !accion.producto || !permisos[accion.tipo]) return;
        accion.pendiente = true; bloquearAccion(); aviso('errorAccionProducto', '');
        const p = accion.producto, ruta = '/api/v1/productos/' + p.id + '/' + (accion.tipo === 'reactivar' ? 'activar/' : accion.tipo === 'eliminar_definitivamente' ? 'eliminar-definitivamente/' : '');
        try {
            await api(ruta, {method: accion.tipo === 'reactivar' ? 'POST' : 'DELETE'});
            accion.pendiente = false; accion.completo = true; bootstrap.Modal.getOrCreateInstance(el('modalAccionProducto')).hide();
            window.dispatchEvent(new Event('smartstock:notifications-changed')); cargarProductos();
        } catch (error) { aviso('errorAccionProducto', error.message); if (error.incierto || error.status === 404) cargarProductos(); }
        finally { accion.pendiente = false; bloquearAccion(); }
    });
    tabla.addEventListener('click', e => {
        const b = e.target.closest('button[data-accion]'); if (!b) return;
        if (b.dataset.accion === 'editar') abrirEdicion(b.dataset.id, b);
        else if (b.dataset.accion === 'minimo') abrirMinimo(b.dataset.id, b.dataset.bodega, b);
        else if (b.dataset.accion === 'detalle') abrirDetalle(b.dataset.id, b);
        else abrirAccion(b.dataset.accion, b.dataset.id, b);
    });
    cargarOpciones();
});
