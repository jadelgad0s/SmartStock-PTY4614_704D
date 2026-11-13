/* Acceso compartido a reportes. Los permisos se consultan en el servidor. */
(() => {
    'use strict';
    let renovacion = null, consultaAcceso = null;
    async function renovar() {
        if (!renovacion) renovacion = (async () => {
            const refresh = localStorage.getItem('refresh_token');
            if (!refresh) return false;
            try {
                const r = await fetch('/api/v1/auth/refresh/', {method: 'POST', cache: 'no-store', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({refresh})});
                const json = await r.json(), datos = json.data || json;
                if (!r.ok || !datos.access) return false;
                localStorage.setItem('access_token', datos.access);
                if (datos.refresh) localStorage.setItem('refresh_token', datos.refresh);
                return true;
            } catch (_) { return false; }
        })().finally(() => { renovacion = null; });
        return renovacion;
    }
    const textoError = valor => typeof valor === 'string' ? valor : Array.isArray(valor) ? valor.map(textoError).join(' ') : valor && typeof valor === 'object' ? Object.values(valor).map(textoError).join(' ') : '';
    async function solicitar(url, {renovarSesion = true} = {}) {
        const original = localStorage.getItem('access_token');
        const enviar = () => fetch(url, {cache: 'no-store', headers: {Authorization: 'Bearer ' + localStorage.getItem('access_token')}});
        let r;
        try { r = await enviar(); if (r.status === 401 && (localStorage.getItem('access_token') !== original || renovarSesion && await renovar())) r = await enviar(); }
        catch (_) { throw new Error('No se pudo conectar con el servidor. Vuelve a intentarlo.'); }
        if (!r.ok) {
            let datos = {}; try { datos = await r.json(); } catch (_) {}
            const error = new Error(r.status === 401 ? 'Tu sesión expiró. Vuelve a iniciar sesión.' : r.status === 403 ? 'No tienes permiso para esta operación.' : textoError(datos.errores || datos.mensaje || datos.detail || datos) || 'No se pudo preparar el reporte.');
            error.status = r.status; throw error;
        }
        return r;
    }
    async function json(url, opciones) {
        const r = await solicitar(url, opciones);
        try { return await r.json(); } catch (_) { throw new Error('El servidor devolvió una respuesta que no se pudo leer.'); }
    }
    function acceso() {
        // En las pantallas existentes, su propio módulo renueva la sesión.
        // El enlace del menú no debe competir por el mismo refresh rotativo.
        if (!consultaAcceso) consultaAcceso = json('/api/v1/reportes/acceso/', {renovarSesion: Boolean(document.getElementById('filtrosReportes'))}).then(r => {
            if (typeof r.data?.ver !== 'boolean' || typeof r.data.exportar !== 'boolean') throw new Error('No se pudieron comprobar los permisos de reportes.');
            return r.data;
        }).catch(e => { consultaAcceso = null; throw e; });
        return consultaAcceso;
    }
    window.SmartStockReportes = {solicitar, json, acceso};
    document.addEventListener('DOMContentLoaded', () => {
        if (window.SmartStockNavegacion) return;
        const enlace = document.getElementById('menu-reportes');
        if (!enlace || !localStorage.getItem('access_token')) return;
        let reintentos = 0;
        async function actualizar() {
            if (!localStorage.getItem('access_token')) { enlace.hidden = true; return; }
            try { enlace.hidden = !(await acceso()).ver; }
            catch (e) {
                enlace.hidden = true;
                if (e.status === 401 && reintentos++ < 2) setTimeout(actualizar, 1000);
            }
        }
        actualizar();
    });
})();
