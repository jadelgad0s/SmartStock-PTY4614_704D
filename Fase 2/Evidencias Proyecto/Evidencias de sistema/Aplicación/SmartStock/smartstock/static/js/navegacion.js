/* El menú y el acceso a cada pantalla se resuelven con la cuenta del servidor. */
(() => {
    'use strict';
    const menu = document.getElementById('ss-navigation');
    if (!menu) return;

    const panel = document.querySelector('.ss-app-layout');
    const estado = document.getElementById('ss-acceso-estado');
    const texto = document.getElementById('ss-acceso-texto');
    const reintentar = document.getElementById('ss-acceso-reintentar');
    const ruta = location.pathname.replace(/\/?$/, '/');
    reintentar.addEventListener('click', () => location.reload());

    function cerrarSesion() {
        const formulario = document.getElementById('ss-cerrar-sesion');
        formulario.elements.namedItem('refresh').value = localStorage.getItem('refresh_token') || '';
        window.smartstockClearSession();
        formulario.submit();
    }
    for (const boton of document.querySelectorAll('#ss-acceso-salir, #btn-logout, button[id^="btn-logout-"]')) {
        boton.addEventListener('click', cerrarSesion);
    }

    function actualizarMenu(datos) {
        const logo = menu.querySelector('[data-ss-inicio]');
        if (logo) logo.href = datos.inicio;
        const inicioBodega = menu.querySelector('#ss-enlace-inicio-bodega');
        inicioBodega.hidden = datos.inicio !== '/inicio-bodega/';
        for (const enlace of menu.querySelectorAll('.sidebar-item')) {
            const item = enlace.closest('li');
            if (item) {
                const permitido = datos.modulos.includes(enlace.getAttribute('href'));
                item.toggleAttribute('data-ss-menu-denegado', !permitido);
                if (permitido && item !== inicioBodega) item.hidden = false;
            }
            if (enlace.getAttribute('href') === ruta) enlace.setAttribute('aria-current', 'page');
        }
        const sistema = menu.querySelector('#menu-sistema-title');
        if (sistema) sistema.hidden = !['/usuarios/', '/alertas-sms/', '/admin/'].some(p => datos.modulos.includes(p));
    }

    async function comprobar() {
        panel.removeAttribute('data-ss-autorizado');
        if (!localStorage.getItem('access_token')) {
            cerrarSesion();
            return null;
        }

        estado.hidden = false;
        texto.textContent = 'Comprobando tu acceso a SmartStock…';
        reintentar.hidden = true;
        try {
            const {data} = await window.SmartStockReportes.json('/api/v1/auth/navegacion/');
            if (!Array.isArray(data?.modulos) || !data.usuario?.id ||
                data.inicio !== '/' && (!/^\/[a-z-]+\/$/.test(data.inicio) || !data.modulos.includes(data.inicio))) {
                throw new Error('No se pudo leer la configuración de tu cuenta.');
            }
            if (!data.modulos.includes(ruta)) {
                location.replace(data.inicio);
                return null;
            }

            localStorage.setItem('usuario', JSON.stringify(data.usuario));
            actualizarMenu(data);
            estado.hidden = true;
            panel.setAttribute('data-ss-autorizado', '');
            return data;
        } catch (error) {
            if (error.status === 401) {
                cerrarSesion();
                return null;
            }
            texto.textContent = error.status === 403
                ? 'Tu cuenta necesita un rol activo. Contacta al administrador.'
                : 'No pudimos comprobar tu acceso. Vuelve a intentarlo.';
            reintentar.hidden = error.status === 403;
            return null;
        }
    }

    const navegacion = {lista: comprobar()};
    window.SmartStockNavegacion = navegacion;
    window.addEventListener('pageshow', evento => {
        if (evento.persisted) navegacion.lista = comprobar();
    });
})();
