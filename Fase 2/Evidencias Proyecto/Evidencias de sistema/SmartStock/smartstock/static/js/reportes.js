/* Reportes: la consulta visible y las exportaciones usan los mismos filtros. */
document.addEventListener('DOMContentLoaded', async () => {
    'use strict';
    if (window.SmartStockNavegacion && !await window.SmartStockNavegacion.lista) return;
    if (!localStorage.getItem('access_token')) { window.location.replace('/'); return; }
    const api = window.SmartStockReportes, el = id => document.getElementById(id);
    const crear = (tag, clase = '', texto) => { const n = document.createElement(tag); n.className = clase; if (texto !== undefined) n.textContent = String(texto ?? ''); return n; };
    let usuario = {}; try { usuario = JSON.parse(localStorage.getItem('usuario') || '{}') || {}; } catch (_) {}
    el('user-name-sidebar').textContent = usuario.nombre_completo || 'Usuario';
    el('user-role-sidebar').textContent = usuario.rol_nombre || 'Sin rol';
    el('user-avatar').src = 'https://ui-avatars.com/api/?name=' + encodeURIComponent(usuario.nombre_completo || 'Usuario') + '&background=0f766e&color=fff';
    const admin = usuario.is_superuser === true || usuario.rol === 'administrador' || String(usuario.rol_nombre).toLowerCase() === 'administrador';
    el('menu-auditoria').hidden = el('menu-usuarios').hidden = !admin;
    el('menu-config').hidden = !(usuario.is_staff || usuario.is_superuser);
    el('menu-sistema-title').hidden = el('menu-usuarios').hidden && el('menu-config').hidden;
    const form = el('filtrosReportes'), tabla = el('filasReporte');
    let bodegas = [], permisos = {ver: false, exportar: false}, lista = false, pagina = 1, total = 0;
    let version = 0, temporizador, exportando = false, consultaAplicada = null, opcionesListas = false;
    let paginaProductos = 1, totalProductos = 0, versionProductos = 0, timerProductos;
    const bodegaInicial = new URLSearchParams(location.search).get('bodega');
    const actual = () => el('informeReporte').value;
    const esStock = () => ['existencias', 'critico'].includes(actual());
    const error = mensaje => { el('errorReportes').textContent = mensaje || ''; el('errorReportes').hidden = !mensaje; };
    function botonesExportar() {
        for (const id of ['exportarReporte', 'imprimirReporte']) {
            el(id).disabled = !permisos.exportar || !lista || exportando;
            el(id).hidden = !permisos.exportar;
        }
    }
    function mensajeTabla(mensaje) {
        const fila = crear('tr'), celda = crear('td', 'ss-report-empty text-muted py-4', mensaje);
        celda.colSpan = Math.max(1, el('cabeceraReporte').querySelectorAll('th').length);
        fila.appendChild(celda); tabla.replaceChildren(fila);
    }
    function invalidar() {
        ++version; lista = false; consultaAplicada = null;
        tabla.setAttribute('aria-busy', 'false');
        botonesExportar(); el('paginasReporte').replaceChildren();
        el('resumenReporte').replaceChildren(); el('metadatosReporte').textContent = ''; el('notasReporte').replaceChildren();
        el('conteoReporte').textContent = ''; el('estadoExportarReporte').textContent = '';
        mensajeTabla('Actualizando reporte…');
    }
    function configurarTipo(bodegaPreferida = null) {
        const stock = esStock(), kardex = actual() === 'kardex';
        el('tituloResultadoReporte').textContent = el('informeReporte').selectedOptions[0].textContent;
        el('cabeceraReporte').replaceChildren();
        el('grupoBuscarReporte').hidden = kardex;
        el('grupoEstadoProducto').hidden = !stock;
        el('grupoTipoReporte').hidden = actual() !== 'movimientos';
        el('grupoProductoKardex').hidden = !kardex;
        for (const id of ['desdeReporte', 'hastaReporte']) el(id).disabled = stock;
        el('bodegaReporte').required = stock || kardex;
        el('productoReporte').required = kardex;
        el('ayudaFechasReporte').textContent = stock ? 'Las existencias y el stock crítico muestran el estado actual, sin filtro de fechas.' :
            kardex ? 'Selecciona una bodega y un producto. El Kardex incluye entradas, salidas, transferencias y mermas.' : 'Las fechas incluyen el día completo en America/Santiago. Sin fechas se consulta todo el historial disponible.';
        const anterior = bodegaPreferida || el('bodegaReporte').value;
        el('bodegaReporte').replaceChildren(...(!stock && !kardex ? [new Option('Todas las bodegas', '')] : []), ...bodegas.map(b => new Option(b.nombre + (b.activa ? '' : ' (inactiva)'), String(b.id))));
        const defecto = bodegas.find(b => b.activa && b.nombre === 'Bodega Central') || bodegas.find(b => b.activa) || bodegas[0];
        el('bodegaReporte').value = bodegas.some(b => String(b.id) === anterior) ? anterior : stock || kardex ? String(defecto?.id || '') : '';
        el('bodegaReporte').disabled = !bodegas.length;
        if (kardex) { el('productoReporte').value = ''; cargarProductos(); }
    }
    function parametros() {
        const p = new URLSearchParams({informe: actual()});
        if (el('bodegaReporte').value) p.set('bodega', el('bodegaReporte').value);
        if (actual() === 'kardex') { if (el('productoReporte').value) p.set('producto', el('productoReporte').value); }
        else if (el('buscarReporte').value.trim()) p.set('search', el('buscarReporte').value.trim());
        if (esStock()) p.set('productos', el('estadoProductoReporte').value);
        else for (const campo of ['desde', 'hasta']) { const valor = el(campo + 'Reporte').value; if (valor) p.set(campo, valor); }
        if (actual() === 'movimientos' && el('tipoReporte').value) p.set('tipo', el('tipoReporte').value);
        return p;
    }
    function paginar() {
        const paginas = Math.ceil(total / 25), nav = el('paginasReporte'); nav.replaceChildren();
        if (paginas <= 1) return;
        function boton(texto, numero, deshabilitado) {
            const b = crear('button', 'btn btn-sm ' + (numero === pagina ? 'btn-primary' : 'btn-outline-secondary'), texto);
            b.type = 'button'; b.dataset.page = String(numero); b.disabled = deshabilitado || numero === pagina;
            b.setAttribute('aria-label', texto === 'Anterior' ? 'Página anterior' : texto === 'Siguiente' ? 'Página siguiente' : 'Página ' + numero);
            if (numero === pagina) b.setAttribute('aria-current', 'page'); nav.appendChild(b);
        }
        boton('Anterior', pagina - 1, pagina === 1);
        const numeros = new Set([1, paginas]); for (let n = Math.max(1, pagina - 1); n <= Math.min(paginas, pagina + 1); n++) numeros.add(n);
        let previo = 0; for (const n of [...numeros].sort((a, b) => a - b)) { if (previo && n > previo + 1) nav.appendChild(crear('span', 'p-2', '…')); boton(String(n), n, false); previo = n; }
        boton('Siguiente', pagina + 1, pagina === paginas);
    }
    function pintar(json) {
        const meta = json.meta;
        if (!Array.isArray(json.results) || !Number.isInteger(json.count) || json.count < 0 || !Array.isArray(meta?.columnas) || !Array.isArray(meta.resumen) || !Array.isArray(meta.notas) || !Array.isArray(meta.filtros)) throw new Error('El servidor devolvió un reporte incompleto.');
        total = json.count;
        if (typeof meta.permisos?.exportar === 'boolean') permisos.exportar = meta.permisos.exportar;
        el('tituloResultadoReporte').textContent = el('descripcionTablaReporte').textContent = meta.titulo;
        const cabecera = crear('tr'); for (const c of meta.columnas) { const th = crear('th', c.numero ? 'text-end' : '', c.etiqueta); th.scope = 'col'; cabecera.appendChild(th); }
        el('cabeceraReporte').replaceChildren(cabecera);
        if (json.results.length) tabla.replaceChildren(...json.results.map(item => {
            const tr = crear('tr');
            for (const c of meta.columnas) {
                const td = crear('td', c.numero ? 'ss-report-number' : '', item[c.campo]); td.dataset.label = c.etiqueta; td.dataset.campo = c.campo; tr.appendChild(td);
            }
            return tr;
        })); else mensajeTabla('No hay registros para estos filtros.');
        el('resumenReporte').replaceChildren(...meta.resumen.map(r => { const grupo = crear('div', 'ss-report-stat'); grupo.append(crear('dt', '', r.etiqueta), crear('dd', '', r.valor)); return grupo; }));
        const fecha = new Date(meta.generado);
        el('metadatosReporte').textContent = meta.filtros.map(f => f[0] + ': ' + f[1]).join(' · ') + ' · ' + meta.orden + '. Generado: ' + (Number.isNaN(fecha.getTime()) ? meta.generado : fecha.toLocaleString('es-CL', {timeZone: 'America/Santiago'})) + ' · America/Santiago.';
        el('notasReporte').replaceChildren(...meta.notas.map(n => crear('p', '', n)));
        el('conteoReporte').textContent = total ? 'Mostrando ' + ((pagina - 1) * 25 + 1) + '–' + ((pagina - 1) * 25 + json.results.length) + ' de ' + total + ' registros' : '0 registros';
        paginar();
    }
    async function cargar({ultima = false} = {}) {
        clearTimeout(temporizador); invalidar(); const v = version; error('');
        el('reintentarReportes').hidden = true;
        if (!opcionesListas) return;
        if ((esStock() || actual() === 'kardex') && !el('bodegaReporte').value) { mensajeTabla('No hay bodegas disponibles para este reporte.'); return; }
        if (actual() === 'kardex' && !el('productoReporte').value) { mensajeTabla('Selecciona un producto para consultar su Kardex.'); return; }
        if (!esStock() && el('desdeReporte').value && el('hastaReporte').value && el('desdeReporte').value > el('hastaReporte').value) { error('La fecha inicial no puede ser posterior a la final.'); mensajeTabla('Revisa el rango de fechas.'); return; }
        const p = parametros(), aplicados = p.toString(); p.set('page', ultima ? 'last' : String(pagina));
        tabla.setAttribute('aria-busy', 'true');
        try {
            const json = await api.json('/api/v1/reportes/consulta/?' + p);
            if (v !== version) return;
            if (ultima) pagina = Math.max(1, Math.ceil(json.count / 25));
            pintar(json); consultaAplicada = aplicados; lista = true;
        } catch (e) {
            if (v !== version) return;
            if (e.status === 404 && pagina > 1 && !ultima) return cargar({ultima: true});
            error(e.message); mensajeTabla('No se pudo cargar el reporte.'); el('reintentarReportes').hidden = false;
        } finally { if (v === version) { tabla.setAttribute('aria-busy', 'false'); botonesExportar(); } }
    }
    async function cargarProductos({ultima = false} = {}) {
        clearTimeout(timerProductos); const v = ++versionProductos;
        const select = el('productoReporte'), anterior = select.value;
        select.disabled = true; el('estadoProductosReporte').textContent = 'Cargando productos…';
        el('reintentarProductosReporte').hidden = true;
        el('productosReporteAnterior').disabled = el('productosReporteSiguiente').disabled = true;
        try {
            const p = new URLSearchParams({page: ultima ? 'last' : String(paginaProductos), search: el('buscarProductoReporte').value.trim()});
            const json = await api.json('/api/v1/reportes/productos/?' + p);
            if (v !== versionProductos) return;
            if (!Array.isArray(json.results) || !Number.isInteger(json.count)) throw new Error('No se pudo leer la lista de productos.');
            totalProductos = json.count;
            if (ultima) paginaProductos = Math.max(1, Math.ceil(totalProductos / 25));
            select.replaceChildren(new Option('Selecciona un producto', ''), ...json.results.map(p => new Option(p.sku + ' · ' + p.nombre + (p.activo ? '' : ' (inactivo)'), String(p.id))));
            if (json.results.some(p => String(p.id) === anterior)) select.value = anterior;
            select.disabled = false;
            el('estadoProductosReporte').textContent = json.count ? 'Página ' + paginaProductos + ' de ' + Math.ceil(json.count / 25) + ' · ' + json.count + ' productos' : 'No se encontraron productos.';
            el('productosReporteAnterior').disabled = paginaProductos <= 1; el('productosReporteSiguiente').disabled = paginaProductos >= Math.ceil(totalProductos / 25);
        } catch (e) {
            if (v !== versionProductos) return;
            if (e.status === 404 && paginaProductos > 1 && !ultima) return cargarProductos({ultima: true});
            select.replaceChildren(new Option('No se pudieron cargar los productos', ''));
            el('estadoProductosReporte').textContent = e.message; el('reintentarProductosReporte').hidden = false;
        }
    }
    async function iniciar() {
        error(''); el('reintentarReportes').hidden = true;
        try {
            permisos = await api.acceso();
            if (!permisos.ver) { error('No tienes permiso para consultar reportes de inventario. Solicita acceso a un administrador.'); mensajeTabla('Acceso restringido.'); return; }
            const r = await api.json('/api/v1/reportes/opciones/');
            if (!Array.isArray(r.data?.bodegas)) throw new Error('No se pudieron cargar las bodegas.');
            bodegas = r.data.bodegas; permisos = r.data.permisos; opcionesListas = true;
            if (r.data.menu) {
                el('menu-auditoria').hidden = !r.data.menu.auditoria;
                el('menu-usuarios').hidden = !r.data.menu.usuarios;
                el('menu-config').hidden = !r.data.menu.configuracion;
                el('menu-sistema-title').hidden = el('menu-usuarios').hidden && el('menu-config').hidden;
            }
            form.hidden = false; configurarTipo(bodegaInicial); await cargar();
        } catch (e) { error(e.message); el('reintentarReportes').hidden = false; }
    }
    el('informeReporte').addEventListener('change', () => { ++versionProductos; pagina = 1; configurarTipo(); cargar(); });
    for (const id of ['bodegaReporte', 'estadoProductoReporte', 'tipoReporte', 'desdeReporte', 'hastaReporte', 'productoReporte']) el(id).addEventListener('change', () => { pagina = 1; cargar(); });
    el('buscarReporte').addEventListener('input', () => { clearTimeout(temporizador); invalidar(); pagina = 1; temporizador = setTimeout(cargar, 300); });
    form.addEventListener('submit', e => { e.preventDefault(); pagina = 1; cargar(); });
    el('limpiarReporte').addEventListener('click', () => { const tipo = actual(); form.reset(); el('informeReporte').value = tipo; pagina = paginaProductos = 1; configurarTipo(); cargar(); });
    el('reintentarReportes').addEventListener('click', () => opcionesListas ? cargar() : iniciar());
    el('buscarProductoReporte').addEventListener('input', () => {
        clearTimeout(timerProductos); ++versionProductos; el('productoReporte').value = ''; el('productoReporte').disabled = true;
        pagina = paginaProductos = 1; cargar(); timerProductos = setTimeout(cargarProductos, 300);
    });
    el('reintentarProductosReporte').addEventListener('click', cargarProductos);
    for (const [id, delta] of [['productosReporteAnterior', -1], ['productosReporteSiguiente', 1]]) el(id).addEventListener('click', () => {
        paginaProductos += delta; el('productoReporte').value = ''; pagina = 1; cargar(); cargarProductos();
    });
    el('paginasReporte').addEventListener('click', e => {
        const b = e.target.closest('button[data-page]'); if (!b || b.disabled) return;
        const numero = Number(b.dataset.page); if (!Number.isInteger(numero) || numero < 1 || numero > Math.ceil(total / 25)) return;
        pagina = numero; cargar(); form.scrollIntoView({block: 'start'});
    });
    function imprimir(html) {
        document.querySelectorAll('.ss-report-print').forEach(f => f.remove());
        return new Promise((resolve, reject) => {
            const frame = crear('iframe', 'ss-report-print'); frame.title = 'Reporte de inventario para imprimir'; frame.setAttribute('aria-hidden', 'true'); frame.tabIndex = -1;
            const espera = setTimeout(() => { frame.remove(); reject(new Error('No se pudo abrir la impresión. Vuelve a intentarlo.')); }, 30000);
            frame.addEventListener('load', () => {
                clearTimeout(espera);
                try { frame.contentWindow.addEventListener('afterprint', () => { frame.remove(); el('imprimirReporte').focus(); }, {once: true}); frame.contentWindow.focus(); frame.contentWindow.print(); resolve(); }
                catch (_) { frame.remove(); reject(new Error('No se pudo abrir la impresión del reporte.')); }
            }, {once: true});
            frame.srcdoc = html; document.body.appendChild(frame);
        });
    }
    async function exportar(formato) {
        if (!lista || !permisos.exportar || exportando || consultaAplicada === null) return;
        const v = version, filtros = consultaAplicada;
        exportando = true; botonesExportar(); el('estadoExportarReporte').textContent = 'Preparando todos los registros filtrados…';
        try {
            const r = await api.solicitar('/api/v1/reportes/' + (formato === 'csv' ? 'exportar/' : 'imprimir/') + '?' + filtros);
            const tipo = (r.headers.get('Content-Type') || '').toLowerCase();
            if (!tipo.startsWith(formato === 'csv' ? 'text/csv' : 'text/html')) throw new Error('El servidor no devolvió el formato solicitado.');
            const contenido = formato === 'csv' ? await r.blob() : await r.text();
            if (v !== version) { el('estadoExportarReporte').textContent = 'Los filtros cambiaron. Vuelve a exportar el reporte actualizado.'; return; }
            if (formato === 'csv') {
                const url = URL.createObjectURL(contenido), a = crear('a'); a.href = url; a.download = 'smartstock-' + new URLSearchParams(filtros).get('informe') + '.csv';
                document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
            } else await imprimir(contenido);
            el('estadoExportarReporte').textContent = formato === 'csv' ? 'CSV preparado con todos los resultados filtrados.' : 'Reporte preparado. Puedes imprimirlo o guardarlo como PDF.';
        } catch (e) { el('estadoExportarReporte').textContent = e.message; }
        finally { exportando = false; botonesExportar(); }
    }
    el('exportarReporte').addEventListener('click', () => exportar('csv'));
    el('imprimirReporte').addEventListener('click', () => exportar('html'));
    iniciar();
});
