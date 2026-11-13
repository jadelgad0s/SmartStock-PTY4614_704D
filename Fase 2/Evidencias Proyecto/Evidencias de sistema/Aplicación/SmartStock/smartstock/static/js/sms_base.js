/* Permisos y solicitudes SMS. Consultar la pantalla nunca procesa envíos. */
(() => {
    'use strict';
    let renovacion = null, consultaAcceso = null;
    const textoError = v => typeof v === 'string' ? v : Array.isArray(v) ? v.map(textoError).join(' ') : v && typeof v === 'object' ? Object.values(v).map(textoError).join(' ') : '';
    async function renovar() {
        if (!renovacion) renovacion = (async () => {
            const refresh = localStorage.getItem('refresh_token'); if (!refresh) return false;
            const r = await fetch('/api/v1/auth/refresh/', {method:'POST',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify({refresh})});
            if (r.status >= 500) throw new Error('No se pudo renovar la sesión. Inténtalo nuevamente.');
            const j = await r.json(), d = j.data || j; if (!r.ok || !d.access) return false;
            localStorage.setItem('access_token',d.access);if(d.refresh)localStorage.setItem('refresh_token',d.refresh);return true;
        })().finally(() => { renovacion = null; });
        return renovacion;
    }
    async function json(url,{method='GET',body,renovarSesion=true}={}) {
        const inicial=localStorage.getItem('access_token'), mutacion=method!=='GET';
        const enviar=()=>fetch(url,{method,cache:'no-store',headers:{Authorization:'Bearer '+localStorage.getItem('access_token'),...(body!==undefined?{'Content-Type':'application/json'}:{})},...(body!==undefined?{body:JSON.stringify(body)}:{})});
        let r;
        try {r=await enviar();if(r.status===401&&(inicial!==localStorage.getItem('access_token')||renovarSesion&&await renovar()))r=await enviar();}
        catch (_) {const e=new Error(mutacion?'No pudimos confirmar el resultado. Actualiza el historial antes de volver a procesar.':'No se pudo conectar con el servidor. Vuelve a intentarlo.');e.incierto=mutacion;throw e;}
        let j;try{j=await r.json();}catch(_){const e=new Error(mutacion?'No se pudo confirmar el resultado. Actualiza el historial para comprobarlo.':'La respuesta no se pudo leer. Reintenta la consulta.');e.incierto=mutacion;throw e;}
        if(!r.ok||j.success===false){const e=new Error(r.status===401?'La sesión expiró. Vuelve a iniciar sesión.':r.status===403?'No tienes permiso para gestionar los SMS.':textoError(j.errores||j.mensaje||j.detail||j)||'No se pudo completar la operación.');e.status=r.status;e.incierto=mutacion&&r.status>=500;throw e;}
        return j;
    }
    function acceso() {
        if(!consultaAcceso)consultaAcceso=json('/api/v1/alertas-sms/acceso/',{renovarSesion:Boolean(document.getElementById('panelSMS'))}).then(j=>{
            if(typeof j.data?.ver!=='boolean'||typeof j.data.procesar!=='boolean')throw new Error('No se pudieron comprobar los permisos SMS.');return j.data;
        }).catch(e=>{consultaAcceso=null;throw e;});return consultaAcceso;
    }
    window.SmartStockSMS={json,acceso};
    document.addEventListener('DOMContentLoaded',()=>{
        if (window.SmartStockNavegacion) return;
        const enlace=document.getElementById('menu-sms');if(!enlace||!localStorage.getItem('access_token'))return;
        let reintentos=0;
        async function actualizar(){try{enlace.hidden=!(await acceso()).ver;}catch(e){enlace.hidden=true;if(e.status===401&&reintentos++<2)setTimeout(actualizar,1000);}}
        actualizar();
    });
})();
