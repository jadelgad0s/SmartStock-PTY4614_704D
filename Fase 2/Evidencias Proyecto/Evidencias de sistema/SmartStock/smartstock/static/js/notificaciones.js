/* Campanita de notificaciones: no solicita permiso de navegador automáticamente. */
(() => {
  'use strict';
  document.addEventListener('DOMContentLoaded', async () => {
    if (window.SmartStockNavegacion && !await window.SmartStockNavegacion.lista) return;
    const logout = document.querySelector('[id^="btn-logout"]');
    const token = localStorage.getItem('access_token');
    if (!logout || !token || !logout.parentElement || document.getElementById('ss-notif-btn')) return;

    const wrap = document.createElement('div');
    wrap.className = 'dropdown me-2 ss-notif-wrap';
    wrap.id = 'ss-notif-wrap';
    wrap.innerHTML = `<button type="button" class="btn btn-outline-secondary position-relative"
       id="ss-notif-btn" data-bs-toggle="dropdown" aria-expanded="false" data-bs-display="static"
       aria-label="Notificaciones"><i class="fa-regular fa-bell"></i>
       <span class="badge rounded-pill bg-danger position-absolute top-0 start-100 translate-middle"
        id="ss-notif-count" hidden></span></button>
       <div class="dropdown-menu dropdown-menu-end shadow p-0 ss-notif-menu">
         <div class="d-flex justify-content-between align-items-center px-3 py-2 border-bottom ss-notif-header">
           <strong>Notificaciones</strong>
           <button type="button" class="btn btn-link btn-sm" id="ss-notif-read-all" disabled>Marcar todas</button>
         </div>
         <p id="ss-notif-error" class="text-danger small px-3 py-2 mb-0" role="alert" hidden></p>
         <div id="ss-notif-list" class="p-2 text-muted small" role="status">Cargando...</div>
       </div>`;
    logout.parentElement.insertBefore(wrap, logout);
    const items = wrap.querySelector('#ss-notif-list');
    const badge = wrap.querySelector('#ss-notif-count');
    const botonCampana = wrap.querySelector('#ss-notif-btn');
    const iconoCampana = botonCampana.querySelector('i');
    const leerTodas = wrap.querySelector('#ss-notif-read-all');
    const errorAvisos = wrap.querySelector('#ss-notif-error');
    const mostrarError = mensaje => { errorAvisos.textContent = mensaje || ''; errorAvisos.hidden = !mensaje; };
    // Conservar la referencia entre módulos de la misma pestaña para no
    // perder una notificación recibida justo antes de navegar.
    const datosUsuario = (() => {
      try { return JSON.parse(localStorage.getItem('usuario') || '{}'); }
      catch (_) { return {}; }
    })();
    const claveVistos = 'ss-notificaciones-vistas:' + String(datosUsuario.id || 'sin-id');
    const recuperarVistos = () => {
      try {
        const valor = JSON.parse(sessionStorage.getItem(claveVistos) || 'null');
        return Array.isArray(valor) ? new Set(valor.map(Number).filter(Number.isSafeInteger)) : null;
      } catch (_) { return null; }
    };
    const recordarVistos = (ids) => {
      try { sessionStorage.setItem(claveVistos, JSON.stringify([...ids])); }
      catch (_) { /* La campana también funciona sin almacenamiento. */ }
    };
    let idsAnteriormenteVistos = recuperarVistos();
    // Aviso dentro de la aplicación: no requiere permisos del sistema operativo.
    const aviso = document.createElement('div');
    aviso.className = 'toast ss-notif-toast';
    aviso.setAttribute('role', 'status');
    aviso.setAttribute('aria-live', 'polite');
    aviso.innerHTML = '<div class="toast-header"><i class="fa-solid fa-bell text-danger me-2"></i><strong class="me-auto">Nueva notificación de SmartStock</strong><button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Cerrar"></button></div><div class="toast-body" id="ss-notif-toast-text"></div>';
    const avisos = document.createElement('div');
    avisos.className = 'ss-notif-toast-container toast-container';
    avisos.append(aviso);
    document.body.append(avisos);
    const toast = bootstrap.Toast.getOrCreateInstance(aviso, {delay: 6000, autohide: true});

    const allowedRoutes = new Set(['/inicio-bodega/', '/movimientos/', '/mermas/', '/productos/', '/bodegas/', '/ubicaciones/', '/alertas-sms/', '/transferencias/', '/usuarios/', '/auditoria/']);
    const auth = () => ({Authorization: 'Bearer ' + (localStorage.getItem('access_token') || '')});
    const text = (tag, content, cls) => {
      const el = document.createElement(tag);
      el.className = cls || '';
      el.textContent = String(content ?? '');
      return el;
    };
    let loading = false, repetirCarga = false, leyendoTodas = false, firmaLista = '', total = 0;
    const leyendo = new Set();
    function rutaSegura(link) {
      if (typeof link !== 'string' || !link.startsWith('/')) return null;
      try {
        const url = new URL(link, window.location.origin);
        return url.origin === window.location.origin && allowedRoutes.has(url.pathname) ? url.pathname + url.search + url.hash : null;
      } catch (_) { return null; }
    }

    async function cargar() {
      if (!localStorage.getItem('access_token')) return;
      // Un guardado puede terminar mientras la primera consulta sigue en curso.
      // Se conserva una recarga pendiente, sin lanzar consultas en paralelo.
      if (loading) { repetirCarga = true; return; }
      loading = true;
      try {
        const response = await fetch('/api/v1/productos/notificaciones/no-leidas/', {
          headers: auth(), cache: 'no-store'
        });
        if (!response.ok) {
          mostrarError('No se pudieron consultar las notificaciones. Abre la campana para reintentar.');
          return;
        }
        const json = await response.json();
        const data = json.data;
        if (!data || !Number.isSafeInteger(data.total) || data.total < 0 || !Array.isArray(data.items)) throw new Error('Respuesta de notificaciones inválida.');
        const count = data.total; total = count; mostrarError(''); leerTodas.disabled = leyendoTodas || !count;
        const pendientes = count > 0;
        badge.hidden = !pendientes;
        badge.style.display = pendientes ? 'inline-flex' : 'none';
        badge.textContent = count > 99 ? '99+' : String(count);
        botonCampana.classList.toggle('ss-has-notifications', pendientes);
        botonCampana.setAttribute('aria-label', pendientes
          ? `Notificaciones: ${count} sin leer` : 'Sin notificaciones nuevas');
        iconoCampana.className = pendientes ? 'fa-solid fa-bell' : 'fa-regular fa-bell';
        const list = data.items.filter(item => Number.isSafeInteger(item.id) && item.id > 0);
        const idsActuales = new Set(list.map(item => Number(item.id)));
        if (idsAnteriormenteVistos !== null) {
          const mayorVisto = Math.max(0, ...idsAnteriormenteVistos);
          // Al leer uno de los primeros 20 avisos, puede aparecer otro más
          // antiguo. No se vuelve a anunciar como si acabara de llegar.
          const nuevas = list.filter(item => !idsAnteriormenteVistos.has(item.id) && item.id > mayorVisto);
          if (nuevas.length) {
            const noticia = nuevas[0];
            aviso.querySelector('#ss-notif-toast-text').textContent =
              nuevas.length === 1
                ? `${noticia.titulo}: ${noticia.mensaje}`
                : `Tienes ${nuevas.length} notificaciones nuevas. Última: ${noticia.titulo}`;
            toast.show();
            botonCampana.classList.remove('ss-notif-just-arrived');
            // Reinicia la animación si llegan más avisos sin cambiar de página.
            void botonCampana.offsetWidth;
            botonCampana.classList.add('ss-notif-just-arrived');
          }
        }
        idsAnteriormenteVistos = new Set([...(idsAnteriormenteVistos || []), ...idsActuales].sort((a, b) => b - a).slice(0, 200));
        recordarVistos(idsAnteriormenteVistos);
        const firma = JSON.stringify(list);
        if (firma === firmaLista) return; // Conservar el foco al sondear una lista sin cambios.
        firmaLista = firma; items.replaceChildren();
        if (!list.length) {
          items.append(text('div', 'No tienes notificaciones nuevas.', 'p-3 text-center'));
        } else {
          for (const entry of list) {
            const card = document.createElement('button');
            card.type = 'button';
            card.className = 'btn btn-light text-start d-block w-100 mb-1 border ss-notif-item';
            card.disabled = leyendo.has(entry.id);
            card.append(text('span', entry.titulo, 'fw-semibold d-block'));
            card.append(text('small', entry.mensaje, 'd-block text-muted'));
            card.append(text('small', entry.fecha, 'd-block text-secondary'));
            card.addEventListener('click', async () => {
              const id = Number(entry.id);
              if (!Number.isSafeInteger(id) || id < 1 || leyendo.has(id)) return;
              leyendo.add(id); card.disabled = true; mostrarError('');
              try {
                const r = await fetch(`/api/v1/productos/notificaciones/${id}/marcar-leida/`, {method: 'POST', headers: auth()});
                if (!r.ok) throw new Error('No se pudo marcar la notificación como leída.');
                await cargar(); if (canal) canal.postMessage('actualizar');
                const ruta = rutaSegura(entry.link); if (ruta) window.location.assign(ruta);
              } catch (_) { mostrarError('No se pudo marcar la notificación como leída. Vuelve a intentarlo.'); }
              finally { leyendo.delete(id); card.disabled = false; }
            });
            items.append(card);
          }
        }
      } catch (e) {
        mostrarError('No se pudieron cargar las notificaciones. Abre la campana para reintentar.');
      } finally {
        if (!errorAvisos.hidden && !firmaLista) items.textContent = 'Consulta de avisos no disponible.';
        loading = false;
        if (repetirCarga) { repetirCarga = false; cargar(); }
      }
    }
    leerTodas.addEventListener('click', async () => {
      if (leyendoTodas || !total) return;
      leyendoTodas = true; leerTodas.disabled = true; mostrarError('');
      try {
        const response = await fetch('/api/v1/productos/notificaciones/marcar-todas-leidas/', {method: 'POST', headers: auth()});
        if (!response.ok) throw new Error('No se pudieron marcar las notificaciones.');
        await cargar(); if (canal) canal.postMessage('actualizar');
      } catch (_) { mostrarError('No se pudieron marcar las notificaciones como leídas. Vuelve a intentarlo.'); }
      finally { leyendoTodas = false; leerTodas.disabled = !total; }
    });
    // Se consulta en primer plano cada 10 segundos. Render funciona con
    // WSGI, por lo que no hay push nativo; no prometemos entrega instantánea.
    cargar();
    setInterval(() => { if (!document.hidden) cargar(); }, 10000);
    // Avisar a otras pestañas abiertas del mismo navegador tras una
    // operación de inventario. Para otras sesiones seguimos con el sondeo.
    const canal = typeof BroadcastChannel !== 'undefined'
      ? new BroadcastChannel('smartstock-notificaciones') : null;
    if (canal) {
      canal.addEventListener('message', (evento) => {
        if (evento.data === 'actualizar') cargar();
      });
    }
    window.addEventListener('smartstock:notifications-changed', () => {
      cargar();
      if (canal) canal.postMessage('actualizar');
    });
    window.addEventListener('pagehide', () => { if (canal) canal.close(); });
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) cargar();
    });
    window.addEventListener('focus', () => {
      if (!document.hidden) cargar();
    });
    const boton = wrap.querySelector('#ss-notif-btn');
    const menu = wrap.querySelector('.ss-notif-menu');
    // Un dropdown de Bootstrap alineado al botón puede quedar fuera de la
    // pantalla en móviles. CSS usa esta coordenada del botón como referencia.
    const ubicarMenu = () => {
      const top = Math.ceil(boton.getBoundingClientRect().bottom + 8);
      wrap.style.setProperty('--ss-notif-top', Math.max(0, top) + 'px');
    };
    boton.addEventListener('click', () => {
      toast.hide();
      ubicarMenu();
      cargar();
    });
    window.addEventListener('resize', () => {
      if (menu.classList.contains('show')) ubicarMenu();
    });
  });
})();

