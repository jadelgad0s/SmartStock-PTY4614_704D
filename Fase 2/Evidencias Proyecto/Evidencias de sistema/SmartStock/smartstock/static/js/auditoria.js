/* Auditoría: consulta paginada, detalle y reportes de todos los resultados filtrados. */
document.addEventListener('DOMContentLoaded', async () => {
    'use strict';
    if (window.SmartStockNavegacion && !await window.SmartStockNavegacion.lista) return;
    const token = localStorage.getItem('access_token');
    if (!token) { window.location.href = '/'; return; }
    let usuario;
    try { usuario = JSON.parse(localStorage.getItem('usuario') || '{}') || {}; }
    catch (_) { usuario = {}; }
    if (!window.SmartStockNavegacion && String(usuario.rol_nombre || '').toLowerCase() !== 'administrador' && usuario.is_superuser !== true) {
        window.location.href = '/dashboard/'; return;
    }
    const el = id => document.getElementById(id);
    el('user-name-sidebar').textContent = usuario.nombre_completo || 'Administrador';
    el('user-role-sidebar').textContent = usuario.rol_nombre || 'Administrador';
    el('user-avatar').src = 'https://ui-avatars.com/api/?name=' + encodeURIComponent(usuario.nombre_completo || 'Admin') + '&background=0f766e&color=fff';

    const headers = {Authorization: 'Bearer ' + token};
    const tabla = el('listaAuditoria');
    const paginador = el('paginacionAuditoria');
    const resumen = el('resumenAuditoria');
    const detalleEl = el('modalDetalleAuditoria');
    const modalDetalle = bootstrap.Modal.getOrCreateInstance(detalleEl);
    const camposFiltros = {usuario: 'usuarioAuditoria', accion: 'accionAuditoria', modelo: 'modeloAuditoria', desde: 'desdeAuditoria', hasta: 'hastaAuditoria'};
    const TAMANO_PAGINA = 25;
    let pagina = 1;
    let total = 0;
    let versionHistorial = 0;
    let versionDetalle = 0;
    let temporizador;
    let historialListo = false;
    let exportando = false;
    let origenDetalle = null;
    let reporte = null;
    const nodo = (tag, clase, texto) => {
        const elemento = document.createElement(tag);
        if (clase) elemento.className = clase;
        if (texto !== undefined) elemento.textContent = String(texto ?? '');
        return elemento;
    };
    function aviso(id, texto) {
        el(id).textContent = texto || '';
        el(id).classList.toggle('d-none', !texto);
    }
    function estadoExportacion(texto, error = false) {
        el('estadoExportarAuditoria').textContent = texto;
        el('estadoExportarAuditoria').classList.toggle('text-danger', error);
        el('estadoExportarAuditoria').classList.toggle('text-muted', !error);
    }
    function actualizarExportacion() {
        ['exportarAuditoria', 'imprimirAuditoria'].forEach(id => { el(id).disabled = exportando || !historialListo; });
    }
    function parametros() {
        const params = new URLSearchParams();
        const search = el('buscarAuditoria').value.trim();
        if (search) params.set('search', search);
        Object.entries(camposFiltros).forEach(([campo, id]) => {
            if (el(id).value) params.set(campo, el(id).value);
        });
        return params;
    }
    async function solicitar(url) {
        let respuesta;
        try { respuesta = await fetch(url, {headers}); }
        catch (_) { throw new Error('No se pudo conectar con el servidor. Revisa la conexión y vuelve a intentarlo.'); }
        if (!respuesta.ok) {
            let datos = {};
            try { datos = await respuesta.json(); } catch (_) { /* Respuesta sin JSON. */ }
            const mensaje = respuesta.status === 401 ? 'La sesión expiró. Vuelve a iniciar sesión.' :
                respuesta.status === 403 ? 'Solo los administradores activos pueden consultar auditoría.' :
                datos.mensaje || datos.detail || (respuesta.status === 400 ? 'Revisa los filtros y el rango de fechas.' : 'No se pudo completar la consulta de auditoría.');
            const error = new Error(mensaje);
            error.status = respuesta.status;
            throw error;
        }
        return respuesta;
    }
    async function consultar(url) {
        const respuesta = await solicitar(url);
        try { return await respuesta.json(); }
        catch (_) { throw new Error('No se pudo leer la respuesta de auditoría. Vuelve a intentarlo.'); }
    }
    function mensajeTabla(texto) {
        const fila = nodo('tr');
        const celda = nodo('td', 'text-center text-muted py-4', texto);
        celda.colSpan = 6;
        fila.appendChild(celda);
        tabla.replaceChildren(fila);
    }
    function prepararHistorial() {
        historialListo = false;
        actualizarExportacion();
        tabla.setAttribute('aria-busy', 'true');
        paginador.replaceChildren();
        resumen.textContent = 'Cargando eventos...';
        aviso('errorHistorialAuditoria', '');
        mensajeTabla('Cargando eventos...');
        if (!exportando) estadoExportacion('El reporte incluirá todos los eventos que coincidan con los filtros.');
    }
    function insigniaAccion(e) {
        const clase = {CREATE: 'create', UPDATE: 'update', DEACTIVATE: 'deactivate', REACTIVATE: 'reactivate', DELETE: 'delete', LOGIN: 'login', LOGOUT: 'logout', LOGIN_FAILED: 'failed'}[e.accion] || 'other';
        return nodo('span', 'ss-audit-badge ss-audit-badge-' + clase, e.accion_etiqueta || e.accion);
    }
    function filaEvento(e) {
        const fila = nodo('tr', 'ss-audit-row');
        const partes = String(e.fecha || '').split(' ');
        const fecha = nodo('td', 'ss-audit-date text-muted');
        fecha.append(nodo('span', '', partes[0]), nodo('span', 'ss-audit-time', partes[1] || ''));
        const persona = nodo('td', 'ss-audit-user');
        persona.appendChild(nodo('strong', '', e.usuario));
        if (e.usuario_email) {
            const correo = nodo('span', 'ss-audit-email', e.usuario_email);
            correo.title = e.usuario_email;
            persona.appendChild(correo);
        }
        const accion = nodo('td', 'ss-audit-action');
        accion.appendChild(insigniaAccion(e));
        const descripcion = nodo('td', 'ss-audit-description');
        descripcion.appendChild(nodo('span', 'ss-audit-preview', e.descripcion || 'Sin descripción.'));
        const acciones = nodo('td', 'ss-audit-actions');
        const boton = nodo('button', 'btn btn-sm btn-outline-secondary', 'Ver detalle');
        boton.type = 'button';
        boton.dataset.detalle = String(e.id);
        boton.setAttribute('aria-label', 'Ver detalle del evento ' + e.id + ' de ' + e.usuario);
        acciones.appendChild(boton);
        fila.append(fecha, persona, accion, nodo('td', 'ss-audit-module', e.modelo), descripcion, acciones);
        return fila;
    }
    function renderizarPaginacion(paginas) {
        paginador.replaceChildren();
        if (paginas <= 1) return;
        const lista = nodo('ul', 'pagination');
        const agregar = (texto, numero, deshabilitado, actual = false) => {
            const item = nodo('li', 'page-item' + (actual ? ' active' : '') + (deshabilitado ? ' disabled' : ''));
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
                const puntos = nodo('span', 'ss-audit-ellipsis', '…');
                puntos.setAttribute('aria-hidden', 'true');
                const item = nodo('li', 'page-item');
                item.appendChild(puntos);
                lista.appendChild(item);
            }
            agregar(String(n), n, false, n === pagina);
            anterior = n;
        });
        agregar('Siguiente', pagina + 1, pagina === paginas);
        paginador.appendChild(lista);
    }
    async function cargarHistorial({ultimaPagina = false, enfocar = false} = {}) {
        clearTimeout(temporizador);
        const version = ++versionHistorial;
        prepararHistorial();
        const activos = Object.values(camposFiltros).filter(id => el(id).value).length;
        el('mostrarFiltrosAuditoria').textContent = 'Filtros' + (activos ? ' (' + activos + ')' : '');
        const desde = el('desdeAuditoria').value;
        const hasta = el('hastaAuditoria').value;
        if (desde && hasta && desde > hasta) {
            aviso('errorHistorialAuditoria', 'La fecha inicial no puede ser posterior a la final.');
            mensajeTabla('Revisa el rango de fechas.');
            resumen.textContent = '';
            tabla.setAttribute('aria-busy', 'false');
            return;
        }
        const params = parametros();
        params.set('page', ultimaPagina ? 'last' : String(pagina));
        try {
            const json = await consultar('/api/v1/auditoria/historial/?' + params);
            if (version !== versionHistorial) return;
            if (!Array.isArray(json.results) || !Number.isInteger(json.count) || json.count < 0) throw new Error('La respuesta del historial no es válida.');
            total = json.count;
            const paginas = Math.ceil(total / TAMANO_PAGINA);
            if (ultimaPagina) pagina = Math.max(1, paginas);
            if (json.results.length) {
                tabla.replaceChildren(...json.results.map(filaEvento));
                const primero = (pagina - 1) * TAMANO_PAGINA + 1;
                resumen.textContent = 'Mostrando ' + primero + '–' + (primero + json.results.length - 1) + ' de ' + total + ' eventos';
            } else {
                mensajeTabla('No hay eventos para estos filtros.');
                resumen.textContent = '0 eventos';
            }
            el('zonaHorariaAuditoria').textContent = json.zona_horaria ? 'Fechas y horas en ' + json.zona_horaria + '.' : '';
            renderizarPaginacion(paginas);
            historialListo = true;
        } catch (error) {
            if (version !== versionHistorial) return;
            if (error.status === 404 && pagina > 1 && !ultimaPagina) return cargarHistorial({ultimaPagina: true, enfocar});
            aviso('errorHistorialAuditoria', error.message);
            mensajeTabla('No se pudo cargar el historial.');
            resumen.textContent = 'Error de carga';
        } finally {
            if (version === versionHistorial) {
                tabla.setAttribute('aria-busy', 'false');
                actualizarExportacion();
                if (enfocar && document.activeElement === document.body) resumen.focus({preventScroll: true});
            }
        }
    }
    el('mostrarFiltrosAuditoria').addEventListener('click', () => {
        const abierto = el('controlesFiltrosAuditoria').classList.toggle('is-open');
        el('mostrarFiltrosAuditoria').setAttribute('aria-expanded', String(abierto));
    });
    el('buscarAuditoria').addEventListener('input', () => {
        clearTimeout(temporizador);
        ++versionHistorial;
        pagina = 1;
        prepararHistorial();
        temporizador = setTimeout(() => cargarHistorial(), 300);
    });
    Object.values(camposFiltros).forEach(id => el(id).addEventListener('change', () => { pagina = 1; cargarHistorial(); }));
    el('filtrosAuditoria').addEventListener('submit', evento => { evento.preventDefault(); pagina = 1; cargarHistorial(); });
    el('limpiarFiltrosAuditoria').addEventListener('click', () => { el('filtrosAuditoria').reset(); pagina = 1; cargarHistorial(); });
    paginador.addEventListener('click', evento => {
        const boton = evento.target.closest('button[data-page]');
        if (!boton || boton.disabled) return;
        const numero = Number(boton.dataset.page);
        if (!Number.isInteger(numero) || numero < 1 || numero > Math.ceil(total / TAMANO_PAGINA)) return;
        pagina = numero;
        cargarHistorial({enfocar: evento.detail === 0});
        el('filtrosAuditoria').scrollIntoView({block: 'start', behavior: 'auto'});
    });
    async function cargarOpciones() {
        el('reintentarOpcionesAuditoria').disabled = true;
        try {
            const json = await consultar('/api/v1/auditoria/opciones/');
            const datos = json.data;
            if (!Array.isArray(datos?.usuarios) || !Array.isArray(datos.acciones) || !Array.isArray(datos.modelos)) throw new Error('No se pudieron leer las opciones de filtro.');
            const personas = [new Option('Todos', '')];
            datos.usuarios.forEach(u => personas.push(new Option(u.nombre + ' · ' + u.email, String(u.id))));
            if (datos.sin_usuario) personas.push(new Option('Sin usuario asociado', 'sin_usuario'));
            el('usuarioAuditoria').replaceChildren(...personas);
            el('accionAuditoria').replaceChildren(new Option('Todas', ''), ...datos.acciones.map(a => new Option(a.etiqueta, a.valor)));
            el('modeloAuditoria').replaceChildren(new Option('Todos', ''), ...datos.modelos.map(m => new Option(m, m)));
            ['usuarioAuditoria', 'accionAuditoria', 'modeloAuditoria'].forEach(id => { el(id).disabled = false; });
            aviso('errorOpcionesAuditoria', '');
            el('reintentarOpcionesAuditoria').classList.add('d-none');
        } catch (error) {
            aviso('errorOpcionesAuditoria', error.message + ([401, 403].includes(error.status) ? '' : ' Puedes seguir buscando por texto y fechas.'));
            el('reintentarOpcionesAuditoria').classList.remove('d-none');
        } finally { el('reintentarOpcionesAuditoria').disabled = false; }
    }
    el('reintentarOpcionesAuditoria').addEventListener('click', cargarOpciones);
    tabla.addEventListener('click', async evento => {
        const boton = evento.target.closest('button[data-detalle]');
        if (!boton) return;
        origenDetalle = boton;
        const version = ++versionDetalle;
        el('estadoDetalleAuditoria').textContent = 'Cargando detalle...';
        el('datosDetalleAuditoria').classList.add('d-none');
        modalDetalle.show();
        try {
            const json = await consultar('/api/v1/auditoria/' + encodeURIComponent(boton.dataset.detalle) + '/');
            if (version !== versionDetalle) return;
            const e = json.data;
            if (!e || !Number.isInteger(e.id)) throw new Error('La respuesta del detalle no es válida.');
            const datos = {Id: '#' + e.id, Usuario: e.usuario, Correo: e.usuario_email || 'Sin correo asociado.', Fecha: e.fecha,
                Zona: e.zona_horaria, Codigo: e.accion, Modelo: e.modelo,
                Objeto: e.objeto_id || 'Sin objeto asociado.', Descripcion: e.descripcion || 'Sin descripción.',
                Ip: e.ip_address || 'No registrada.', Agente: e.user_agent || 'No registrado.'};
            Object.entries(datos).forEach(([id, texto]) => { el('detalleAuditoria' + id).textContent = texto; });
            el('detalleAuditoriaAccion').replaceChildren(insigniaAccion(e));
            const otraClasificacion = Boolean(e.accion_registrada && e.accion_registrada !== e.accion);
            el('detalleAuditoriaRegistradaEtiqueta').hidden = !otraClasificacion;
            el('detalleAuditoriaRegistrada').hidden = !otraClasificacion;
            el('detalleAuditoriaRegistrada').textContent = otraClasificacion ? e.accion_registrada : '';
            el('datosDetalleAuditoria').classList.remove('d-none');
            el('estadoDetalleAuditoria').textContent = '';
        } catch (error) {
            if (version === versionDetalle) el('estadoDetalleAuditoria').textContent = error.message;
        }
    });
    detalleEl.addEventListener('hide.bs.modal', () => { ++versionDetalle; });
    detalleEl.addEventListener('hidden.bs.modal', () => {
        if (origenDetalle?.isConnected) origenDetalle.focus({preventScroll: true});
    });

    function imprimirDocumento(html) {
        if (reporte) reporte.remove();
        const frame = nodo('iframe', 'ss-audit-print-frame');
        frame.title = 'Reporte de auditoría para imprimir';
        frame.tabIndex = -1;
        frame.setAttribute('aria-hidden', 'true');
        reporte = frame;
        return new Promise((resolve, reject) => {
            const timeout = setTimeout(() => { frame.remove(); reject(new Error('El reporte no terminó de cargar. Vuelve a intentarlo.')); }, 30000);
            frame.addEventListener('load', () => {
                clearTimeout(timeout);
                try {
                    frame.contentWindow.addEventListener('afterprint', () => {
                        setTimeout(() => { frame.remove(); el('imprimirAuditoria').focus({preventScroll: true}); }, 0);
                    }, {once: true});
                    frame.contentWindow.focus();
                    frame.contentWindow.print();
                    resolve();
                } catch (_) { frame.remove(); reject(new Error('No se pudo abrir la impresión del reporte.')); }
            }, {once: true});
            // Este HTML procede de la plantilla del servidor, que escapa todos los datos de los eventos.
            frame.srcdoc = html;
            document.body.appendChild(frame);
        });
    }
    async function exportar(tipo) {
        if (exportando || !historialListo) return;
        const version = versionHistorial;
        const params = parametros();
        exportando = true;
        actualizarExportacion();
        estadoExportacion(tipo === 'csv' ? 'Preparando CSV con todos los resultados filtrados...' : 'Preparando reporte completo para imprimir...');
        try {
            const respuesta = await solicitar('/api/v1/auditoria/' + (tipo === 'csv' ? 'exportar/' : 'reporte/') + '?' + params);
            const esperado = tipo === 'csv' ? 'text/csv' : 'text/html';
            if (!(respuesta.headers.get('Content-Type') || '').toLowerCase().startsWith(esperado)) throw new Error('El servidor no devolvió un reporte válido.');
            if (tipo === 'csv') {
                const blob = await respuesta.blob();
                const url = URL.createObjectURL(blob);
                const enlace = nodo('a');
                const nombre = (respuesta.headers.get('Content-Disposition') || '').match(/filename="?([^";]+)"?/i);
                enlace.download = nombre ? nombre[1] : 'auditoria.csv';
                enlace.href = url;
                document.body.appendChild(enlace);
                enlace.click();
                enlace.remove();
                setTimeout(() => URL.revokeObjectURL(url), 60000);
            } else { await imprimirDocumento(await respuesta.text()); }
            estadoExportacion(version !== versionHistorial ? 'Reporte generado con los filtros seleccionados al iniciar la exportación.' :
                tipo === 'csv' ? 'CSV descargado con todos los resultados filtrados.' : 'Se abrió la impresión del reporte completo. Puedes guardarlo como PDF.');
        } catch (error) { estadoExportacion(error.message, true); }
        finally { exportando = false; actualizarExportacion(); }
    }
    el('exportarAuditoria').addEventListener('click', () => exportar('csv'));
    el('imprimirAuditoria').addEventListener('click', () => exportar('pdf'));
    cargarHistorial();
    cargarOpciones();
});
