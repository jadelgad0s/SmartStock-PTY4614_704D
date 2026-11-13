/* Transferencias inmediatas: cantidades por bodega y confirmación recuperable. */
document.addEventListener('DOMContentLoaded', async () => {
    'use strict';
    if (window.SmartStockNavegacion && !await window.SmartStockNavegacion.lista) return;
    if (!localStorage.getItem('access_token')) { window.location.replace('/'); return; }
    const el = id => document.getElementById(id);
    const nodo = (tag, clase, texto) => { const n = document.createElement(tag); if (clase) n.className = clase; if (texto !== undefined) n.textContent = String(texto ?? ''); return n; };
    const aviso = (id, texto) => { el(id).textContent = texto || ''; el(id).hidden = !texto; };
    const numero = n => Number(n).toLocaleString('es-CL');
    const entero = n => Number.isSafeInteger(n) && n > 0;
    const MAX = 2147483647, TAMANO = 25, API = '/api/v1/productos/transferencias/';
    let usuario = {}; try { usuario = JSON.parse(localStorage.getItem('usuario') || '{}') || {}; } catch (_) {}
    el('user-name-sidebar').textContent = usuario.nombre_completo || 'Usuario';
    el('user-role-sidebar').textContent = usuario.rol_nombre || 'Sin rol';
    el('user-avatar').src = 'https://ui-avatars.com/api/?name=' + encodeURIComponent(usuario.nombre_completo || 'Usuario') + '&background=0f766e&color=fff';
    const textoError = d => Array.isArray(d) ? d.map(textoError).join(' ') : d && typeof d === 'object' ? Object.values(d).map(textoError).join(' ') : String(d || '');
    let renovacion = null;
    async function api(ruta, opciones = {}) {
        const escritura = opciones.method === 'POST';
        let token = localStorage.getItem('access_token'), respuesta;
        const enviar = () => fetch(ruta, {...opciones, cache: 'no-store', headers: {
            Authorization: 'Bearer ' + token, ...(opciones.body ? {'Content-Type': 'application/json'} : {}),
        }});
        try {
            respuesta = await enviar();
            if (respuesta.status === 401) {
                if (localStorage.getItem('access_token') === token) {
                    if (!renovacion) renovacion = (async () => {
                        const refresh = localStorage.getItem('refresh_token'); if (!refresh) return false;
                        const r = await fetch('/api/v1/auth/refresh/', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({refresh})});
                        if (r.status >= 500) throw new Error('No se pudo renovar la sesión. Inténtalo nuevamente.');
                        if (!r.ok) return false;
                        const j = await r.json(), d = j.data || j;
                        if (!d.access) return false;
                        localStorage.setItem('access_token', d.access); if (d.refresh) localStorage.setItem('refresh_token', d.refresh);
                        return true;
                    })().finally(() => { renovacion = null; });
                    if (!await renovacion) { window.smartstockClearSession(); window.location.replace('/'); throw new Error('La sesión expiró. Vuelve a iniciar sesión.'); }
                }
                token = localStorage.getItem('access_token'); respuesta = await enviar();
            }
        } catch (causa) {
            const e = new Error(escritura ? 'No pudimos confirmar el resultado. Verifica esta transferencia para recuperar la confirmación sin duplicarla.' : causa.message || 'No se pudo conectar con el servidor.');
            e.incierto = escritura; throw e;
        }
        let json;
        try { json = await respuesta.json(); }
        catch (_) { const e = new Error('No se pudo leer la respuesta del servidor. Inténtalo nuevamente.'); e.incierto = escritura && (respuesta.ok || respuesta.status >= 500); throw e; }
        if (!json || typeof json !== 'object' || Array.isArray(json)) {
            const e = new Error('El servidor devolvió una respuesta inválida. Inténtalo nuevamente.');
            e.status = respuesta.status; e.incierto = escritura && (respuesta.ok || respuesta.status >= 500); throw e;
        }
        if (!respuesta.ok || json.success === false) {
            const e = new Error(json.mensaje || json.detail || textoError(json) || 'No se pudo completar la consulta.');
            e.status = respuesta.status; e.datos = json.errores || json; e.incierto = escritura && respuesta.status >= 500;
            throw e;
        }
        return json;
    }

    const bodegaInicial = new URLSearchParams(location.search).get('bodega');
    let opciones = null, pagina = 1, total = 0, versionHistorial = 0, versionDetalle = 0;
    let timerHistorial, timerProductos, origenDetalle = null;
    const filtrosIds = ['origenTransferencias', 'destinoTransferencias', 'estadoTransferencias', 'desdeTransferencias', 'hastaTransferencias'];
    function contarFiltros() { const n = filtrosIds.filter(id => el(id).value).length; el('mostrarFiltrosTransferencias').textContent = 'Filtros' + (n ? ' (' + n + ')' : ''); }
    el('mostrarFiltrosTransferencias').addEventListener('click', () => {
        const abierto = el('mostrarFiltrosTransferencias').getAttribute('aria-expanded') !== 'true';
        el('mostrarFiltrosTransferencias').setAttribute('aria-expanded', String(abierto));
        el('camposFiltrosTransferencias').classList.toggle('is-open', abierto);
    });
    function mensajeTabla(texto) { const tr = nodo('tr'), td = nodo('td', 'text-center text-muted py-4', texto); td.colSpan = 7; tr.append(td); el('listaTransferencias').replaceChildren(tr); }
    function fila(t) {
        const tr = nodo('tr', 'ss-transfer-row'), partes = String(t.fecha || '').split(' ');
        const fecha = nodo('td', 'ss-transfer-date text-muted'); fecha.dataset.label = 'Fecha / hora'; fecha.append(nodo('span', '', partes[0]), nodo('span', 'small', partes[1]));
        const producto = nodo('td', 'ss-transfer-product'); producto.dataset.label = 'Producto';
        if (t.detalles.length === 1) producto.append(nodo('strong', '', t.detalles[0].producto), nodo('span', '', 'SKU: ' + t.detalles[0].sku));
        else producto.append(nodo('strong', '', t.detalles.length ? t.detalles.length + ' productos' : 'Sin productos registrados'));
        const ruta = nodo('td', 'ss-transfer-route'); ruta.dataset.label = 'Origen y destino'; ruta.append(nodo('span', '', t.bodega_origen.nombre), nodo('span', '', '→ ' + t.bodega_destino.nombre));
        const cantidad = nodo('td', 'ss-transfer-amount', numero(t.cantidad_total) + ' unid.'); cantidad.dataset.label = 'Cantidad';
        const estado = nodo('td'); estado.dataset.label = 'Estado'; estado.append(nodo('span', 'ss-transfer-status' + (t.estado === 'COMPLETADA' ? ' completada' : ''), t.estado === 'COMPLETADA' ? 'Completada' : t.estado === 'PENDIENTE' ? 'Pendiente' : t.estado));
        const persona = nodo('td', '', t.usuario); persona.dataset.label = 'Responsable';
        const acciones = nodo('td'), b = nodo('button', 'btn btn-sm btn-outline-secondary', 'Ver detalle'); b.type = 'button'; b.dataset.detalle = String(t.id); b.setAttribute('aria-label', 'Ver transferencia ' + t.id); acciones.append(b);
        tr.append(fecha, producto, ruta, cantidad, estado, persona, acciones); return tr;
    }
    function paginar() {
        const cont = el('paginacionTransferencias'), paginas = Math.ceil(total / TAMANO); cont.replaceChildren(); if (paginas <= 1) return;
        const agregar = (texto, n, desactivado = false) => { const b = nodo('button', 'btn btn-sm ' + (n === pagina ? 'btn-primary' : 'btn-outline-secondary'), texto); b.type = 'button'; b.dataset.page = String(n); b.disabled = desactivado || n === pagina; if (n === pagina) b.setAttribute('aria-current', 'page'); cont.append(b); };
        agregar('Anterior', pagina - 1, pagina === 1); const numeros = new Set([1, paginas]);
        for (let n = Math.max(1, pagina - 1); n <= Math.min(paginas, pagina + 1); n++) numeros.add(n);
        let previo = 0; [...numeros].sort((a,b) => a-b).forEach(n => { if (previo && n > previo + 1) cont.append(nodo('span', 'align-self-center', '…')); agregar(String(n), n); previo = n; });
        agregar('Siguiente', pagina + 1, pagina === paginas);
    }
    async function cargarHistorial(ultima = false) {
        clearTimeout(timerHistorial); const version = ++versionHistorial;
        contarFiltros(); el('listaTransferencias').setAttribute('aria-busy', 'true'); el('paginacionTransferencias').replaceChildren(); el('resumenTransferencias').textContent = 'Cargando...';
        aviso('errorHistorialTransferencias', ''); el('reintentarHistorialTransferencias').hidden = true; mensajeTabla('Cargando transferencias...');
        const desde = el('desdeTransferencias').value, hasta = el('hastaTransferencias').value;
        if (desde && hasta && desde > hasta) { aviso('errorHistorialTransferencias', 'La fecha inicial no puede ser posterior a la final.'); mensajeTabla('Revisa el rango de fechas.'); el('listaTransferencias').setAttribute('aria-busy', 'false'); return; }
        const params = new URLSearchParams({page: ultima ? 'last' : String(pagina)});
        const valores = {search: el('buscarTransferencias').value.trim(), origen: el('origenTransferencias').value, destino: el('destinoTransferencias').value, estado: el('estadoTransferencias').value, desde, hasta};
        Object.entries(valores).forEach(([k,v]) => { if (v) params.set(k,v); });
        try {
            const d = await api(API + '?' + params); if (version !== versionHistorial) return;
            if (!Array.isArray(d.results) || !Number.isInteger(d.count) || d.count < 0) throw new Error('El historial tiene un formato inválido.');
            total = d.count; if (ultima) pagina = Math.max(1, Math.ceil(total / TAMANO));
            if (d.results.length) el('listaTransferencias').replaceChildren(...d.results.map(fila)); else mensajeTabla('No hay transferencias para estos filtros.');
            el('totalTransferencias').textContent = total + ' transferencias';
            el('resumenTransferencias').textContent = total ? 'Mostrando ' + ((pagina - 1) * TAMANO + 1) + '–' + ((pagina - 1) * TAMANO + d.results.length) + ' de ' + total : '0 transferencias'; paginar();
        } catch (error) {
            if (version !== versionHistorial) return;
            if (error.status === 404 && pagina > 1 && !ultima) return cargarHistorial(true);
            aviso('errorHistorialTransferencias', error.message); mensajeTabla('No se pudo cargar el historial.'); el('reintentarHistorialTransferencias').hidden = false; el('totalTransferencias').textContent = 'Error de carga'; el('resumenTransferencias').textContent = '';
        } finally { if (version === versionHistorial) el('listaTransferencias').setAttribute('aria-busy', 'false'); }
    }
    el('buscarTransferencias').addEventListener('input', () => { ++versionHistorial; pagina = 1; clearTimeout(timerHistorial); mensajeTabla('Buscando...'); el('paginacionTransferencias').replaceChildren(); timerHistorial = setTimeout(() => cargarHistorial(), 300); });
    filtrosIds.forEach(id => el(id).addEventListener('change', () => { pagina = 1; cargarHistorial(); }));
    el('filtrosTransferencias').addEventListener('submit', e => { e.preventDefault(); pagina = 1; cargarHistorial(); });
    el('limpiarTransferencias').addEventListener('click', () => { el('filtrosTransferencias').reset(); pagina = 1; cargarHistorial(); });
    el('reintentarHistorialTransferencias').addEventListener('click', () => cargarHistorial());
    el('paginacionTransferencias').addEventListener('click', e => { const b = e.target.closest('[data-page]'); if (!b || b.disabled) return; pagina = Number(b.dataset.page); cargarHistorial(); el('totalTransferencias').scrollIntoView({block:'start'}); });
    el('arribaTransferencias').addEventListener('click', () => { el('filtrosTransferencias').scrollIntoView({block:'start'}); el('buscarTransferencias').focus({preventScroll:true}); });

    const detalleModal = bootstrap.Modal.getOrCreateInstance(el('modalDetalleTransferencia'));
    el('listaTransferencias').addEventListener('click', async e => {
        const b = e.target.closest('[data-detalle]'); if (!b) return;
        const version = ++versionDetalle; origenDetalle = b; el('datosDetalleTransferencia').hidden = true; el('estadoDetalleTransferencia').textContent = 'Cargando...'; detalleModal.show();
        try {
            const j = await api(API + encodeURIComponent(b.dataset.detalle) + '/'); if (version !== versionDetalle) return;
            const d = j.data, campos = {Id:'#' + d.id, Fecha:d.fecha, Estado:d.estado === 'COMPLETADA' ? 'Completada' : d.estado === 'PENDIENTE' ? 'Pendiente' : d.estado, Usuario:d.usuario, Origen:d.bodega_origen.nombre, Destino:d.bodega_destino.nombre};
            Object.entries(campos).forEach(([k,v]) => { el('detalleTransferencia' + k).textContent = v; });
            const filas = d.detalles.map(p => { const tr = nodo('tr'); tr.append(nodo('td','',p.sku), nodo('td','',p.producto), nodo('td','',numero(p.cantidad) + ' unid.')); return tr; });
            if (!filas.length) { const tr = nodo('tr'), td = nodo('td','','Sin productos registrados.'); td.colSpan = 3; tr.append(td); filas.push(tr); }
            el('detalleTransferenciaProductos').replaceChildren(...filas);
            const s = d.stock;
            el('detalleTransferenciaStock').textContent = s ? 'Stock al realizar el traslado. Origen: ' + numero(s.origen_anterior) + ' → ' + numero(s.origen_posterior) + '. Destino: ' + numero(s.destino_anterior) + ' → ' + numero(s.destino_posterior) + ' unidades.' : 'Este registro no tiene una instantánea de stock anterior y posterior.';
            el('detalleTransferenciaMovimientos').textContent = d.movimientos ? 'Movimientos asociados: salida #' + d.movimientos.salida + ' y entrada #' + d.movimientos.entrada + '.' : '';
            el('estadoDetalleTransferencia').textContent = ''; el('datosDetalleTransferencia').hidden = false;
        } catch (error) { if (version === versionDetalle) el('estadoDetalleTransferencia').textContent = error.message; }
    });
    el('modalDetalleTransferencia').addEventListener('hidden.bs.modal', () => { ++versionDetalle; if (origenDetalle?.isConnected) origenDetalle.focus(); });

    const f = {abierto:false, guardando:false, incierta:false, completa:false, cargando:false, resolviendo:false, camara:false, codigoCamara:null, version:0, producto:null, productos:new Map(), pagina:1, total:0, solicitud:null, payload:null};
    const modalEl = el('modalTransferencia'), modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    const clavePendiente = entero(usuario.id) ? 'ss-transferencia-pendiente:' + usuario.id : null;
    let pendienteGuardada = null;
    function validarPendiente(d) {
        const p = d?.payload;
        return p && entero(p.producto_id) && entero(p.bodega_origen_id) && entero(p.bodega_destino_id) && p.bodega_origen_id !== p.bodega_destino_id && entero(p.cantidad) && p.cantidad <= MAX && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(p.solicitud_id)
            && validarProducto(d.producto, {origen:String(p.bodega_origen_id),destino:String(p.bodega_destino_id)}) && d.producto.id === p.producto_id;
    }
    if (clavePendiente) { try { const d = JSON.parse(sessionStorage.getItem(clavePendiente) || 'null'); if (validarPendiente(d)) pendienteGuardada = d; } catch (_) {} }
    function guardarPendiente(d) { pendienteGuardada = d; if (clavePendiente) { try { sessionStorage.setItem(clavePendiente, JSON.stringify(d)); } catch (_) {} } actualizarAcceso(); }
    function borrarPendiente() { pendienteGuardada = null; if (clavePendiente) { try { sessionStorage.removeItem(clavePendiente); } catch (_) {} } actualizarAcceso(); }
    function nuevoId() {
        if (window.crypto?.randomUUID) return window.crypto.randomUUID();
        const a = window.crypto.getRandomValues(new Uint8Array(16)); a[6] = (a[6] & 15) | 64; a[8] = (a[8] & 63) | 128;
        const h = [...a].map(n => n.toString(16).padStart(2,'0')).join(''); return h.slice(0,8) + '-' + h.slice(8,12) + '-' + h.slice(12,16) + '-' + h.slice(16,20) + '-' + h.slice(20);
    }
    function actualizarAcceso() {
        const pendiente = Boolean(pendienteGuardada);
        el('avisoTransferenciaPendiente').hidden = !pendiente;
        el('nuevaTransferencia').disabled = !opciones || (!pendiente && (!opciones.permisos.registrar || opciones.bodegas.length < 2));
        el('nuevaTransferencia').textContent = pendiente ? 'Verificar transferencia' : 'Nueva transferencia';
        el('reanudarTransferencia').disabled = !opciones;
    }
    function contexto() {
        const origen = el('transferenciaOrigen').value, destino = el('transferenciaDestino').value;
        return origen && destino && origen !== destino ? {origen,destino} : null;
    }
    function nombreBodega(id) { return opciones?.bodegas_historial.find(b => String(b.id) === String(id))?.nombre || 'Bodega #' + id; }
    function validarProducto(p,c) { return p && entero(p.id) && typeof p.nombre === 'string' && typeof p.sku === 'string' && Number.isSafeInteger(p.stock_origen) && Number.isSafeInteger(p.stock_destino) && String(p.bodega_origen_id) === c.origen && String(p.bodega_destino_id) === c.destino; }
    function actualizarFormulario() {
        const c = contexto(), p = f.producto, bloqueado = f.guardando || f.incierta || f.completa;
        modalEl.querySelectorAll('input,select,button').forEach(n => { n.disabled = bloqueado; });
        modalEl.querySelectorAll('[data-bs-dismiss]').forEach(n => { n.disabled = f.guardando; });
        el('transferenciaProducto').disabled = bloqueado || f.cargando || f.resolviendo || !c || !f.productos.size;
        ['transferenciaBuscarProducto','transferenciaCodigo','buscarCodigoTransferencia','camaraTransferencia'].forEach(id => { el(id).disabled = bloqueado || !c || (id !== 'transferenciaBuscarProducto' && f.resolviendo); });
        el('productosTransferenciaAnterior').disabled = bloqueado || f.cargando || f.resolviendo || f.pagina <= 1;
        el('productosTransferenciaSiguiente').disabled = bloqueado || f.cargando || f.resolviendo || f.pagina >= Math.ceil(f.total / TAMANO);
        const n = f.incierta && f.payload ? f.payload.cantidad : Number(el('transferenciaCantidad').value);
        const cantidadValida = entero(n) && n <= MAX;
        const disponible = p && c && validarProducto(p,c);
        const suficiente = disponible && cantidadValida && n <= p.stock_origen;
        const destinoValido = disponible && p.stock_destino >= 0 && p.stock_destino + n <= MAX && p.stock_origen - n <= MAX;
        const valido = cantidadValida && suficiente && destinoValido;
        el('previsionTransferencia').hidden = !p;
        if (p) {
            el('nombreOrigenTransferencia').textContent = nombreBodega(p.bodega_origen_id); el('nombreDestinoTransferencia').textContent = nombreBodega(p.bodega_destino_id);
            el('stockOrigenTransferencia').textContent = 'Antes: ' + numero(p.stock_origen) + (valido ? ' · Después: ' + numero(p.stock_origen - n) : '') + ' unid.';
            el('stockDestinoTransferencia').textContent = 'Antes: ' + numero(p.stock_destino) + (valido ? ' · Después: ' + numero(p.stock_destino + n) : '') + ' unid.';
        }
        el('resumenNuevaTransferencia').textContent = f.incierta ? 'Verifica la misma confirmación. Si ya se registró, se recuperará el resultado sin volver a descontar unidades.' :
            !c ? 'Selecciona dos bodegas distintas para origen y destino.' : !p ? 'Selecciona un producto de la bodega de origen.' : !cantidadValida ? 'Ingresa una cantidad entera mayor que cero.' : !suficiente ? 'Stock insuficiente en origen: hay ' + numero(p.stock_origen) + ' unidades disponibles.' : !destinoValido ? 'Revisa las cantidades de destino: el traslado supera el límite permitido o hay stock negativo.' :
            'Se trasladarán ' + numero(n) + ' unidades de ' + p.nombre + ' desde ' + nombreBodega(p.bodega_origen_id) + ' hacia ' + nombreBodega(p.bodega_destino_id) + '.';
        el('resumenNuevaTransferencia').classList.toggle('alert-warning', Boolean(p && !valido) || f.incierta);
        el('resumenNuevaTransferencia').classList.toggle('alert-info', !f.incierta && (!p || valido));
        el('confirmarTransferencia').disabled = f.guardando || f.completa || f.camara || !f.abierto || (!f.incierta && (!opciones?.permisos.registrar || !valido || f.cargando || f.resolviendo));
        el('confirmarTransferencia').textContent = f.guardando ? 'Confirmando...' : f.incierta ? 'Verificar transferencia' : f.completa ? 'Transferencia completada' : 'Confirmar transferencia';
        return Boolean(valido);
    }
    function prepararProductos() {
        f.producto = null; f.productos.clear(); f.total = 0; f.cargando = true; f.resolviendo = false;
        el('transferenciaProducto').replaceChildren(new Option('Cargando productos...', '')); el('resumenProductosTransferencia').textContent = 'Cargando...'; el('reintentarProductosTransferencia').hidden = true;
        actualizarFormulario();
    }
    async function cargarProductos(ultima = false) {
        clearTimeout(timerProductos); if (!f.abierto || f.guardando || f.incierta) return;
        const version = ++f.version, c = contexto(); prepararProductos();
        if (!c) { f.cargando = false; el('transferenciaProducto').replaceChildren(new Option('Selecciona las bodegas de origen y destino', '')); el('resumenProductosTransferencia').textContent = ''; actualizarFormulario(); return; }
        const params = new URLSearchParams({...c,page:ultima ? 'last' : String(f.pagina)}), q = el('transferenciaBuscarProducto').value.trim(); if (q) params.set('search',q);
        try {
            const d = await api(API + 'productos/?' + params); if (version !== f.version || !f.abierto) return;
            if (!Array.isArray(d.results) || !Number.isInteger(d.count) || d.count < 0 || d.results.some(p => !validarProducto(p,c))) throw new Error('No se pudieron leer los productos de estas bodegas. Vuelve a consultar.');
            f.total = d.count; if (ultima) f.pagina = Math.max(1,Math.ceil(f.total / TAMANO));
            f.productos = new Map(d.results.map(p => [String(p.id),p]));
            el('transferenciaProducto').replaceChildren(new Option(d.results.length ? 'Selecciona un producto...' : 'Sin productos con existencias para esta búsqueda', ''), ...d.results.map(p => new Option(p.sku + ' · ' + p.nombre + ' (Disponible: ' + numero(p.stock_origen) + ')',String(p.id))));
            el('resumenProductosTransferencia').textContent = f.total ? ((f.pagina-1)*TAMANO+1) + '–' + ((f.pagina-1)*TAMANO+d.results.length) + ' de ' + f.total + ' productos' : '0 productos con existencias'; aviso('errorNuevaTransferencia','');
        } catch (error) {
            if (version !== f.version || !f.abierto) return;
            if (error.status === 404 && f.pagina > 1 && !ultima) return cargarProductos(true);
            aviso('errorNuevaTransferencia',error.message); el('transferenciaProducto').replaceChildren(new Option('No se pudieron cargar los productos','')); el('resumenProductosTransferencia').textContent = 'Error de carga'; el('reintentarProductosTransferencia').hidden = false;
        } finally { if (version === f.version) { f.cargando = false; actualizarFormulario(); } }
    }
    async function resolverCodigo(codigo) {
        codigo = String(codigo || '').trim(); const c = contexto();
        if (!codigo || !c || !f.abierto || f.guardando || f.incierta || f.resolviendo) return;
        clearTimeout(timerProductos); const version = ++f.version; prepararProductos(); f.resolviendo = true; actualizarFormulario(); aviso('errorNuevaTransferencia','');
        try {
            const j = await api(API + 'resolver/?' + new URLSearchParams({...c,codigo})); if (version !== f.version || !f.abierto) return;
            if (!validarProducto(j.data,c)) throw new Error('El producto consultado corresponde a otras bodegas. Vuelve a escanear.');
            const p = j.data; f.producto = p; f.productos = new Map([[String(p.id),p]]); f.pagina = 1; f.total = 1;
            el('transferenciaProducto').replaceChildren(new Option(p.sku + ' · ' + p.nombre,String(p.id),true,true)); el('resumenProductosTransferencia').textContent = 'Producto encontrado por código';
        } catch (error) { if (version === f.version && f.abierto) { aviso('errorNuevaTransferencia',error.message); el('transferenciaProducto').replaceChildren(new Option('No se encontró un producto disponible','')); el('resumenProductosTransferencia').textContent = ''; } }
        finally { if (version === f.version) { f.cargando = false; f.resolviendo = false; actualizarFormulario(); } }
    }
    function opcionesFormulario() {
        for (const [id,texto] of [['transferenciaOrigen','Selecciona origen'],['transferenciaDestino','Selecciona destino']]) el(id).replaceChildren(new Option(texto,''), ...(opciones?.bodegas || []).map(b => new Option(b.etiqueta || b.nombre,String(b.id))));
    }
    function abrirFormulario() {
        if (!opciones || f.guardando || (!pendienteGuardada && (!opciones.permisos.registrar || opciones.bodegas.length < 2))) return;
        Object.assign(f,{abierto:true,incierta:false,completa:false,cargando:false,resolviendo:false,camara:false,codigoCamara:null,producto:null,productos:new Map(),pagina:1,total:0,payload:null}); ++f.version;
        el('formTransferencia').reset(); aviso('errorNuevaTransferencia',''); el('reintentarProductosTransferencia').hidden = true; opcionesFormulario();
        if (pendienteGuardada) {
            f.incierta = true; f.payload = {...pendienteGuardada.payload}; f.solicitud = f.payload.solicitud_id; f.producto = {...pendienteGuardada.producto};
            for (const [id,n] of [['transferenciaOrigen',f.payload.bodega_origen_id],['transferenciaDestino',f.payload.bodega_destino_id]]) { if (![...el(id).options].some(o => o.value === String(n))) el(id).add(new Option(nombreBodega(n),String(n))); el(id).value = String(n); }
            f.productos.set(String(f.producto.id),f.producto); el('transferenciaProducto').replaceChildren(new Option(f.producto.sku + ' · ' + f.producto.nombre,String(f.producto.id),true,true)); el('transferenciaCantidad').value = String(f.payload.cantidad); el('resumenProductosTransferencia').textContent = 'Solicitud por verificar'; el('tituloNuevaTransferencia').textContent = 'Verificar transferencia';
            aviso('errorNuevaTransferencia','La respuesta anterior no pudo confirmarse. Verifica esta solicitud para recuperar su resultado.'); actualizarFormulario(); modal.show(); return;
        }
        try { f.solicitud = nuevoId(); } catch (_) { f.abierto = false; aviso('errorHistorialTransferencias','El navegador no permite iniciar una confirmación segura. Abre el sitio mediante HTTPS o localhost.'); return; }
        const origen = bodegaInicial || String(opciones.bodega_predeterminada || opciones.bodegas[0]?.id || '');
        el('transferenciaOrigen').value = opciones.bodegas.some(b => String(b.id) === origen) ? origen : '';
        el('tituloNuevaTransferencia').textContent = 'Nueva transferencia'; actualizarFormulario(); modal.show(); cargarProductos();
    }
    el('nuevaTransferencia').addEventListener('click', abrirFormulario); el('reanudarTransferencia').addEventListener('click', abrirFormulario);
    ['transferenciaOrigen','transferenciaDestino'].forEach(id => el(id).addEventListener('change', () => { if (f.guardando || f.incierta) return; f.pagina = 1; aviso('errorNuevaTransferencia',''); cargarProductos(); }));
    el('transferenciaBuscarProducto').addEventListener('input', () => { if (f.guardando || f.incierta) return; clearTimeout(timerProductos); ++f.version; f.pagina = 1; prepararProductos(); timerProductos = setTimeout(() => cargarProductos(),300); });
    el('transferenciaProducto').addEventListener('change', () => { if (f.guardando || f.incierta) return; f.producto = f.productos.get(el('transferenciaProducto').value) || null; aviso('errorNuevaTransferencia',''); actualizarFormulario(); });
    el('transferenciaCantidad').addEventListener('input', () => { if (f.guardando || f.incierta) return; aviso('errorNuevaTransferencia',''); actualizarFormulario(); });
    [['productosTransferenciaAnterior',-1],['productosTransferenciaSiguiente',1]].forEach(([id,n]) => el(id).addEventListener('click', () => { if (el(id).disabled) return; f.pagina += n; cargarProductos(); }));
    el('reintentarProductosTransferencia').addEventListener('click', () => cargarProductos());
    el('transferenciaCodigo').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); resolverCodigo(el('transferenciaCodigo').value); } });
    el('buscarCodigoTransferencia').addEventListener('click', () => resolverCodigo(el('transferenciaCodigo').value));
    el('camaraTransferencia').addEventListener('click', () => { if (!el('camaraTransferencia').disabled) f.camara = true; });
    el('transferenciaCodigo').addEventListener('smartstock:product-barcode-scanned', e => { if (f.camara) f.codigoCamara = e.detail?.codigo; else resolverCodigo(e.detail?.codigo); });
    modalEl.addEventListener('hide.bs.modal', e => { if (f.guardando) e.preventDefault(); });
    modalEl.addEventListener('hidden.bs.modal', () => { if (!f.camara) { f.abierto = false; ++f.version; clearTimeout(timerProductos); if (f.incierta) cargarHistorial(); if (!el('nuevaTransferencia').disabled) el('nuevaTransferencia').focus(); } });
    modalEl.addEventListener('shown.bs.modal', () => {
        if (f.camara) { f.camara = false; const codigo = f.codigoCamara; f.codigoCamara = null; if (codigo) resolverCodigo(codigo); }
        if (window.matchMedia('(min-width: 992px)').matches && !f.incierta) el('transferenciaCodigo').focus();
    });
    el('formTransferencia').addEventListener('submit', async e => {
        e.preventDefault(); if (!f.abierto || f.guardando || f.completa || f.camara || !modalEl.classList.contains('show')) return;
        if (!f.incierta && (!actualizarFormulario() || !el('formTransferencia').reportValidity())) return;
        const payload = f.incierta ? {...f.payload} : {bodega_origen_id:Number(el('transferenciaOrigen').value),bodega_destino_id:Number(el('transferenciaDestino').value),producto_id:f.producto.id,cantidad:Number(el('transferenciaCantidad').value),solicitud_id:f.solicitud};
        f.payload = payload; guardarPendiente({payload,producto:{...f.producto}}); f.guardando = true; actualizarFormulario(); aviso('errorNuevaTransferencia','');
        try {
            const j = await api(API,{method:'POST',body:JSON.stringify(payload)});
            if (!j.data || !entero(j.data.id) || j.data.estado !== 'COMPLETADA') { const err = new Error('No se pudo verificar la confirmación. Inténtalo nuevamente.'); err.incierto = true; throw err; }
            f.completa = true; f.incierta = false; f.guardando = false; borrarPendiente(); modal.hide(); pagina = 1; cargarHistorial(); window.dispatchEvent(new Event('smartstock:notifications-changed'));
        } catch (error) {
            f.incierta = Boolean(error.incierto);
            if (!f.incierta) { borrarPendiente(); if (error.datos?.codigo === 'SOLICITUD_UTILIZADA') f.completa = true; }
            if (!f.incierta && f.producto) { if (Number.isInteger(error.datos?.stock_origen)) f.producto.stock_origen = error.datos.stock_origen; if (Number.isInteger(error.datos?.stock_destino)) f.producto.stock_destino = error.datos.stock_destino; }
            aviso('errorNuevaTransferencia',error.message + (error.status === 400 && error.datos ? ' ' + textoError(error.datos) : ''));
        } finally { f.guardando = false; actualizarFormulario(); actualizarAcceso(); }
    });

    async function cargarOpciones() {
        if (f.abierto || f.guardando) return;
        el('actualizarBodegasTransferencias').disabled = true; el('estadoBodegasTransferencias').textContent = 'Cargando bodegas...';
        try {
            const j = await api(API + 'opciones/'), d = j.data;
            if (!d || !Array.isArray(d.bodegas) || !Array.isArray(d.bodegas_historial) || !d.permisos || d.bodegas_historial.some(b => !entero(b.id) || typeof b.nombre !== 'string')) throw new Error('No se pudieron leer las bodegas.');
            opciones = d;
            for (const id of ['origenTransferencias','destinoTransferencias']) { const previo = el(id).value; el(id).replaceChildren(new Option('Todas','',true), ...d.bodegas_historial.map(b => new Option((b.etiqueta || b.nombre) + (b.activa === false ? ' (inactiva)' : ''),String(b.id)))); if (d.bodegas_historial.some(b => String(b.id) === previo)) el(id).value = previo; }
            [['menu-auditoria',d.permisos.auditoria],['menu-usuarios',d.permisos.usuarios],['menu-config',d.permisos.configuracion],['menu-sistema-title',d.permisos.usuarios || d.permisos.configuracion]].forEach(([id,v]) => { el(id).hidden = !v; });
            el('estadoBodegasTransferencias').textContent = !d.permisos.registrar ? 'Acceso de consulta. Para registrar necesitas el permiso de transferencias.' : d.bodegas.length < 2 ? 'Necesitas al menos dos bodegas activas para registrar una transferencia. Puedes administrarlas desde Bodegas.' : 'Las transferencias se completan al confirmar y conservan el total de unidades.';
        } catch (error) { opciones = null; el('estadoBodegasTransferencias').textContent = error.message; }
        finally { el('actualizarBodegasTransferencias').disabled = false; actualizarAcceso(); contarFiltros(); }
    }
    el('actualizarBodegasTransferencias').addEventListener('click', cargarOpciones);
    actualizarAcceso(); cargarHistorial(); cargarOpciones();
});
