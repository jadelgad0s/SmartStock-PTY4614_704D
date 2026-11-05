/* Mermas: historial y confirmación del descuento en la bodega seleccionada. */
document.addEventListener('DOMContentLoaded', async () => {
    'use strict';
    if (window.SmartStockNavegacion && !await window.SmartStockNavegacion.lista) return;
    const token = localStorage.getItem('access_token');
    if (!token) { window.location.href = '/'; return; }
    const usuario = (() => { try { return JSON.parse(localStorage.getItem('usuario') || '{}'); } catch (_) { return {}; } })();
    const rol = (usuario.rol_nombre || 'Operador').toLowerCase();
    const administrador = rol === 'administrador' || usuario.is_superuser === true;
    if (!window.SmartStockNavegacion && !administrador && rol === 'operador') { window.location.href = '/movimientos/'; return; }
    const el = id => document.getElementById(id);
    if (!window.SmartStockNavegacion && !administrador) ['menu-auditoria', 'menu-usuarios', 'menu-config', 'menu-sistema-title'].forEach(id => {
        if (el(id)) el(id).hidden = true;
    });
    el('user-name-sidebar').textContent = usuario.nombre_completo || 'Usuario';
    el('user-role-sidebar').textContent = usuario.rol_nombre || 'Rol';
    el('user-avatar').src = 'https://ui-avatars.com/api/?name=' + encodeURIComponent(usuario.nombre_completo || 'User') + '&background=0f766e&color=fff';

    const headers = {Authorization: 'Bearer ' + token};
    const tabla = el('listaMermas');
    const paginador = el('paginacionMermas');
    const resumen = el('resumenMermas');
    const formulario = el('formNuevaMerma');
    const select = el('mermaProducto');
    const modalEl = el('modalNuevaMerma');
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    const detalleEl = el('modalDetalleMerma');
    const modalDetalle = bootstrap.Modal.getOrCreateInstance(detalleEl);
    let pagina = 1;
    let total = 0;
    let versionHistorial = 0;
    let versionDetalle = 0;
    let temporizadorHistorial;
    let paginaProductos = 1;
    let totalProductos = 0;
    let versionProductos = 0;
    let temporizadorProductos;
    let cargandoProductos = false;
    let productos = new Map();
    let producto = null;
    let esperando = false;
    let registrado = false;
    let origenDetalle = null;
    let bodegaInicial = new URLSearchParams(location.search).get('bodega');
    let bodegasListas = false, bodegas = [], predeterminada = '';
    const TAMANO_PAGINA = 25;
    const nodo = (tag, clase, texto) => {
        const elemento = document.createElement(tag);
        if (clase) elemento.className = clase;
        if (texto !== undefined) elemento.textContent = String(texto ?? '');
        return elemento;
    };
    const aviso = (id, texto, tipo = 'danger') => {
        const elemento = el(id);
        elemento.className = 'alert' + (texto ? ' alert-' + tipo : ' d-none');
        elemento.textContent = texto || '';
    };
    async function consultar(url, opciones = {}) {
        let res;
        try { res = await fetch(url, {headers, ...opciones}); }
        catch (_) { throw new Error('No se pudo conectar con el servidor. Revisa la conexión y el historial antes de reintentar un registro.'); }
        let json;
        try { json = await res.json(); }
        catch (_) { throw new Error('No se pudo leer la respuesta. Revisa el historial antes de reintentar un registro.'); }
        if (!res.ok || json.success === false) {
            const error = new Error(res.status === 401 ? 'La sesión expiró. Vuelve a iniciar sesión.' : json.mensaje || json.detail || 'No se pudo completar la consulta.');
            error.status = res.status;
            error.datos = json;
            throw error;
        }
        return json;
    }
    function mensajeTabla(texto) {
        const fila = nodo('tr');
        const celda = nodo('td', 'text-center text-muted py-4', texto);
        celda.colSpan = 6;
        fila.appendChild(celda);
        tabla.replaceChildren(fila);
    }
    function prepararHistorial() {
        tabla.setAttribute('aria-busy', 'true');
        paginador.replaceChildren();
        resumen.textContent = 'Cargando mermas...';
        aviso('errorHistorialMermas', '');
        mensajeTabla('Cargando mermas...');
    }
    function filaMerma(m) {
        const fila = nodo('tr', 'ss-loss-row');
        const partes = String(m.fecha || '').split(' ');
        const fecha = nodo('td', 'ss-loss-date text-muted');
        fecha.append(nodo('span', '', partes[0] || ''), nodo('span', 'ss-loss-time', partes[1] || ''));
        const celdaProducto = nodo('td', 'ss-loss-product');
        celdaProducto.append(nodo('strong', '', m.producto), nodo('span', 'ss-loss-sku', 'SKU: ' + m.sku));
        celdaProducto.append(nodo('span', 'ss-loss-sku', m.bodega));
        const cantidad = nodo('td', 'ss-loss-quantity text-danger');
        cantidad.append(nodo('span', '', '−' + m.cantidad), nodo('span', 'ss-loss-units', ' unid.'));
        const motivo = nodo('td', 'ss-loss-reason');
        motivo.appendChild(nodo('span', 'ss-loss-reason-tag', m.motivo));
        if (m.observacion) motivo.appendChild(nodo('span', 'ss-loss-preview', m.observacion));
        const responsable = nodo('td', 'ss-loss-person', m.responsable);
        const acciones = nodo('td', 'ss-loss-actions');
        const boton = nodo('button', 'btn btn-sm btn-outline-secondary', 'Ver detalle');
        boton.type = 'button';
        boton.dataset.detalle = String(m.id);
        boton.setAttribute('aria-label', 'Ver detalle de la merma ' + m.id + ' de ' + m.producto);
        acciones.appendChild(boton);
        fila.append(fecha, celdaProducto, cantidad, motivo, responsable, acciones);
        return fila;
    }
    function renderizarPaginacion(paginas) {
        paginador.replaceChildren();
        if (paginas <= 1) return;
        const lista = nodo('ul', 'pagination');
        const agregar = (texto, numero, deshabilitado, actual = false) => {
            const item = nodo('li', 'page-item' + (actual ? ' active' : ''));
            const boton = nodo('button', 'page-link', texto);
            boton.type = 'button';
            boton.dataset.page = String(numero);
            boton.disabled = deshabilitado || actual;
            boton.setAttribute('aria-label', texto === 'Anterior' ? 'Página anterior' : texto === 'Siguiente' ? 'Página siguiente' : 'Ir a página ' + numero);
            if (actual) boton.setAttribute('aria-current', 'page');
            item.appendChild(boton);
            lista.appendChild(item);
        };
        agregar('Anterior', pagina - 1, pagina === 1);
        const numeros = new Set([1, paginas]);
        for (let n = Math.max(1, pagina - 1); n <= Math.min(paginas, pagina + 1); n++) numeros.add(n);
        if (pagina <= 2 && paginas >= 3) numeros.add(3);
        let anterior = 0;
        [...numeros].sort((a, b) => a - b).forEach(n => {
            if (anterior && n > anterior + 1) {
                const item = nodo('li', 'page-item');
                const puntos = nodo('span', 'ss-loss-ellipsis', '…');
                puntos.setAttribute('aria-hidden', 'true');
                item.appendChild(puntos);
                lista.appendChild(item);
            }
            agregar(String(n), n, false, n === pagina);
            anterior = n;
        });
        agregar('Siguiente', pagina + 1, pagina === paginas);
        paginador.appendChild(lista);
    }
    function indicadorFiltros() {
        const cantidad = ['bodegaHistorialMermas', 'motivoMermas', 'desdeMermas', 'hastaMermas'].filter(id => el(id).value).length;
        el('mostrarFiltrosMermas').textContent = 'Filtros' + (cantidad ? ' (' + cantidad + ')' : '');
    }
    async function cargarHistorial({ultimaPagina = false, enfocar = false} = {}) {
        clearTimeout(temporizadorHistorial);
        const version = ++versionHistorial;
        prepararHistorial();
        indicadorFiltros();
        const desde = el('desdeMermas').value;
        const hasta = el('hastaMermas').value;
        if (desde && hasta && desde > hasta) {
            aviso('errorHistorialMermas', 'La fecha inicial no puede ser posterior a la final.');
            mensajeTabla('Revisa el rango de fechas.');
            resumen.textContent = '';
            tabla.setAttribute('aria-busy', 'false');
            return;
        }
        const params = new URLSearchParams({page: ultimaPagina ? 'last' : String(pagina)});
        const campos = {search: el('buscarMermas').value.trim(), bodega: el('bodegaHistorialMermas').value, motivo: el('motivoMermas').value, desde, hasta};
        Object.entries(campos).forEach(([key, value]) => { if (value) params.set(key, value); });
        try {
            const json = await consultar('/api/v1/productos/mermas/historial/?' + params);
            if (version !== versionHistorial) return;
            if (!Array.isArray(json.results) || !Number.isInteger(json.count) || json.count < 0) throw new Error('La respuesta del historial no es válida.');
            total = json.count;
            const paginas = Math.ceil(total / TAMANO_PAGINA);
            if (ultimaPagina) pagina = Math.max(1, paginas);
            if (json.results.length) {
                tabla.replaceChildren(...json.results.map(filaMerma));
                const primero = (pagina - 1) * TAMANO_PAGINA + 1;
                resumen.textContent = 'Mostrando ' + primero + '–' + (primero + json.results.length - 1) + ' de ' + total + ' mermas';
            } else {
                mensajeTabla('No hay mermas para estos filtros.');
                resumen.textContent = '0 mermas';
            }
            renderizarPaginacion(paginas);
        } catch (error) {
            if (version !== versionHistorial) return;
            if (error.status === 404 && pagina > 1 && !ultimaPagina) return cargarHistorial({ultimaPagina: true, enfocar});
            aviso('errorHistorialMermas', error.message);
            mensajeTabla('No se pudo cargar el historial.');
            resumen.textContent = 'Error de carga';
        } finally {
            if (version === versionHistorial) {
                tabla.setAttribute('aria-busy', 'false');
                if (enfocar && document.activeElement === document.body) resumen.focus({preventScroll: true});
            }
        }
    }
    el('mostrarFiltrosMermas').addEventListener('click', () => {
        const abierto = el('controlesFiltrosMermas').classList.toggle('is-open');
        el('mostrarFiltrosMermas').setAttribute('aria-expanded', String(abierto));
    });
    el('buscarMermas').addEventListener('input', () => {
        clearTimeout(temporizadorHistorial);
        ++versionHistorial;
        pagina = 1;
        prepararHistorial();
        temporizadorHistorial = setTimeout(() => cargarHistorial(), 300);
    });
    ['bodegaHistorialMermas', 'motivoMermas', 'desdeMermas', 'hastaMermas'].forEach(id => el(id).addEventListener('change', () => {
        pagina = 1;
        cargarHistorial();
    }));
    el('filtrosMermas').addEventListener('submit', evento => { evento.preventDefault(); pagina = 1; cargarHistorial(); });
    el('limpiarFiltrosMermas').addEventListener('click', () => { el('filtrosMermas').reset(); pagina = 1; cargarHistorial(); });
    paginador.addEventListener('click', evento => {
        const boton = evento.target.closest('button[data-page]');
        if (!boton || boton.disabled) return;
        const numero = Number(boton.dataset.page);
        if (!Number.isInteger(numero) || numero < 1 || numero > Math.ceil(total / TAMANO_PAGINA)) return;
        pagina = numero;
        cargarHistorial({enfocar: evento.detail === 0});
        el('filtrosMermas').scrollIntoView({block: 'start', behavior: 'auto'});
    });
    tabla.addEventListener('click', async evento => {
        const boton = evento.target.closest('button[data-detalle]');
        if (!boton) return;
        origenDetalle = boton;
        const version = ++versionDetalle;
        el('estadoDetalleMerma').textContent = 'Cargando detalle...';
        el('datosDetalleMerma').classList.add('d-none');
        modalDetalle.show();
        try {
            const json = await consultar('/api/v1/productos/mermas/' + encodeURIComponent(boton.dataset.detalle) + '/');
            if (version !== versionDetalle) return;
            const m = json.data;
            const datos = {Id: '#' + m.id, Producto: m.producto, Sku: m.sku, Cantidad: '−' + m.cantidad + ' unidades',
                Motivo: m.motivo, Observacion: m.observacion || 'Sin observación.', Fecha: m.fecha,
                Responsable: m.responsable, Bodega: m.bodega, Estado: m.estado};
            Object.entries(datos).forEach(([id, texto]) => { el('detalleMerma' + id).textContent = texto; });
            el('datosDetalleMerma').classList.remove('d-none');
            el('estadoDetalleMerma').textContent = '';
        } catch (error) {
            if (version === versionDetalle) el('estadoDetalleMerma').textContent = error.message;
        }
    });
    detalleEl.addEventListener('hidden.bs.modal', () => {
        ++versionDetalle;
        if (origenDetalle?.isConnected) origenDetalle.focus({preventScroll: true});
    });

    function actualizarResumen() {
        const cantidad = Number(el('mermaCantidad').value);
        const valida = Number.isInteger(cantidad) && cantidad > 0 && cantidad <= 2147483647;
        const disponible = producto ? Number(producto.stock_disponible) : 0;
        const suficiente = producto && valida && cantidad <= disponible;
        el('mermaStockDisponible').textContent = producto ?
            'Disponible en ' + producto.bodega + ': ' + disponible + ' unidades.' :
            'Selecciona un producto para consultar el stock de la bodega elegida.';
        const texto = !producto ? 'Selecciona un producto e indica la cantidad a descontar.' :
            !valida ? 'Ingresa una cantidad entera mayor que cero.' :
            !suficiente ? 'Stock insuficiente: solicitas ' + cantidad + ' y hay ' + disponible + ' unidades disponibles.' :
            'Se descontarán ' + cantidad + ' unidades de ' + producto.nombre + '. Stock disponible en ' + producto.bodega +
                ': ' + disponible + '. Stock restante estimado: ' + (disponible - cantidad) + ' unidades.';
        el('mermaResumenConfirmacion').textContent = texto;
        el('mermaResumenConfirmacion').classList.toggle('alert-warning', Boolean(producto && !suficiente));
        el('mermaResumenConfirmacion').classList.toggle('alert-info', !producto || Boolean(suficiente));
        const completa = bodegasListas && el('mermaBodega').value && suficiente && el('mermaMotivo').value && el('mermaObservacion').value.trim();
        el('btnGuardarMerma').disabled = esperando || registrado || cargandoProductos || !completa;
        el('btnGuardarMerma').textContent = esperando ? 'Registrando merma...' : registrado ? 'Merma registrada' : 'Confirmar merma';
        return Boolean(completa);
    }
    function prepararProductos() {
        cargandoProductos = true;
        producto = null;
        productos.clear();
        select.replaceChildren(new Option('Buscando productos...', ''));
        select.disabled = true;
        el('mermaProductosAnterior').disabled = true;
        el('mermaProductosSiguiente').disabled = true;
        el('resumenProductosMerma').textContent = 'Cargando...';
        actualizarResumen();
    }
    function etiquetaProducto(item) {
        return item.sku + ' · ' + item.nombre + ' (Disponible: ' + item.stock_disponible + ')';
    }
    async function cargarProductos({ultimaPagina = false} = {}) {
        clearTimeout(temporizadorProductos);
        const version = ++versionProductos;
        prepararProductos();
        const bodega = el('mermaBodega').value;
        if (!bodegasListas || !bodega) { cargandoProductos = false; select.replaceChildren(new Option('Selecciona una bodega activa', '')); return; }
        const params = new URLSearchParams({page: ultimaPagina ? 'last' : String(paginaProductos)});
        params.set('bodega', bodega);
        const consulta = el('mermaBuscarProducto').value.trim();
        if (consulta) params.set('search', consulta);
        try {
            const json = await consultar('/api/v1/productos/mermas/productos/?' + params);
            if (version !== versionProductos || el('mermaBodega').value !== bodega) return;
            if (!Array.isArray(json.results) || !Number.isInteger(json.count)) throw new Error('La respuesta del catálogo no es válida.');
            totalProductos = json.count;
            if (ultimaPagina) paginaProductos = Math.max(1, Math.ceil(totalProductos / TAMANO_PAGINA));
            if (json.results.some(item => item.bodega_id && String(item.bodega_id) !== bodega)) throw new Error('La respuesta corresponde a otra bodega. Vuelve a consultar el producto.');
            productos = new Map(json.results.map(item => [String(item.id), {...item, bodega_id: Number(bodega)}]));
            select.replaceChildren(new Option(json.results.length ? 'Selecciona un producto...' : 'No se encontraron productos', ''));
            json.results.forEach(item => select.add(new Option(etiquetaProducto(item), item.id)));
            const primero = json.results.length ? (paginaProductos - 1) * TAMANO_PAGINA + 1 : 0;
            el('resumenProductosMerma').textContent = totalProductos ?
                primero + '–' + (primero + json.results.length - 1) + ' de ' + totalProductos + ' productos' : '0 productos';
            el('mermaProductosAnterior').disabled = esperando || paginaProductos <= 1;
            el('mermaProductosSiguiente').disabled = esperando || paginaProductos >= Math.ceil(totalProductos / TAMANO_PAGINA);
            aviso('errorNuevaMerma', '');
        } catch (error) {
            if (version !== versionProductos) return;
            if (error.status === 404 && paginaProductos > 1 && !ultimaPagina) return cargarProductos({ultimaPagina: true});
            select.replaceChildren(new Option('No se pudieron cargar los productos', ''));
            el('resumenProductosMerma').textContent = 'Error de carga';
            aviso('errorNuevaMerma', error.message);
        } finally {
            if (version === versionProductos) {
                cargandoProductos = false;
                select.disabled = esperando || productos.size === 0;
                actualizarResumen();
            }
        }
    }
    el('mermaBuscarProducto').addEventListener('input', () => {
        clearTimeout(temporizadorProductos);
        ++versionProductos;
        paginaProductos = 1;
        aviso('errorNuevaMerma', '');
        prepararProductos();
        temporizadorProductos = setTimeout(() => cargarProductos(), 300);
    });
    select.addEventListener('change', () => {
        producto = productos.get(select.value) || null;
        aviso('errorNuevaMerma', '');
        actualizarResumen();
    });
    [['mermaProductosAnterior', -1], ['mermaProductosSiguiente', 1]].forEach(([id, cambio]) => {
        el(id).addEventListener('click', () => {
            if (cargandoProductos || esperando || el(id).disabled) return;
            paginaProductos += cambio;
            cargarProductos();
        });
    });
    ['mermaCantidad', 'mermaObservacion', 'mermaMotivo'].forEach(id => el(id).addEventListener('input', () => {
        aviso('errorNuevaMerma', '');
        actualizarResumen();
    }));
    modalEl.addEventListener('show.bs.modal', evento => {
        if (!bodegasListas) { evento.preventDefault(); return; }
        formulario.reset();
        const elegida = el('bodegaHistorialMermas').value;
        el('mermaBodega').value = bodegas.some(b => String(b.id) === elegida) ? elegida : predeterminada;
        registrado = false;
        producto = null;
        paginaProductos = 1;
        aviso('errorNuevaMerma', '');
        cargarProductos();
    });
    modalEl.addEventListener('shown.bs.modal', () => {
        if (window.matchMedia('(min-width: 992px)').matches) el('mermaBuscarProducto').focus();
    });
    modalEl.addEventListener('hide.bs.modal', evento => { if (esperando) evento.preventDefault(); });
    modalEl.addEventListener('hidden.bs.modal', () => {
        ++versionProductos;
        clearTimeout(temporizadorProductos);
    });
    function bloquearFormulario(bloqueado) {
        modalEl.querySelectorAll('input, select, textarea, button').forEach(control => { control.disabled = bloqueado; });
        if (!bloqueado) {
            select.disabled = cargandoProductos || productos.size === 0;
            el('mermaProductosAnterior').disabled = cargandoProductos || paginaProductos <= 1;
            el('mermaProductosSiguiente').disabled = cargandoProductos || paginaProductos >= Math.ceil(totalProductos / TAMANO_PAGINA);
        }
        actualizarResumen();
    }
    formulario.addEventListener('submit', async evento => {
        evento.preventDefault();
        if (esperando || registrado || cargandoProductos || !modalEl.classList.contains('show') || !actualizarResumen() || !formulario.reportValidity()) return;
        const payload = {producto_id: Number(select.value), bodega_id: producto.bodega_id, cantidad: Number(el('mermaCantidad').value),
            motivo: el('mermaMotivo').value, observacion: el('mermaObservacion').value.trim()};
        esperando = true;
        bloquearFormulario(true);
        aviso('errorNuevaMerma', '');
        try {
            const json = await consultar('/api/v1/productos/mermas/', {
                method: 'POST', headers: {...headers, 'Content-Type': 'application/json'}, body: JSON.stringify(payload),
            });
            producto.stock_disponible = json.data.stock_restante;
            registrado = true;
            esperando = false;
            modal.hide();
            window.dispatchEvent(new Event('smartstock:notifications-changed'));
            pagina = 1;
            cargarHistorial();
        } catch (error) {
            if (Number.isInteger(error.datos?.errores?.stock_disponible) && producto) {
                producto.stock_disponible = error.datos.errores.stock_disponible;
                if (select.selectedOptions[0]) select.selectedOptions[0].textContent = etiquetaProducto(producto);
            }
            aviso('errorNuevaMerma', error.message);
        } finally {
            esperando = false;
            bloquearFormulario(false);
        }
    });
    async function cargarBodegas() {
        bodegasListas = false; el('btnNuevaMerma').disabled = true; el('reintentarBodegasMermas').hidden = true;
        el('estadoBodegasMermas').textContent = 'Cargando bodegas...';
        try {
            const json = await consultar('/api/v1/bodegas/opciones/'), d = json.data;
            if (!d || !Array.isArray(d.bodegas) || !Array.isArray(d.bodegas_historial)) throw new Error('No se pudieron leer las bodegas.');
            bodegas = d.bodegas; predeterminada = String(d.bodega_predeterminada || bodegas[0]?.id || '');
            el('mermaBodega').replaceChildren(...bodegas.map(b => new Option(b.etiqueta || b.nombre, String(b.id), String(b.id) === predeterminada)));
            if (!bodegas.length) el('mermaBodega').append(new Option('Sin bodegas activas', ''));
            el('mermaBodega').value = predeterminada; el('mermaBodega').disabled = !bodegas.length;
            const filtro = el('bodegaHistorialMermas'), anterior = bodegaInicial || filtro.value;
            filtro.replaceChildren(new Option('Todas', ''), ...d.bodegas_historial.map(b => new Option((b.etiqueta || b.nombre) + (b.activa === false ? ' (inactiva)' : ''), String(b.id))));
            filtro.value = d.bodegas_historial.some(b => String(b.id) === anterior) ? anterior : '';
            if (bodegaInicial) {
                bodegaInicial = null;
                cargarHistorial();
            }
            bodegasListas = bodegas.length > 0 && d.operar?.merma !== false;
            el('btnNuevaMerma').disabled = !bodegasListas;
            el('estadoBodegasMermas').textContent = !bodegas.length ? 'Crea o reactiva una bodega en Bodegas para registrar mermas.' : d.operar?.merma === false ? 'No tienes permiso para registrar mermas.' : '';
        } catch (error) { el('estadoBodegasMermas').textContent = error.message; el('reintentarBodegasMermas').hidden = false; }
    }
    el('mermaBodega').addEventListener('change', () => { paginaProductos = 1; producto = null; cargarProductos(); });
    el('reintentarBodegasMermas').addEventListener('click', cargarBodegas);
    if (!bodegaInicial) cargarHistorial();
    cargarBodegas();
});

