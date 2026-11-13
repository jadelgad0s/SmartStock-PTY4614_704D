/* Gestión de usuarios: páginas reales, formularios y confirmaciones con identidad visible. */
document.addEventListener('DOMContentLoaded', async () => {
    'use strict';
    if (window.SmartStockNavegacion && !await window.SmartStockNavegacion.lista) return;
    let token = localStorage.getItem('access_token');
    if (!token) { window.location.replace('/'); return; }
    let sesion;
    try { sesion = JSON.parse(localStorage.getItem('usuario') || '{}') || {}; } catch (_) { sesion = {}; }
    if (!window.SmartStockNavegacion && String(sesion.rol_nombre || '').toLowerCase() !== 'administrador' && sesion.is_superuser !== true) {
        window.location.replace('/dashboard/'); return;
    }
    const el = id => document.getElementById(id);
    const nodo = (tag, clase, texto) => {
        const n = document.createElement(tag);
        if (clase) n.className = clase;
        if (texto !== undefined) n.textContent = String(texto ?? '');
        return n;
    };
    const nombre = u => u.nombre_completo || [u.nombres, u.apellidos].filter(Boolean).join(' ') || u.email || 'Usuario';
    const rolId = u => typeof u.rol === 'object' && u.rol ? u.rol.id : u.rol;
    const rolNombre = u => u.rol_nombre || (typeof u.rol === 'object' && u.rol ? u.rol.nombre : '') || 'Sin rol';
    const protegida = u => u.cuenta_protegida === true || u.is_superuser === true;
    const propia = u => Number(u.id) === Number(sesion.id);
    function perfil() {
        el('user-name-sidebar').textContent = nombre(sesion);
        el('user-role-sidebar').textContent = sesion.rol_nombre || 'Administrador';
        el('user-avatar').src = 'https://ui-avatars.com/api/?name=' + encodeURIComponent(nombre(sesion)) + '&background=0f766e&color=fff';
    }
    perfil();
    let renovacionPendiente = null;
    async function renovarSesion() {
        if (!renovacionPendiente) renovacionPendiente = (async () => {
            const refresh = localStorage.getItem('refresh_token');
            if (!refresh) return false;
            try {
                const res = await fetch('/api/v1/auth/refresh/', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({refresh})});
                if (!res.ok) return false;
                const json = await res.json();
                const datos = json.data || json;
                if (!datos.access) return false;
                token = datos.access;
                localStorage.setItem('access_token', token);
                if (datos.refresh) localStorage.setItem('refresh_token', datos.refresh);
                return true;
            } catch (_) { return false; }
        })().finally(() => { renovacionPendiente = null; });
        return renovacionPendiente;
    }
    async function apiFetch(url, options = {}) {
        const enviar = () => fetch(url, {...options, headers: {...options.headers, Authorization: 'Bearer ' + token}});
        let res;
        try {
            res = await enviar();
            if (res.status === 401) {
                if (await renovarSesion()) res = await enviar();
                else {
                    localStorage.removeItem('access_token'); localStorage.removeItem('refresh_token');
                    window.location.replace('/');
                }
            }
        } catch (_) {
            const error = new Error(options.method ? 'No pudimos confirmar el resultado. Revisa la lista antes de volver a intentarlo.' : 'No se pudo conectar con el servidor. Vuelve a intentarlo.');
            error.incierto = Boolean(options.method);
            throw error;
        }
        let datos;
        try { datos = await res.json(); }
        catch (_) {
            const error = new Error(options.method ? 'No pudimos confirmar el resultado. Revisa la lista antes de volver a intentarlo.' : 'No se pudo leer la respuesta del servidor.');
            error.incierto = Boolean(options.method);
            throw error;
        }
        if (!datos || typeof datos !== 'object') throw new Error('El servidor devolvió una respuesta que no se pudo leer.');
        if (!res.ok || datos.success === false) {
            const error = new Error(res.status === 401 ? 'La sesión expiró. Vuelve a iniciar sesión.' :
                datos.mensaje || datos.detail || (res.status === 403 ? 'Solo administradores activos pueden administrar usuarios.' : 'No se pudo completar la operación.'));
            error.status = res.status;
            error.datos = datos;
            throw error;
        }
        return datos;
    }
    const aviso = (id, texto) => { el(id).textContent = texto || ''; el(id).classList.toggle('d-none', !texto); };
    const mensajeError = valor => Array.isArray(valor) ? valor.map(mensajeError).join(' ') : valor && typeof valor === 'object' ? Object.values(valor).map(mensajeError).join(' ') : String(valor || '');
    function fechaVista(valor) {
        if (!valor || Number.isNaN(new Date(valor).getTime())) return 'Sin accesos registrados';
        const partes = new Intl.DateTimeFormat('es-CL', {timeZone: 'America/Santiago', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'}).formatToParts(new Date(valor));
        const p = Object.fromEntries(partes.map(parte => [parte.type, parte.value]));
        return p.day + '/' + p.month + '/' + p.year + ' ' + p.hour + ':' + p.minute + ':' + p.second;
    }

    const tabla = el('listaUsuarios'), paginador = el('paginacionUsuarios'), resumen = el('resumenUsuarios');
    let pagina = 1, total = 0, versionLista = 0, timerBusqueda;
    let roles = new Map(), opcionesListas = false, cargandoOpciones = false;
    const TAMANO_PAGINA = 25;
    function mensajeTabla(texto) {
        const fila = nodo('tr'), celda = nodo('td', 'text-center text-muted py-4', texto);
        celda.colSpan = 5; fila.appendChild(celda); tabla.replaceChildren(fila);
    }
    function prepararLista() {
        tabla.setAttribute('aria-busy', 'true'); paginador.replaceChildren();
        resumen.textContent = 'Cargando usuarios...'; aviso('usuarios-api-aviso', ''); mensajeTabla('Cargando usuarios...');
    }
    function botonAccion(texto, accion, u, clase) {
        const b = nodo('button', clase, texto); b.type = 'button'; b.dataset.accion = accion; b.dataset.id = String(u.id);
        b.setAttribute('aria-label', texto + ' — ' + nombre(u)); return b;
    }
    function filaUsuario(u) {
        const fila = nodo('tr', 'ss-user-row'), identidad = nodo('td', 'ss-user-identity');
        identidad.append(nodo('strong', '', nombre(u)), nodo('span', 'ss-user-email', u.email));
        const meta = nodo('div', 'ss-user-meta');
        meta.append(nodo('span', '', '#' + u.id), botonAccion('Ver detalle', 'detalle', u, 'ss-user-detail-link'));
        if (propia(u)) meta.appendChild(nodo('span', 'ss-user-label', 'Tu cuenta'));
        if (protegida(u)) meta.appendChild(nodo('span', 'ss-user-label', 'Cuenta protegida'));
        identidad.appendChild(meta);
        const rol = nodo('td', 'ss-user-role'); rol.appendChild(nodo('span', 'ss-user-role-tag', rolNombre(u)));
        const estado = nodo('td', 'ss-user-status');
        estado.appendChild(nodo('span', 'ss-user-state ss-user-state-' + (u.activo ? 'active' : 'inactive'), u.activo ? 'Activo' : 'Inactivo'));
        const acciones = nodo('td', 'ss-user-actions'), grupo = nodo('div', 'ss-user-action-group');
        grupo.appendChild(botonAccion('Editar', 'editar', u, 'btn btn-sm btn-outline-primary'));
        if (!u.activo) grupo.appendChild(botonAccion('Reactivar', 'reactivar', u, 'btn btn-sm btn-outline-success'));
        else if (!protegida(u) && !propia(u)) grupo.appendChild(botonAccion('Desactivar', 'desactivar', u, 'btn btn-sm btn-outline-warning'));
        if (!protegida(u) && !propia(u)) {
            const mas = nodo('details', 'ss-user-more');
            const titulo = nodo('summary', 'btn btn-sm btn-outline-secondary', 'Más acciones');
            const icono = nodo('i', 'fa-solid fa-chevron-down'); icono.setAttribute('aria-hidden', 'true'); titulo.appendChild(icono);
            mas.append(titulo, botonAccion('Eliminar definitivamente', 'eliminar', u, 'btn btn-sm btn-outline-danger ss-user-delete'));
            grupo.appendChild(mas);
        }
        acciones.appendChild(grupo);
        fila.append(identidad, rol, estado, nodo('td', 'ss-user-last-login', fechaVista(u.ultimo_login)), acciones);
        return fila;
    }
    function paginar(paginas) {
        paginador.replaceChildren(); if (paginas <= 1) return;
        const lista = nodo('ul', 'pagination');
        const agregar = (texto, n, deshabilitado, actual = false) => {
            const item = nodo('li', 'page-item' + (actual ? ' active' : '') + (deshabilitado ? ' disabled' : ''));
            const b = nodo('button', 'page-link', texto); b.type = 'button'; b.dataset.page = String(n); b.disabled = deshabilitado || actual;
            b.setAttribute('aria-label', texto === 'Anterior' ? 'Página anterior' : texto === 'Siguiente' ? 'Página siguiente' : 'Ir a página ' + n);
            if (actual) b.setAttribute('aria-current', 'page'); item.appendChild(b); lista.appendChild(item);
        };
        agregar('Anterior', pagina - 1, pagina === 1);
        const numeros = new Set([1, paginas]);
        for (let n = Math.max(1, pagina - 1); n <= Math.min(paginas, pagina + 1); n++) numeros.add(n);
        if (pagina <= 2 && paginas >= 3) numeros.add(3);
        let previo = 0;
        [...numeros].sort((a, b) => a - b).forEach(n => {
            if (previo && n > previo + 1) { const li = nodo('li'); const puntos = nodo('span', 'ss-users-ellipsis', '…'); puntos.setAttribute('aria-hidden', 'true'); li.appendChild(puntos); lista.appendChild(li); }
            agregar(String(n), n, false, n === pagina); previo = n;
        });
        agregar('Siguiente', pagina + 1, pagina === paginas); paginador.appendChild(lista);
    }
    async function cargarUsuarios({ultima = false, enfocar = false} = {}) {
        clearTimeout(timerBusqueda); const version = ++versionLista; prepararLista();
        const params = new URLSearchParams({page: ultima ? 'last' : String(pagina), ordering: el('ordenUsuarios').value});
        const campos = {search: el('buscarUsuarios').value.trim(), rol: el('rolUsuarios').value, activo: el('estadoUsuarios').value};
        Object.entries(campos).forEach(([k, v]) => { if (v) params.set(k, v); });
        const activos = ['rolUsuarios', 'estadoUsuarios'].filter(id => el(id).value).length;
        el('mostrarFiltrosUsuarios').textContent = 'Filtros' + (activos ? ' (' + activos + ')' : '');
        try {
            const datos = await apiFetch('/api/v1/usuarios/?' + params);
            if (version !== versionLista) return;
            if (!Number.isInteger(datos.count) || datos.count < 0 || !Array.isArray(datos.results)) throw new Error('El listado de usuarios no tiene un formato válido.');
            total = datos.count; const paginas = Math.ceil(total / TAMANO_PAGINA);
            if (ultima) pagina = Math.max(1, paginas);
            if (datos.results.length) {
                tabla.replaceChildren(...datos.results.map(filaUsuario));
                const primero = (pagina - 1) * TAMANO_PAGINA + 1;
                resumen.textContent = 'Mostrando ' + primero + '–' + (primero + datos.results.length - 1) + ' de ' + total + ' usuarios';
            } else { mensajeTabla('No hay usuarios para estos filtros.'); resumen.textContent = '0 usuarios'; }
            paginar(paginas);
        } catch (error) {
            if (version !== versionLista) return;
            if (error.status === 404 && pagina > 1 && !ultima) return cargarUsuarios({ultima: true, enfocar});
            aviso('usuarios-api-aviso', error.message); mensajeTabla('No se pudieron cargar los usuarios.'); resumen.textContent = 'Error de carga';
        } finally {
            if (version === versionLista) { tabla.setAttribute('aria-busy', 'false'); if (enfocar && document.activeElement === document.body) resumen.focus({preventScroll: true}); }
        }
    }
    el('mostrarFiltrosUsuarios').addEventListener('click', () => {
        const abierto = el('controlesFiltrosUsuarios').classList.toggle('is-open'); el('mostrarFiltrosUsuarios').setAttribute('aria-expanded', String(abierto));
    });
    el('buscarUsuarios').addEventListener('input', () => { clearTimeout(timerBusqueda); ++versionLista; pagina = 1; prepararLista(); timerBusqueda = setTimeout(() => cargarUsuarios(), 300); });
    ['rolUsuarios', 'estadoUsuarios', 'ordenUsuarios'].forEach(id => el(id).addEventListener('change', () => { pagina = 1; cargarUsuarios(); }));
    el('filtrosUsuarios').addEventListener('submit', e => { e.preventDefault(); pagina = 1; cargarUsuarios(); });
    el('limpiarFiltrosUsuarios').addEventListener('click', () => { el('filtrosUsuarios').reset(); pagina = 1; cargarUsuarios(); });
    paginador.addEventListener('click', e => {
        const b = e.target.closest('button[data-page]'); if (!b || b.disabled) return;
        const n = Number(b.dataset.page); if (!Number.isInteger(n) || n < 1 || n > Math.ceil(total / TAMANO_PAGINA)) return;
        pagina = n; cargarUsuarios({enfocar: e.detail === 0}); el('filtrosUsuarios').scrollIntoView({block: 'start', behavior: 'auto'});
    });

    function estadoFormulario(modalId, formId, botonId, errorId, campos) {
        const estado = {elemento: el(modalId), form: el(formId), boton: el(botonId), errorId, campos, enviando: false, guardado: false, cargando: false, usuario: null, version: 0, origen: null};
        estado.modal = bootstrap.Modal.getOrCreateInstance(estado.elemento);
        estado.elemento.addEventListener('hide.bs.modal', e => { if (estado.enviando) e.preventDefault(); else ++estado.version; });
        estado.elemento.addEventListener('hidden.bs.modal', () => {
            if (estado.origen?.isConnected) estado.origen.focus({preventScroll: true});
            else resumen.focus({preventScroll: true});
        });
        Object.values(campos).forEach(id => el(id).addEventListener('input', () => { el(id).classList.remove('is-invalid'); el(id).removeAttribute('aria-invalid'); }));
        return estado;
    }
    const crear = estadoFormulario('modalNuevoUsuario', 'formCrearUsuario', 'guardarNuevoUsuario', 'errorCrearUsuario', {
        nombres: 'inputNombres', apellidos: 'inputApellidos', email: 'inputEmail', telefono: 'inputTelefono', rol_id: 'inputRol', password: 'inputPassword', password_confirmacion: 'inputPasswordConfirmacion',
    });
    const editar = estadoFormulario('modalEditarUsuario', 'formEditarUsuario', 'guardarEditarUsuario', 'errorEditarUsuario', {
        nombres: 'editNombres', apellidos: 'editApellidos', telefono: 'editTelefono', rol_id: 'editRol',
    });
    const accion = estadoFormulario('modalAccionUsuario', 'formAccionUsuario', 'confirmarAccionUsuario', 'errorAccionUsuario', {});
    function controles(estado) {
        const ocupado = estado.enviando || estado.guardado;
        estado.form.querySelectorAll('input, select, textarea').forEach(c => { c.disabled = ocupado || estado.cargando; });
        estado.elemento.querySelectorAll('[data-bs-dismiss]').forEach(b => { b.disabled = estado.enviando; });
        if (estado === crear) {
            el('inputRol').disabled = ocupado || !opcionesListas;
            estado.boton.disabled = ocupado || !opcionesListas || ![...roles.values()].some(r => r.activo);
            estado.boton.textContent = estado.enviando ? 'Creando usuario...' : estado.guardado ? 'Usuario creado' : 'Crear usuario';
        } else if (estado === editar) {
            el('editRol').disabled = ocupado || estado.cargando || !opcionesListas || !estado.usuario || protegida(estado.usuario);
            estado.boton.disabled = ocupado || estado.cargando || !estado.usuario || !opcionesListas;
            estado.boton.textContent = estado.enviando ? 'Guardando...' : estado.guardado ? 'Cambios guardados' : 'Guardar cambios';
        } else {
            estado.boton.disabled = ocupado || estado.cargando || !estado.usuario;
            estado.boton.textContent = estado.enviando ? 'Procesando...' : estado.guardado ? 'Acción completada' : estado.texto || 'Confirmar';
        }
    }
    function limpiarErrores(estado) {
        aviso(estado.errorId, '');
        Object.values(estado.campos).forEach(id => { el(id).classList.remove('is-invalid'); el(id).removeAttribute('aria-invalid'); el(id + 'Error').textContent = ''; });
    }
    function errorCampo(id, mensaje) { el(id).classList.add('is-invalid'); el(id).setAttribute('aria-invalid', 'true'); el(id + 'Error').textContent = mensaje; }
    function erroresServidor(estado, error) {
        let inline = false;
        Object.entries(error.datos?.errores || {}).forEach(([campo, mensaje]) => {
            const id = estado.campos[campo]; if (id) { errorCampo(id, mensajeError(mensaje)); inline = true; }
        });
        aviso(estado.errorId, inline ? 'Revisa los campos indicados.' : error.message);
        estado.form.querySelector('.is-invalid')?.focus();
        if (error.incierto) cargarUsuarios();
    }
    function descripcionRol(id, ayuda, usuario = null) {
        const r = roles.get(el(id).value) || (usuario && typeof usuario.rol === 'object' ? usuario.rol : null);
        el(ayuda).textContent = r ? r.descripcion || 'Este rol define las acciones disponibles para el usuario.' : 'Selecciona el rol que tendrá esta cuenta.';
    }
    function llenarRoles() {
        const valorFiltro = el('rolUsuarios').value, valorCrear = el('inputRol').value;
        el('rolUsuarios').replaceChildren(new Option('Todos', ''), ...[...roles.values()].map(r => new Option(r.nombre + (r.activo ? '' : ' (inactivo)'), String(r.id))));
        el('rolUsuarios').value = valorFiltro;
        el('inputRol').replaceChildren(new Option('Selecciona un rol...', ''), ...[...roles.values()].filter(r => r.activo).map(r => new Option(r.nombre, String(r.id))));
        el('inputRol').value = valorCrear;
        const valorEditar = editar.usuario ? String(rolId(editar.usuario) || '') : el('editRol').value;
        const disponibles = [...roles.values()].filter(r => r.activo || String(r.id) === valorEditar);
        if (editar.usuario?.rol && typeof editar.usuario.rol === 'object' && !disponibles.some(r => String(r.id) === valorEditar)) disponibles.push(editar.usuario.rol);
        el('editRol').replaceChildren(new Option('Sin rol asignado', ''), ...disponibles.map(r => new Option(r.nombre + (r.activo === false ? ' (inactivo)' : ''), String(r.id))));
        el('editRol').value = valorEditar;
        descripcionRol('inputRol', 'inputRolAyuda'); descripcionRol('editRol', 'editRolAyuda', editar.usuario);
    }
    async function cargarOpciones() {
        if (cargandoOpciones) return; cargandoOpciones = true; el('reintentarOpcionesUsuarios').disabled = true;
        try {
            const json = await apiFetch('/api/v1/usuarios/opciones/'), datos = json.data;
            if (!Array.isArray(datos?.roles) || !Array.isArray(datos.password_requisitos)) throw new Error('No se pudieron leer los roles y requisitos de contraseña.');
            roles = new Map(datos.roles.map(r => [String(r.id), r])); opcionesListas = true; llenarRoles(); el('rolUsuarios').disabled = false;
            el('requisitosPasswordUsuarios').replaceChildren(...datos.password_requisitos.map(texto => nodo('li', '', texto)));
            aviso('errorOpcionesUsuarios', ''); el('reintentarOpcionesUsuarios').classList.add('d-none');
        } catch (error) { aviso('errorOpcionesUsuarios', error.message); el('reintentarOpcionesUsuarios').classList.remove('d-none'); }
        finally { cargandoOpciones = false; el('reintentarOpcionesUsuarios').disabled = false; controles(crear); controles(editar); }
    }
    el('reintentarOpcionesUsuarios').addEventListener('click', cargarOpciones);
    el('inputRol').addEventListener('change', () => descripcionRol('inputRol', 'inputRolAyuda'));
    el('editRol').addEventListener('change', () => descripcionRol('editRol', 'editRolAyuda', editar.usuario));
    crear.elemento.addEventListener('show.bs.modal', e => {
        ++crear.version; crear.enviando = false; crear.guardado = false; crear.origen = e.relatedTarget || document.activeElement;
        crear.form.reset(); limpiarErrores(crear); descripcionRol('inputRol', 'inputRolAyuda');
        crear.form.querySelectorAll('[data-password-toggle]').forEach(b => {
            el(b.dataset.passwordToggle).type = 'password'; b.setAttribute('aria-pressed', 'false'); b.setAttribute('aria-label', 'Mostrar contraseña'); b.title = 'Mostrar contraseña';
            b.querySelector('i')?.classList.remove('fa-eye-slash'); b.querySelector('i')?.classList.add('fa-eye');
        });
        controles(crear);
    });
    crear.elemento.addEventListener('shown.bs.modal', () => { if (window.matchMedia('(min-width: 768px)').matches) el('inputNombres').focus(); });
    function validarFormulario(estado) {
        limpiarErrores(estado);
        for (const campo of ['nombres', 'apellidos']) if (!el(estado.campos[campo]).value.trim()) errorCampo(estado.campos[campo], 'Este campo es obligatorio.');
        if (estado === crear) {
            if (!el('inputEmail').value.trim() || el('inputEmail').validity.typeMismatch) errorCampo('inputEmail', 'Ingresa un correo electrónico válido.');
            if (!roles.get(el('inputRol').value)?.activo) errorCampo('inputRol', 'Selecciona un rol activo.');
            if (el('inputPassword').value.length < 8) errorCampo('inputPassword', 'La contraseña debe tener al menos 8 caracteres.');
            if (!el('inputPasswordConfirmacion').value || el('inputPassword').value !== el('inputPasswordConfirmacion').value) errorCampo('inputPasswordConfirmacion', 'Las contraseñas deben coincidir.');
        } else if (!protegida(estado.usuario) && el('editRol').value && el('editRol').value !== String(rolId(estado.usuario) || '') && !roles.get(el('editRol').value)?.activo) errorCampo('editRol', 'Selecciona un rol activo.');
        const invalido = estado.form.querySelector('.is-invalid'); if (invalido) { aviso(estado.errorId, 'Revisa los campos indicados.'); invalido.focus(); }
        return !invalido;
    }
    function actualizarSesion(u) {
        if (!propia(u)) return;
        sesion = {...sesion, nombres: u.nombres, apellidos: u.apellidos, nombre_completo: nombre(u)};
        localStorage.setItem('usuario', JSON.stringify(sesion)); perfil();
    }
    async function guardar(estado) {
        if (estado.enviando || estado.guardado || estado.cargando || !opcionesListas || (estado === editar && !estado.usuario)) return;
        if (!validarFormulario(estado)) return;
        const payload = {nombres: el(estado.campos.nombres).value.trim(), apellidos: el(estado.campos.apellidos).value.trim(), telefono: el(estado.campos.telefono).value.trim()};
        if (estado === crear) Object.assign(payload, {email: el('inputEmail').value.trim(), rol_id: Number(el('inputRol').value), password: el('inputPassword').value, password_confirmacion: el('inputPasswordConfirmacion').value});
        else if (!protegida(estado.usuario) && el('editRol').value !== String(rolId(estado.usuario) || '')) payload.rol_id = el('editRol').value ? Number(el('editRol').value) : null;
        estado.enviando = true; controles(estado);
        try {
            const json = await apiFetch('/api/v1/usuarios/' + (estado === crear ? '' : estado.usuario.id + '/'), {method: estado === crear ? 'POST' : 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
            if (!Number.isInteger(json.data?.id)) throw new Error('La operación respondió sin identificar al usuario. Revisa la lista antes de reintentar.');
            actualizarSesion(json.data); estado.guardado = true; estado.enviando = false; controles(estado);
            window.dispatchEvent(new Event('smartstock:notifications-changed'));
            estado.modal.hide(); if (estado === crear) pagina = 1; cargarUsuarios();
        } catch (error) { erroresServidor(estado, error); }
        finally { estado.enviando = false; controles(estado); }
    }
    crear.form.addEventListener('submit', e => { e.preventDefault(); guardar(crear); });
    editar.form.addEventListener('submit', e => { e.preventDefault(); guardar(editar); });
    async function abrirEditar(id, origen) {
        if (editar.enviando) return;
        const version = ++editar.version; editar.usuario = null; editar.origen = origen; editar.guardado = false; editar.cargando = true;
        editar.form.reset(); limpiarErrores(editar); el('editCorreo').textContent = ''; el('estadoEditarUsuario').textContent = 'Cargando usuario...';
        el('editRolProtegido').classList.add('d-none'); controles(editar); editar.modal.show();
        try {
            const json = await apiFetch('/api/v1/usuarios/' + id + '/'); if (version !== editar.version) return;
            const u = json.data || json; if (!Number.isInteger(u?.id)) throw new Error('No se pudo leer el usuario.');
            editar.usuario = u; el('editUserId').value = u.id; el('editCorreo').textContent = nombre(u) + ' · ' + u.email;
            el('editNombres').value = u.nombres || ''; el('editApellidos').value = u.apellidos || ''; el('editTelefono').value = u.telefono || '';
            llenarRoles(); el('editRolProtegido').classList.toggle('d-none', !protegida(u)); el('estadoEditarUsuario').textContent = '';
        } catch (error) { if (version === editar.version) aviso(editar.errorId, error.message); }
        finally { if (version === editar.version) { editar.cargando = false; controles(editar); } }
    }

    const detalleEl = el('modalDetalleUsuario'), detalleModal = bootstrap.Modal.getOrCreateInstance(detalleEl);
    let versionDetalle = 0, origenDetalle;
    async function abrirDetalle(id, origen) {
        const version = ++versionDetalle; origenDetalle = origen; el('datosDetalleUsuario').classList.add('d-none'); el('estadoDetalleUsuario').textContent = 'Cargando detalle...'; detalleModal.show();
        try {
            const json = await apiFetch('/api/v1/usuarios/' + id + '/'); if (version !== versionDetalle) return;
            const u = json.data || json; if (!Number.isInteger(u?.id)) throw new Error('No se pudo leer el detalle del usuario.');
            const datos = {Nombre: nombre(u), Correo: u.email, Id: '#' + u.id, Rol: rolNombre(u), Estado: u.activo ? 'Activo' : 'Inactivo', Telefono: u.telefono || 'Sin teléfono registrado', Creacion: u.fecha_creacion ? fechaVista(u.fecha_creacion) : 'No registrada', UltimoLogin: fechaVista(u.ultimo_login), Proteccion: protegida(u) ? 'Cuenta de administración protegida' : propia(u) ? 'Tu cuenta' : 'Cuenta estándar'};
            Object.entries(datos).forEach(([key, value]) => { el('detalleUsuario' + key).textContent = value; });
            el('datosDetalleUsuario').classList.remove('d-none'); el('estadoDetalleUsuario').textContent = '';
        } catch (error) { if (version === versionDetalle) el('estadoDetalleUsuario').textContent = error.message; }
    }
    detalleEl.addEventListener('hide.bs.modal', () => { ++versionDetalle; });
    detalleEl.addEventListener('hidden.bs.modal', () => { if (origenDetalle?.isConnected) origenDetalle.focus({preventScroll: true}); });
    const acciones = {
        desactivar: {titulo: 'Desactivar usuario', descripcion: 'Esta persona no podrá iniciar sesión. Su cuenta y su historial se conservarán.', metodo: 'DELETE', sufijo: '', clase: 'warning', resultado: 'usuario desactivado correctamente.'},
        reactivar: {titulo: 'Reactivar usuario', descripcion: 'Esta cuenta volverá a estar habilitada para iniciar sesión con su rol asignado.', metodo: 'POST', sufijo: 'activar/', clase: 'success', resultado: 'usuario reactivado correctamente.'},
        eliminar: {titulo: 'Eliminar definitivamente', descripcion: 'Se eliminará esta cuenta de forma permanente. Esta acción no se puede deshacer. Las cuentas con historial asociado deben desactivarse para conservar sus registros.', metodo: 'DELETE', sufijo: 'eliminar-definitivamente/', clase: 'danger', resultado: 'usuario eliminado definitivamente.'},
    };
    async function abrirAccion(tipo, id, origen) {
        if (accion.enviando) return;
        const config = acciones[tipo]; if (!config) return;
        const version = ++accion.version; Object.assign(accion, {tipo, usuario: null, origen, guardado: false, cargando: true, texto: config.titulo});
        aviso(accion.errorId, ''); el('tituloAccionUsuario').textContent = config.titulo; el('estadoAccionUsuario').textContent = 'Cargando usuario...';
        el('contenidoAccionUsuario').classList.add('d-none'); accion.boton.className = 'btn btn-' + config.clase; controles(accion); accion.modal.show();
        try {
            const json = await apiFetch('/api/v1/usuarios/' + id + '/'); if (version !== accion.version) return;
            const u = json.data || json; if (!Number.isInteger(u?.id)) throw new Error('No se pudo leer el usuario.');
            if (tipo !== 'reactivar' && (protegida(u) || propia(u))) throw new Error('Esta cuenta está protegida y no permite esta acción.');
            if (tipo === 'desactivar' && !u.activo) throw new Error('El usuario ya está inactivo. Actualiza la lista.');
            if (tipo === 'reactivar' && u.activo) throw new Error('El usuario ya está activo. Actualiza la lista.');
            accion.usuario = u; el('nombreAccionUsuario').textContent = nombre(u); el('correoAccionUsuario').textContent = u.email;
            el('descripcionAccionUsuario').textContent = config.descripcion; el('contenidoAccionUsuario').classList.remove('d-none'); el('estadoAccionUsuario').textContent = '';
        } catch (error) { if (version === accion.version) aviso(accion.errorId, error.message); }
        finally { if (version === accion.version) { accion.cargando = false; controles(accion); } }
    }
    accion.form.addEventListener('submit', async e => {
        e.preventDefault(); if (accion.enviando || accion.guardado || accion.cargando || !accion.usuario) return;
        accion.enviando = true; controles(accion); aviso(accion.errorId, ''); const config = acciones[accion.tipo];
        try {
            await apiFetch('/api/v1/usuarios/' + accion.usuario.id + '/' + config.sufijo, {method: config.metodo});
            accion.guardado = true; accion.enviando = false; controles(accion);
            window.dispatchEvent(new Event('smartstock:notifications-changed')); accion.modal.hide(); cargarUsuarios();
        } catch (error) { aviso(accion.errorId, error.message); if (error.incierto) cargarUsuarios(); }
        finally { accion.enviando = false; controles(accion); }
    });
    tabla.addEventListener('click', e => {
        const b = e.target.closest('button[data-accion]'); if (!b || b.disabled) return;
        const id = Number(b.dataset.id); if (!Number.isInteger(id) || id <= 0) return;
        if (b.dataset.accion === 'detalle') abrirDetalle(id, b);
        else if (b.dataset.accion === 'editar') abrirEditar(id, b);
        else abrirAccion(b.dataset.accion, id, b);
    });
    controles(crear); controles(editar); controles(accion); cargarUsuarios(); cargarOpciones();
});
