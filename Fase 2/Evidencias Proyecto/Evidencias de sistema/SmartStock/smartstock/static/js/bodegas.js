/* Administración de bodegas con historial y bajas protegidas. */
document.addEventListener('DOMContentLoaded', async () => {
    'use strict';
    if (window.SmartStockNavegacion && !await window.SmartStockNavegacion.lista) return;
    if (!localStorage.getItem('access_token')) { window.location.replace('/'); return; }
    const el = id => document.getElementById(id);
    const nodo = (tag, clase, texto) => { const n = document.createElement(tag); if (clase) n.className = clase; if (texto !== undefined) n.textContent = String(texto ?? ''); return n; };
    const aviso = (id, texto) => { el(id).textContent = texto || ''; el(id).hidden = !texto; };
    const aTexto = v => Array.isArray(v) ? v.map(aTexto).join(' ') : v && typeof v === 'object' ? Object.values(v).map(aTexto).join(' ') : String(v || '');
    let sesion = {}; try { sesion = JSON.parse(localStorage.getItem('usuario') || '{}') || {}; } catch (_) {}
    el('user-name-sidebar').textContent = sesion.nombre_completo || 'Usuario'; el('user-role-sidebar').textContent = sesion.rol_nombre || 'Sin rol';
    el('user-avatar').src = 'https://ui-avatars.com/api/?name=' + encodeURIComponent(sesion.nombre_completo || 'Usuario') + '&background=0f766e&color=fff';
    let renovacion;
    async function api(url, opciones = {}) {
        let token = localStorage.getItem('access_token');
        const enviar = () => fetch(url, {...opciones, cache: 'no-store', headers: {...(opciones.body ? {'Content-Type': 'application/json'} : {}), Authorization: 'Bearer ' + token}});
        let r;
        try {
            r = await enviar();
            if (r.status === 401) {
                if (!renovacion) renovacion = (async () => {
                    const refresh = localStorage.getItem('refresh_token'); if (!refresh) return false;
                    const res = await fetch('/api/v1/auth/refresh/', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({refresh})});
                    if (res.status >= 500) throw new Error('No se pudo renovar la sesión. Inténtalo nuevamente.');
                    if (!res.ok) return false;
                    const json = await res.json(), d = json.data || json;
                    if (!d.access) return false;
                    localStorage.setItem('access_token', d.access); if (d.refresh) localStorage.setItem('refresh_token', d.refresh); return true;
                })().finally(() => { renovacion = null; });
                if (await renovacion || localStorage.getItem('access_token') !== token) { token = localStorage.getItem('access_token'); r = await enviar(); }
                else { window.smartstockClearSession(); window.location.replace('/'); throw new Error('La sesión expiró. Vuelve a iniciar sesión.'); }
            }
        } catch (error) { throw new Error(opciones.method ? 'No pudimos confirmar el resultado. Revisa el listado antes de volver a registrar.' : error.message || 'No se pudo conectar con el servidor.'); }
        let json; try { json = await r.json(); } catch (_) { throw new Error('No se pudo leer la respuesta. Revisa el listado antes de reintentar.'); }
        if (!r.ok || json.success === false) { const error = new Error(json.mensaje || json.detail || 'Revisa los datos de la operación.'); error.status = r.status; error.datos = json.errores || json; throw error; }
        return json;
    }
    let pagina = 1, total = 0, versionLista = 0, timer, opciones = null;
    const url = (id = '') => '/api/v1/bodegas/' + (id ? encodeURIComponent(id) + '/' : '');
    function aplicarPermisos() {
        const p = opciones?.permisos || {};
        el('nuevaEntidad').hidden = !opciones || !p.crear;
        [['menu-auditoria', p.auditoria], ['menu-usuarios', p.usuarios], ['menu-config', p.configuracion], ['menu-sistema-title', p.usuarios || p.configuracion]].forEach(([id, mostrar]) => { el(id).hidden = !mostrar; });
    }
    function cabecera() {
        const titulos = ['Bodega', 'Dirección', 'Unidades', 'Estado', 'Acciones'];
        const tr = nodo('tr'); titulos.forEach(t => tr.append(nodo('th', '', t))); el('encabezadoBodegas').replaceChildren(tr); return titulos;
    }
    function boton(texto, accion, item, clase) { const b = nodo('button', 'btn btn-sm ' + clase, texto); b.type = 'button'; b.dataset.accion = accion; b.dataset.id = String(item.id); b.setAttribute('aria-label', texto + ' ' + 'bodega' + ' ' + item.nombre); return b; }
    const vistaMovil = window.matchMedia?.('(max-width: 575.98px)');
    function distribuirAcciones(grupo) {
        const estado = grupo.querySelector('.ss-bodega-state-action'); if (!estado) return;
        let mas = grupo.querySelector('.ss-bodega-more');
        if (vistaMovil?.matches) { if (mas) { grupo.append(estado); mas.remove(); } return; }
        if (!mas) {
            mas = nodo('details', 'ss-bodega-more');
            const summary = nodo('summary', 'btn btn-sm btn-outline-secondary', 'Más acciones');
            const icono = nodo('i', 'fa-solid fa-chevron-down'); icono.setAttribute('aria-hidden', 'true'); summary.append(icono);
            const panel = nodo('div', 'ss-bodega-more-panel'); panel.append(estado); mas.append(summary, panel); grupo.append(mas);
        }
    }
    vistaMovil?.addEventListener('change', () => document.querySelectorAll('.ss-bodegas-actions').forEach(distribuirAcciones));
    document.addEventListener('click', e => document.querySelectorAll('.ss-bodega-more[open]').forEach(m => { if (!m.contains(e.target)) m.open = false; }));
    document.addEventListener('keydown', e => { if (e.key === 'Escape') document.querySelectorAll('.ss-bodega-more[open]').forEach(m => { m.open = false; m.querySelector('summary').focus(); }); });
    function fila(item, titulos) {
        const tr = nodo('tr', 'ss-bodega-row'), valores = [item.nombre, item.direccion || 'Sin dirección', Number(item.unidades).toLocaleString('es-CL')];
        valores.forEach((v, i) => { const td = nodo('td'); td.dataset.label = titulos[i]; td.append(nodo(i ? 'span' : 'strong', '', v)); tr.append(td); });
        const estado = nodo('td'); estado.dataset.label = 'Estado'; estado.append(nodo('span', 'ss-bodegas-badge' + (item.activa ? ' activa' : ''), item.activa ? 'Activa' : 'Inactiva')); tr.append(estado);
        const acciones = nodo('td'), grupo = nodo('div', 'ss-bodegas-actions'), p = opciones.permisos;
        if (p.editar) grupo.append(boton('Editar', 'editar', item, 'btn-outline-primary'));
        if (p.desactivar) grupo.append(boton(item.activa ? 'Desactivar' : 'Reactivar', item.activa ? 'desactivar' : 'activar', item, 'ss-bodega-state-action ' + (item.activa ? 'btn-outline-warning' : 'btn-outline-success')));
        if (!grupo.children.length) grupo.append(nodo('span', 'small text-muted', 'Solo lectura'));
        const ubicaciones = nodo('a', 'btn btn-sm btn-outline-secondary', 'Ubicaciones');
        ubicaciones.href = '/ubicaciones/?bodega=' + encodeURIComponent(item.id);
        ubicaciones.setAttribute('aria-label', 'Ver ubicaciones de ' + item.nombre);
        grupo.prepend(ubicaciones);
        distribuirAcciones(grupo);
        acciones.append(grupo); tr.append(acciones); return tr;
    }
    function tablaMensaje(texto) { const tr = nodo('tr'), td = nodo('td', 'text-center text-muted py-4', texto); td.colSpan = 5; tr.append(td); el('listaBodegas').replaceChildren(tr); }
    function paginar() {
        const cont = el('paginacionBodegas'), paginas = Math.ceil(total / 25); cont.replaceChildren(); if (paginas <= 1) return;
        const agregar = (texto, n, disabled = false) => { const b = nodo('button', 'btn btn-sm ' + (n === pagina ? 'btn-primary' : 'btn-outline-secondary'), texto); b.type = 'button'; b.dataset.page = String(n); b.disabled = disabled || n === pagina; if (n === pagina) b.setAttribute('aria-current', 'page'); cont.append(b); };
        agregar('Anterior', pagina - 1, pagina === 1);
        const numeros = new Set([1, paginas]); for (let n = Math.max(1, pagina - 1); n <= Math.min(paginas, pagina + 1); n++) numeros.add(n);
        let previo = 0; [...numeros].sort((a,b) => a-b).forEach(n => { if (previo && n > previo + 1) cont.append(nodo('span', 'align-self-center', '…')); agregar(String(n), n); previo = n; });
        agregar('Siguiente', pagina + 1, pagina === paginas);
    }
    async function cargarLista(ultima = false) {
        clearTimeout(timer); if (!opciones) return;
        const version = ++versionLista, titulos = cabecera(); tablaMensaje('Cargando...'); el('listaBodegas').setAttribute('aria-busy', 'true'); el('paginacionBodegas').replaceChildren(); aviso('avisoBodegas', ''); el('reintentarBodegas').hidden = true;
        const params = new URLSearchParams({page: ultima ? 'last' : String(pagina)});
        const filtros = {search: el('buscarBodegas').value.trim(), activa: el('estadoBodegas').value};
        Object.entries(filtros).forEach(([k,v]) => { if (v) params.set(k,v); });
        try {
            const d = await api(url() + '?' + params);
            if (version !== versionLista) return;
            if (!Array.isArray(d.results) || !Number.isInteger(d.count) || d.count < 0) throw new Error('El listado tiene un formato inválido.');
            total = d.count; if (ultima) pagina = Math.max(1, Math.ceil(total / 25));
            if (d.results.length) el('listaBodegas').replaceChildren(...d.results.map(i => fila(i, titulos))); else tablaMensaje('No hay registros para estos filtros.');
            el('totalBodegas').textContent = total + ' bodegas'; el('resumenBodegas').textContent = total ? 'Mostrando ' + ((pagina - 1) * 25 + 1) + '–' + ((pagina - 1) * 25 + d.results.length) + ' de ' + total : '0 registros'; paginar();
        } catch (error) { if (version !== versionLista) return; if (error.status === 404 && pagina > 1 && !ultima) return cargarLista(true); aviso('avisoBodegas', error.message); tablaMensaje('No se pudo cargar el listado.'); el('reintentarBodegas').hidden = false; }
        finally { if (version === versionLista) el('listaBodegas').setAttribute('aria-busy', 'false'); }
    }
    async function cargarOpciones() {
        el('reintentarBodegas').hidden = true;
        try {
            const json = await api('/api/v1/bodegas/opciones/'), d = json.data;
            if (!d || !d.permisos) throw new Error('No se pudieron leer las opciones.');
            opciones = d;
            aplicarPermisos(); return true;
        } catch (error) { aviso('avisoBodegas', error.message); el('reintentarBodegas').hidden = false; aplicarPermisos(); return false; }
    }
    el('buscarBodegas').addEventListener('input', () => { versionLista++; pagina = 1; clearTimeout(timer); tablaMensaje('Buscando...'); timer = setTimeout(() => cargarLista(), 300); });
    ['estadoBodegas'].forEach(id => el(id).addEventListener('change', () => { pagina = 1; cargarLista(); }));
    el('filtrosBodegas').addEventListener('submit', e => { e.preventDefault(); pagina = 1; cargarLista(); });
    el('limpiarBodegas').addEventListener('click', () => { el('filtrosBodegas').reset(); pagina = 1; cargarLista(); });
    el('paginacionBodegas').addEventListener('click', e => { const b = e.target.closest('[data-page]'); if (!b || b.disabled) return; pagina = Number(b.dataset.page); cargarLista(); el('totalBodegas').scrollIntoView({block:'start'}); });
    el('reintentarBodegas').addEventListener('click', async () => { if (await cargarOpciones()) cargarLista(); });

    const form = {id:null, version:0, abierto:false, cargando:false, pendiente:false, completo:false, datos:null};
    const modal = bootstrap.Modal.getOrCreateInstance(el('modalEntidad'));
    function bloquearForm() { el('modalEntidad').querySelectorAll('input,select,button').forEach(c => { c.disabled = form.pendiente || (!c.hasAttribute('data-bs-dismiss') && (form.cargando || form.completo || (form.id && !form.datos && c.id !== 'reintentarEntidad'))); }); el('guardarEntidad').textContent = form.pendiente ? 'Guardando...' : form.id ? 'Guardar cambios' : 'Crear bodega'; }
    function limpiarErrores() { aviso('errorEntidad', ''); el('formEntidad').querySelectorAll('.is-invalid').forEach(c => { c.classList.remove('is-invalid'); c.removeAttribute('aria-invalid'); }); }
    function errorCampo(campo, texto) { const id = 'entidad' + campo[0].toUpperCase() + campo.slice(1); el(id).classList.add('is-invalid'); el(id).setAttribute('aria-invalid','true'); el(id + 'Error').textContent = texto; }
    async function cargarEntidad() {
        const version = ++form.version; form.cargando = true; form.datos = null; bloquearForm(); aviso('estadoEntidad', 'Cargando registro...'); el('reintentarEntidad').hidden = true;
        try {
            const d = await api(url(form.id)); if (version !== form.version || !form.abierto) return;
            form.datos = d; el('entidadNombre').value = d.nombre; el('entidadDireccion').value = d.direccion || '';
            aviso('estadoEntidad', '');
        } catch (error) { if (version === form.version) { aviso('errorEntidad', error.message); el('reintentarEntidad').hidden = false; } }
        finally { if (version === form.version) { form.cargando = false; bloquearForm(); } }
    }
    function abrirFormulario(id = null) {
        const p = opciones?.permisos; if (!p || !(id ? p.editar : p.crear) || form.pendiente || accion.pendiente) return;
        Object.assign(form,{id,abierto:true,cargando:false,pendiente:false,completo:false,datos:null}); form.version++; el('formEntidad').reset(); limpiarErrores(); aviso('estadoEntidad',''); el('reintentarEntidad').hidden = true;
        el('tituloEntidad').textContent = id ? 'Editar bodega' : 'Nueva bodega';
        bloquearForm(); modal.show(); if (id) cargarEntidad();
    }
    el('nuevaEntidad').addEventListener('click', () => abrirFormulario()); el('reintentarEntidad').addEventListener('click', cargarEntidad);
    el('modalEntidad').addEventListener('hide.bs.modal', e => { if (form.pendiente) e.preventDefault(); else { form.abierto = false; form.version++; } });
    el('modalEntidad').addEventListener('shown.bs.modal', () => { if (!form.cargando) el('entidadNombre').focus(); });
    el('formEntidad').addEventListener('submit', async e => {
        e.preventDefault(); if (!form.abierto || form.pendiente || form.completo || form.cargando || (form.id && !form.datos)) return;
        limpiarErrores(); const data = {nombre:el('entidadNombre').value.trim(),direccion:el('entidadDireccion').value.trim()};
        if (!data.nombre) errorCampo('nombre','Ingresa un nombre.');
        if (el('formEntidad').querySelector('.is-invalid')) { el('formEntidad').querySelector('.is-invalid').focus(); return; }
        form.pendiente = true; bloquearForm();
        try { await api(url(form.id),{method:form.id ? 'PATCH':'POST',body:JSON.stringify(data)}); form.completo = true; form.pendiente = false; modal.hide(); window.dispatchEvent(new Event('smartstock:notifications-changed')); pagina = 1; if (await cargarOpciones()) cargarLista(); }
        catch (error) { aviso('errorEntidad',error.message); ['nombre','direccion'].forEach(c => { if (error.datos?.[c]) errorCampo(c,aTexto(error.datos[c])); }); }
        finally { form.pendiente = false; bloquearForm(); }
    });
    const accion = {id:null,version:0,abierto:false,cargando:false,pendiente:false,completo:false,datos:null,activar:false};
    const modalAccion = bootstrap.Modal.getOrCreateInstance(el('modalEstadoEntidad'));
    function bloquearAccion() { el('confirmarEstadoEntidad').disabled = accion.cargando || accion.pendiente || accion.completo || !accion.datos; el('confirmarEstadoEntidad').textContent = accion.pendiente ? 'Guardando...' : accion.activar ? 'Reactivar' : 'Desactivar'; el('modalEstadoEntidad').querySelectorAll('[data-bs-dismiss]').forEach(b => { b.disabled = accion.pendiente; }); }
    async function abrirAccion(id,activar) {
        const p = opciones?.permisos; if (!p || !p.desactivar || accion.pendiente || form.pendiente) return;
        Object.assign(accion,{id,activar,abierto:true,cargando:true,pendiente:false,completo:false,datos:null}); const version = ++accion.version;
        el('tituloEstadoEntidad').textContent = activar ? 'Reactivar bodega' : 'Desactivar bodega'; el('nombreAccionEntidad').textContent = ''; aviso('errorEstadoEntidad',''); el('estadoAccionEntidad').textContent = 'Consultando el registro...'; el('descripcionAccionEntidad').textContent = ''; bloquearAccion(); modalAccion.show();
        try { const d = await api(url(id)); if (version !== accion.version || !accion.abierto) return; if (Boolean(d.activa) === activar) throw new Error('El estado cambió. Cierra esta ventana y actualiza el listado.'); accion.datos = d; el('nombreAccionEntidad').textContent = d.nombre; el('estadoAccionEntidad').textContent = ''; el('descripcionAccionEntidad').textContent = activar ? 'La bodega volverá a estar disponible para registrar operaciones.' : 'Solo se puede desactivar una bodega sin existencias ni transferencias pendientes. Su historial se conserva.'; }
        catch (error) { if (version === accion.version) aviso('errorEstadoEntidad',error.message); }
        finally { if (version === accion.version) { accion.cargando = false; bloquearAccion(); } }
    }
    el('modalEstadoEntidad').addEventListener('hide.bs.modal', e => { if (accion.pendiente) e.preventDefault(); else { accion.abierto = false; accion.version++; } });
    el('formEstadoEntidad').addEventListener('submit', async e => {
        e.preventDefault(); if (!accion.abierto || accion.pendiente || accion.completo || accion.cargando || !accion.datos) return;
        accion.pendiente = true; bloquearAccion(); aviso('errorEstadoEntidad','');
        try { await api(url(accion.id) + (accion.activar ? 'activar/' : ''),{method:accion.activar ? 'POST':'DELETE'}); accion.completo = true; accion.pendiente = false; modalAccion.hide(); window.dispatchEvent(new Event('smartstock:notifications-changed')); if (await cargarOpciones()) cargarLista(); }
        catch (error) { aviso('errorEstadoEntidad',error.message); }
        finally { accion.pendiente = false; bloquearAccion(); }
    });
    el('listaBodegas').addEventListener('click', e => { const b = e.target.closest('[data-accion]'); if (!b) return; if (b.dataset.accion === 'editar') abrirFormulario(b.dataset.id); else abrirAccion(b.dataset.id,b.dataset.accion === 'activar'); });
    aplicarPermisos(); cargarOpciones().then(ok => { if (ok) cargarLista(); });
});
