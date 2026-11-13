document.addEventListener('DOMContentLoaded', async () => {
    'use strict';
    if (window.SmartStockNavegacion && !await window.SmartStockNavegacion.lista) return;
    const token = localStorage.getItem('access_token');
    if (!token) { window.location.href = '/'; return; }
    const usuario = (() => { try { return JSON.parse(localStorage.getItem('usuario') || '{}'); } catch (_) { return {}; } })();
    if (!window.SmartStockNavegacion && usuario.rol_nombre && usuario.rol_nombre.toLowerCase() !== 'administrador') {
        document.querySelectorAll('a[href="/usuarios/"], a[href="/admin/"]').forEach(link => {
            if (link.closest('li')) link.closest('li').hidden = true;
        });
    }
    const el = id => document.getElementById(id);
    const headers = {Authorization: 'Bearer ' + token};
    const escritorio = () => window.matchMedia('(min-width: 992px)').matches;
    const modal = id => bootstrap.Modal.getOrCreateInstance(el(id));
    const modalAccion = modal('modalAccionMovimiento');
    const modalManual = modal('modalIngresoManual');
    const modalDetalle = modal('modalDetalleMovimiento');
    const tabla = el('listaMovimientos');
    const paginador = el('paginacionMovimientos');
    const resumen = el('resumenMovimientos');
    const inputEscaner = el('inputEscaner');
    let paginaActual = 1;
    let totalResultados = 0;
    let solicitudHistorial = 0;
    let solicitudDetalle = 0;
    let temporizadorBusqueda;
    let resolviendo = false;
    let guardando = false;
    let registroConfirmado = false;
    let productoActual = null;
    let bodegaInicial = new URLSearchParams(location.search).get('bodega');
    let bodegasListas = false;
    let solicitudStock = 0;
    let consultandoStock = false;
    let stockVigente = false;
    const TAMANO_PAGINA = 25;

    function actualizarIndicadorFiltros() {
        const activos = ['bodegaHistorialMovimientos', 'tipoMovimientos', 'desdeMovimientos', 'hastaMovimientos'].filter(id => el(id).value).length;
        el('mostrarFiltrosMovimientos').textContent = 'Filtros' + (activos ? ' (' + activos + ')' : '');
    }
    el('mostrarFiltrosMovimientos').addEventListener('click', () => {
        const abierto = el('controlesFiltrosMovimientos').classList.toggle('is-open');
        el('mostrarFiltrosMovimientos').setAttribute('aria-expanded', String(abierto));
    });

    const mostrarMensaje = (id, texto) => {
        const elemento = el(id);
        elemento.textContent = texto || '';
        elemento.classList.toggle('d-none', !texto);
    };
    const nodo = (tag, clase, texto) => {
        const elemento = document.createElement(tag);
        if (clase) elemento.className = clase;
        if (texto !== undefined) elemento.textContent = texto;
        return elemento;
    };
    async function leerRespuesta(respuesta) {
        const json = await respuesta.json();
        if (!respuesta.ok) {
            const error = new Error(json.mensaje || json.detail || 'No se pudo completar la consulta.');
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
        resumen.textContent = 'Cargando movimientos...';
        mostrarMensaje('errorHistorialMovimientos', '');
        mensajeTabla('Cargando movimientos...');
    }
    function renderizarFila(mov) {
        const fila = nodo('tr', 'ss-mov-row');
        const fecha = nodo('td', 'ss-mov-date text-muted');
        const partes = String(mov.fecha || '').split(' ');
        fecha.append(nodo('span', '', partes[0] || ''), nodo('span', 'ss-mov-date-time', partes[1] || ''));
        const tipo = nodo('td', 'ss-mov-type');
        const entrada = mov.tipo === 'ENTRADA';
        tipo.appendChild(nodo('span', 'badge rounded-pill ' + (entrada ? 'badge-soft-success' : 'badge-soft-danger'), entrada ? 'Entrada' : 'Salida'));
        const producto = nodo('td', 'ss-mov-product');
        producto.append(nodo('strong', '', mov.producto), nodo('span', 'ss-mov-sku', 'SKU: ' + mov.sku));
        producto.append(nodo('span', 'ss-mov-sku', mov.bodega));
        const cantidad = nodo('td', 'ss-mov-quantity ' + (entrada ? 'text-success' : 'text-danger'));
        cantidad.append(nodo('span', '', (entrada ? '+' : '−') + mov.cantidad), nodo('span', 'ss-mov-units', ' unid.'));
        const operador = nodo('td', 'ss-mov-user', mov.usuario);
        const acciones = nodo('td', 'ss-mov-actions');
        const boton = nodo('button', 'btn btn-sm btn-outline-secondary', 'Ver detalle');
        boton.type = 'button';
        boton.dataset.detalle = String(mov.id);
        boton.setAttribute('aria-label', 'Ver detalle del movimiento ' + mov.movimiento_id + ' de ' + mov.producto);
        acciones.appendChild(boton);
        fila.append(fecha, tipo, producto, cantidad, operador, acciones);
        return fila;
    }
    function renderizarPaginacion(totalPaginas) {
        paginador.replaceChildren();
        if (totalPaginas <= 1) return;
        const lista = nodo('ul', 'pagination');
        const boton = (texto, pagina, deshabilitado, actual = false) => {
            const item = nodo('li', 'page-item' + (actual ? ' active' : ''));
            const control = nodo('button', 'page-link', texto);
            control.type = 'button';
            control.dataset.page = String(pagina);
            control.disabled = deshabilitado || actual;
            control.setAttribute('aria-label', texto === 'Anterior' ? 'Página anterior' : texto === 'Siguiente' ? 'Página siguiente' : 'Ir a página ' + pagina);
            if (actual) control.setAttribute('aria-current', 'page');
            item.appendChild(control);
            lista.appendChild(item);
        };
        boton('Anterior', paginaActual - 1, paginaActual === 1);
        const paginas = new Set([1, totalPaginas]);
        for (let n = Math.max(1, paginaActual - 1); n <= Math.min(totalPaginas, paginaActual + 1); n++) paginas.add(n);
        if (paginaActual <= 2 && totalPaginas >= 3) paginas.add(3);
        let anterior = 0;
        [...paginas].sort((a, b) => a - b).forEach(n => {
            if (anterior && n > anterior + 1) {
                const item = nodo('li', 'page-item');
                const puntos = nodo('span', 'ss-mov-ellipsis', '…');
                puntos.setAttribute('aria-hidden', 'true');
                item.appendChild(puntos);
                lista.appendChild(item);
            }
            boton(String(n), n, false, n === paginaActual);
            anterior = n;
        });
        boton('Siguiente', paginaActual + 1, paginaActual === totalPaginas);
        paginador.appendChild(lista);
    }
    async function cargarHistorial({ultimaPagina = false, enfocarResumen = false} = {}) {
        clearTimeout(temporizadorBusqueda);
        actualizarIndicadorFiltros();
        const solicitud = ++solicitudHistorial;
        prepararHistorial();
        const desde = el('desdeMovimientos').value;
        const hasta = el('hastaMovimientos').value;
        if (desde && hasta && desde > hasta) {
            mostrarMensaje('errorHistorialMovimientos', 'La fecha inicial no puede ser posterior a la final.');
            mensajeTabla('Revisa el rango de fechas.');
            resumen.textContent = '';
            tabla.setAttribute('aria-busy', 'false');
            return;
        }
        const parametros = new URLSearchParams({page: ultimaPagina ? 'last' : String(paginaActual)});
        const consulta = el('buscarMovimientos').value.trim();
        const tipo = el('tipoMovimientos').value;
        if (consulta) parametros.set('search', consulta);
        if (tipo) parametros.set('tipo', tipo);
        if (desde) parametros.set('desde', desde);
        if (hasta) parametros.set('hasta', hasta);
        if (el('bodegaHistorialMovimientos').value) parametros.set('bodega', el('bodegaHistorialMovimientos').value);
        try {
            const res = await fetch('/api/v1/productos/movimientos/?' + parametros, {headers});
            if (solicitud !== solicitudHistorial) return;
            if (res.status === 404 && paginaActual > 1 && !ultimaPagina) {
                return cargarHistorial({ultimaPagina: true, enfocarResumen});
            }
            const data = await leerRespuesta(res);
            if (solicitud !== solicitudHistorial) return;
            if (!Array.isArray(data.results) || !Number.isInteger(data.count) || data.count < 0) throw new Error('La respuesta del historial no es válida.');
            totalResultados = data.count;
            const paginas = Math.ceil(totalResultados / TAMANO_PAGINA);
            if (ultimaPagina) paginaActual = Math.max(1, paginas);
            if (data.results.length) {
                tabla.replaceChildren(...data.results.map(renderizarFila));
                const primero = (paginaActual - 1) * TAMANO_PAGINA + 1;
                resumen.textContent = 'Mostrando ' + primero + '–' + (primero + data.results.length - 1) + ' de ' + totalResultados + ' movimientos';
            } else {
                mensajeTabla('No hay movimientos para estos filtros.');
                resumen.textContent = '0 movimientos';
            }
            renderizarPaginacion(paginas);
        } catch (error) {
            if (solicitud !== solicitudHistorial) return;
            mostrarMensaje('errorHistorialMovimientos', error.message || 'No se pudo cargar el historial.');
            mensajeTabla('No se pudieron cargar los movimientos.');
            resumen.textContent = 'Error de carga';
        } finally {
            if (solicitud === solicitudHistorial) {
                tabla.setAttribute('aria-busy', 'false');
                if (enfocarResumen && document.activeElement === document.body) resumen.focus({preventScroll: true});
            }
        }
    }
    el('buscarMovimientos').addEventListener('input', () => {
        clearTimeout(temporizadorBusqueda);
        ++solicitudHistorial;
        paginaActual = 1;
        prepararHistorial();
        temporizadorBusqueda = setTimeout(() => cargarHistorial(), 300);
    });
    ['bodegaHistorialMovimientos', 'tipoMovimientos', 'desdeMovimientos', 'hastaMovimientos'].forEach(id => {
        el(id).addEventListener('change', () => { paginaActual = 1; cargarHistorial(); });
    });
    el('filtrosMovimientos').addEventListener('submit', evento => {
        evento.preventDefault();
        paginaActual = 1;
        cargarHistorial();
    });
    el('limpiarFiltrosMovimientos').addEventListener('click', () => {
        el('filtrosMovimientos').reset();
        paginaActual = 1;
        cargarHistorial();
    });
    paginador.addEventListener('click', evento => {
        const boton = evento.target.closest('button[data-page]');
        if (!boton || boton.disabled) return;
        const pagina = Number(boton.dataset.page);
        if (!Number.isInteger(pagina) || pagina < 1 || pagina > Math.ceil(totalResultados / TAMANO_PAGINA)) return;
        paginaActual = pagina;
        cargarHistorial({enfocarResumen: evento.detail === 0});
        el('filtrosMovimientos').scrollIntoView({block: 'start', behavior: 'auto'});
    });
    tabla.addEventListener('click', async evento => {
        const boton = evento.target.closest('button[data-detalle]');
        if (!boton) return;
        const solicitud = ++solicitudDetalle;
        el('datosDetalleMovimiento').classList.add('d-none');
        el('estadoDetalleMovimiento').textContent = 'Cargando detalle...';
        modalDetalle.show();
        try {
            const json = await leerRespuesta(await fetch('/api/v1/productos/movimientos/' + encodeURIComponent(boton.dataset.detalle) + '/', {headers}));
            if (solicitud !== solicitudDetalle) return;
            const mov = json.data;
            const campos = {
                detalleMovId: '#' + mov.movimiento_id, detalleMovProducto: mov.producto,
                detalleMovSku: mov.sku, detalleMovTipo: mov.tipo === 'ENTRADA' ? 'Entrada' : 'Salida',
                detalleMovCantidad: (mov.tipo === 'ENTRADA' ? '+' : '−') + mov.cantidad + ' unidades',
                detalleMovFecha: mov.fecha, detalleMovUsuario: mov.usuario, detalleMovBodega: mov.bodega,
                detalleMovReferencia: mov.documento_referencia || 'Sin referencia u observación.',
            };
            Object.entries(campos).forEach(([id, texto]) => { el(id).textContent = texto; });
            el('estadoDetalleMovimiento').textContent = '';
            el('datosDetalleMovimiento').classList.remove('d-none');
        } catch (error) {
            if (solicitud === solicitudDetalle) el('estadoDetalleMovimiento').textContent = error.message || 'No se pudo cargar el detalle.';
        }
    });
    el('modalDetalleMovimiento').addEventListener('hidden.bs.modal', () => { ++solicitudDetalle; });

    function actualizarControlesEscaner() {
        const sinBodega = !bodegasListas || !el('bodegaMovimiento').value;
        // El producto se libera en hidden.bs.modal, al terminar el cierre.
        const ocupado = resolviendo || guardando || productoActual !== null;
        inputEscaner.disabled = ocupado || sinBodega;
        el('bodegaMovimiento').disabled = ocupado || !bodegasListas || Boolean(document.querySelector('.modal.show'));
        document.querySelectorAll('.ss-movement-terminal .ss-scan-code, #btn-movimiento-manual').forEach(b => { b.disabled = ocupado || sinBodega; });
    }
    function devolverFocoEscaner() {
        actualizarControlesEscaner();
        if (escritorio() && !inputEscaner.disabled && !document.querySelector('.modal.show')) inputEscaner.focus();
    }
    async function buscarProductoCodigo(codigo, bodega = el('bodegaMovimiento').value) {
        if (!bodegasListas || !bodega) throw new Error('Selecciona una bodega activa para registrar el movimiento.');
        const params = new URLSearchParams({codigo, bodega});
        const json = await leerRespuesta(await fetch('/api/v1/productos/resolver-movimiento/?' + params, {headers, cache: 'no-store'}));
        if (el('bodegaMovimiento').value !== bodega || String(json.data?.bodega_id) !== bodega) throw new Error('La bodega cambió. Vuelve a consultar el producto.');
        if (!Number.isSafeInteger(json.data?.id) || json.data.id < 1 || !Number.isSafeInteger(json.data.stock_disponible) || typeof json.data.nombre !== 'string' || typeof json.data.sku !== 'string' || typeof json.data.bodega !== 'string') throw new Error('No se pudieron leer el producto y sus existencias. Vuelve a consultar.');
        return json.data;
    }
    function actualizarConfirmacion() {
        const salida = el('movTipo').value === 'SALIDA';
        el('movEtiquetaBodega').textContent = salida ? 'Bodega de salida' : 'Bodega de recepción';
        el('movAyudaBodega').textContent = salida ? 'Las unidades se descontarán de esta bodega.' : 'Las unidades ingresarán a esta bodega.';
        el('movBodega').disabled = guardando || registroConfirmado || !bodegasListas;
        el('reintentarStockMovimiento').disabled = guardando || consultandoStock;
        const bodega = el('movBodega').value;
        const contextoValido = productoActual && stockVigente && !consultandoStock && String(productoActual.bodega_id) === bodega;
        el('reintentarStockMovimiento').hidden = !productoActual || !bodega || consultandoStock || contextoValido || registroConfirmado;
        const confirmar = el('confirmarMovimiento');
        const etiqueta = guardando ? 'Guardando...' : salida ? 'Confirmar salida' : 'Confirmar entrada';
        // WebKit puede perder el clic si se reemplaza el texto al salir de Cantidad.
        if (confirmar.textContent !== etiqueta) confirmar.textContent = etiqueta;
        if (!contextoValido) {
            const nombre = el('movBodega').selectedOptions[0]?.textContent || 'la bodega seleccionada';
            el('movStockDisponible').textContent = consultandoStock ? 'Consultando existencias en ' + nombre + '...' : 'Stock pendiente de consulta.';
            el('movResumenConfirmacion').textContent = !bodega ? 'Selecciona una bodega activa para registrar el movimiento.' : consultandoStock ? 'Espera la consulta de stock de ' + nombre + ' antes de confirmar.' : 'Vuelve a consultar las existencias de la bodega antes de confirmar.';
            el('movResumenConfirmacion').classList.add('alert-warning');
            el('movResumenConfirmacion').classList.remove('alert-info');
            confirmar.disabled = true;
            return false;
        }
        const cantidad = Number(el('movCantidad').value);
        const stock = Number(productoActual.stock_disponible);
        const valida = Number.isInteger(cantidad) && cantidad > 0 && cantidad <= 2147483647;
        const suficiente = !salida || cantidad <= stock;
        const nuevoStock = salida ? stock - cantidad : stock + cantidad;
        const dentroDelLimite = nuevoStock >= 0 && nuevoStock <= 2147483647;
        el('movStockDisponible').textContent = 'Disponible en ' + productoActual.bodega + ': ' + stock + ' unidades';
        el('movResumenConfirmacion').textContent = !valida ? 'Ingresa una cantidad entera mayor que cero.' :
            !suficiente ? 'Stock insuficiente: solicitas ' + cantidad + ' y hay ' + stock + ' unidades disponibles.' :
            !dentroDelLimite ? 'La cantidad supera el límite de stock permitido.' :
            (salida ? 'Salida' : 'Entrada') + ' de ' + cantidad + ' unidades de ' + productoActual.nombre +
            '. Stock estimado en ' + productoActual.bodega + ': ' + (salida ? stock - cantidad : stock + cantidad) + ' unidades.';
        el('movResumenConfirmacion').classList.toggle('alert-warning', !valida || !suficiente || !dentroDelLimite);
        el('movResumenConfirmacion').classList.toggle('alert-info', valida && suficiente && dentroDelLimite);
        confirmar.disabled = guardando || registroConfirmado || !valida || !suficiente || !dentroDelLimite;
        return valida && suficiente && dentroDelLimite;
    }
    async function consultarStockBodega() {
        if (!productoActual || guardando || registroConfirmado || !el('modalAccionMovimiento').classList.contains('show')) return;
        const solicitud = ++solicitudStock, productoId = productoActual.id, bodega = el('movBodega').value;
        stockVigente = false;
        consultandoStock = Boolean(bodega);
        if (bodega) el('bodegaMovimiento').value = bodega;
        mostrarMensaje('movErrorRegistro', '');
        actualizarConfirmacion();
        if (!bodega) return;
        try {
            const producto = await buscarProductoCodigo(productoActual.sku, bodega);
            if (solicitud !== solicitudStock || !el('modalAccionMovimiento').classList.contains('show')) return;
            if (producto.id !== productoId) throw new Error('El código ahora corresponde a otro producto. Cierra el formulario y vuelve a escanear.');
            productoActual = producto;
            stockVigente = true;
            el('movNombreProducto').textContent = producto.nombre;
            el('movSkuProducto').textContent = 'SKU: ' + producto.sku;
        } catch (error) {
            if (solicitud !== solicitudStock) return;
            mostrarMensaje('movErrorRegistro', error.message || 'No se pudieron consultar las existencias de esta bodega.');
        } finally {
            if (solicitud === solicitudStock) { consultandoStock = false; actualizarConfirmacion(); }
        }
    }
    function mostrarProducto(producto) {
        ++solicitudStock;
        productoActual = producto;
        consultandoStock = false;
        stockVigente = true;
        registroConfirmado = false;
        el('movBodega').value = String(producto.bodega_id);
        el('movProductoId').value = producto.id;
        el('movNombreProducto').textContent = producto.nombre;
        el('movSkuProducto').textContent = 'SKU: ' + producto.sku;
        el('movCantidad').value = '1';
        el('movTipo').value = 'ENTRADA';
        el('movObservacion').value = '';
        mostrarMensaje('movErrorRegistro', '');
        actualizarConfirmacion();
        modalAccion.show();
    }
    async function procesarCodigoBarras(codigo) {
        if (!codigo || resolviendo || guardando || productoActual || document.querySelector('.modal.show')) return;
        resolviendo = true;
        actualizarControlesEscaner();
        mostrarMensaje('errorEscaner', '');
        try {
            mostrarProducto(await buscarProductoCodigo(codigo));
        } catch (error) {
            mostrarMensaje('errorEscaner', error.message || 'No se pudo consultar el producto. Inténtalo nuevamente.');
        } finally {
            resolviendo = false;
            actualizarControlesEscaner();
            devolverFocoEscaner();
        }
    }
    inputEscaner.addEventListener('keydown', evento => {
        if (evento.key !== 'Enter') return;
        evento.preventDefault();
        const codigo = inputEscaner.value.trim();
        inputEscaner.value = '';
        procesarCodigoBarras(codigo);
    });
    window.addEventListener('smartstock:barcode-scanned', evento => {
        const codigo = String(evento.detail?.codigo || '').trim();
        inputEscaner.value = '';
        procesarCodigoBarras(codigo);
    });
    el('btn-movimiento-manual').addEventListener('click', () => {
        el('formIngresoManual').reset();
        mostrarMensaje('errorSkuManual', '');
        modalManual.show();
    });
    el('modalIngresoManual').addEventListener('shown.bs.modal', () => { actualizarControlesEscaner(); el('inputSkuManual').focus(); });
    el('inputSkuManual').addEventListener('input', () => mostrarMensaje('errorSkuManual', ''));
    el('formIngresoManual').addEventListener('submit', async evento => {
        evento.preventDefault();
        if (resolviendo || guardando) return;
        const codigo = el('inputSkuManual').value.trim();
        if (!codigo) return;
        resolviendo = true;
        actualizarControlesEscaner();
        const boton = el('formIngresoManual').querySelector('[type="submit"]');
        boton.disabled = true;
        try {
            const producto = await buscarProductoCodigo(codigo);
            el('modalIngresoManual').addEventListener('hidden.bs.modal', () => mostrarProducto(producto), {once: true});
            resolviendo = false;
            modalManual.hide();
        } catch (error) {
            mostrarMensaje('errorSkuManual', error.message || 'No se pudo consultar el producto.');
        } finally {
            resolviendo = false;
            boton.disabled = false;
            actualizarControlesEscaner();
        }
    });
    el('modalIngresoManual').addEventListener('hide.bs.modal', evento => { if (resolviendo) evento.preventDefault(); });
    el('modalAccionMovimiento').addEventListener('shown.bs.modal', () => { actualizarControlesEscaner(); el('movTipo').focus(); });
    el('modalIngresoManual').addEventListener('hidden.bs.modal', actualizarControlesEscaner);
    el('modalAccionMovimiento').addEventListener('hide.bs.modal', evento => { if (guardando) evento.preventDefault(); });
    el('modalAccionMovimiento').addEventListener('hidden.bs.modal', () => {
        ++solicitudStock; consultandoStock = false; stockVigente = false; productoActual = null;
        actualizarConfirmacion(); devolverFocoEscaner();
    });
    el('movBodega').addEventListener('change', consultarStockBodega);
    el('reintentarStockMovimiento').addEventListener('click', consultarStockBodega);
    ['movTipo', 'movCantidad'].forEach(id => ['input', 'change'].forEach(tipo => el(id).addEventListener(tipo, () => {
        mostrarMensaje('movErrorRegistro', '');
        actualizarConfirmacion();
    })));
    function bloquearFormulario(bloqueado) {
        el('modalAccionMovimiento').querySelectorAll('input, select, button').forEach(control => { control.disabled = bloqueado; });
        actualizarControlesEscaner();
        actualizarConfirmacion();
    }
    el('formRegistrarMovimiento').addEventListener('submit', async evento => {
        evento.preventDefault();
        if (guardando || registroConfirmado || !el('modalAccionMovimiento').classList.contains('show') || !actualizarConfirmacion() || !el('formRegistrarMovimiento').reportValidity()) return;
        const payload = {
            producto_id: productoActual.id,
            bodega_id: Number(el('movBodega').value),
            tipo_movimiento: el('movTipo').value,
            cantidad: Number(el('movCantidad').value),
            observacion: el('movObservacion').value.trim(),
        };
        guardando = true;
        bloquearFormulario(true);
        mostrarMensaje('movErrorRegistro', '');
        try {
            const json = await leerRespuesta(await fetch('/api/v1/productos/registrar-movimiento/', {
                method: 'POST', headers: {...headers, 'Content-Type': 'application/json'}, body: JSON.stringify(payload),
            }));
            productoActual.stock_disponible = json.data.stock_restante;
            registroConfirmado = true;
            guardando = false;
            modalAccion.hide();
            paginaActual = 1;
            cargarHistorial();
            window.dispatchEvent(new Event('smartstock:notifications-changed'));
        } catch (error) {
            if (Number.isInteger(error.datos?.errores?.stock_disponible)) productoActual.stock_disponible = error.datos.errores.stock_disponible;
            mostrarMensaje('movErrorRegistro', error.message || 'No se pudo confirmar el movimiento. Revisa el historial antes de reintentar si se perdió la conexión.');
        } finally {
            guardando = false;
            bloquearFormulario(false);
        }
    });

    async function cargarBodegas() {
        bodegasListas = false; actualizarControlesEscaner(); el('reintentarBodegasMovimiento').hidden = true;
        el('estadoBodegasMovimiento').textContent = 'Cargando bodegas...';
        try {
            const json = await leerRespuesta(await fetch('/api/v1/bodegas/opciones/', {headers})), d = json.data;
            if (!d || !Array.isArray(d.bodegas) || !Array.isArray(d.bodegas_historial)) throw new Error('No se pudieron leer las bodegas.');
            const selector = el('bodegaMovimiento');
            const previa = selector.value || bodegaInicial || String(d.bodega_predeterminada || '');
            const bodegaInicialInvalida = Boolean(bodegaInicial && !d.bodegas.some(b => String(b.id) === bodegaInicial));
            for (const id of ['bodegaMovimiento', 'movBodega']) el(id).replaceChildren(...d.bodegas.map(b => new Option(b.etiqueta || b.nombre, String(b.id))));
            if (!d.bodegas.length) selector.append(new Option('Sin bodegas activas', ''));
            else if (bodegaInicialInvalida) selector.prepend(new Option('Selecciona una bodega', ''));
            selector.value = d.bodegas.some(b => String(b.id) === previa) ? previa :
                bodegaInicialInvalida ? '' : String(d.bodegas[0]?.id || '');
            bodegaInicial = null;
            const filtro = el('bodegaHistorialMovimientos'), anterior = filtro.value;
            filtro.replaceChildren(new Option('Todas', ''), ...d.bodegas_historial.map(b => new Option((b.etiqueta || b.nombre) + (b.activa === false ? ' (inactiva)' : ''), String(b.id))));
            filtro.value = d.bodegas_historial.some(b => String(b.id) === anterior) ? anterior : '';
            bodegasListas = d.bodegas.length > 0;
            el('estadoBodegasMovimiento').textContent = bodegaInicialInvalida && bodegasListas
                ? 'La bodega del enlace no está disponible. Selecciona otra para continuar.'
                : bodegasListas ? 'Al cambiar la bodega aquí, también se filtra el historial. Puedes elegir «Todas» en el historial para ver los demás movimientos.' : 'Crea o reactiva una bodega en Bodegas para registrar movimientos.';
        } catch (error) { el('estadoBodegasMovimiento').textContent = error.message; el('reintentarBodegasMovimiento').hidden = false; }
        finally { actualizarControlesEscaner(); }
    }
    el('bodegaMovimiento').addEventListener('change', () => {
        productoActual = null;
        inputEscaner.value = '';
        mostrarMensaje('errorEscaner', '');
        actualizarControlesEscaner();
        el('bodegaHistorialMovimientos').value = el('bodegaMovimiento').value;
        paginaActual = 1;
        cargarHistorial();
    });
    el('reintentarBodegasMovimiento').addEventListener('click', cargarBodegas);
    cargarHistorial();
    cargarBodegas();
    devolverFocoEscaner();
});

