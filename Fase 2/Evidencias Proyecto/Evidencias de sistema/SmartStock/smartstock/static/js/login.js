document.addEventListener('DOMContentLoaded', () => {
  'use strict';
  const form = document.getElementById('login-form');
  if (!form) return;
  const correo = document.getElementById('email'), clave = document.getElementById('password');
  const boton = document.getElementById('login-submit'), aviso = document.getElementById('alert-box');
  let enviando = false, completado = false;
  const mensaje = texto => { aviso.textContent = texto; aviso.hidden = !texto; };
  const estado = () => {
    const ocupado = enviando || completado;
    boton.disabled = ocupado;
    boton.textContent = completado ? 'Abriendo SmartStock…' : enviando ? 'Iniciando sesión…' : 'Iniciar sesión';
    form.setAttribute('aria-busy', String(ocupado));
    correo.readOnly = ocupado; clave.readOnly = ocupado;
  };
  [correo,clave].forEach(campo => campo.addEventListener('input', () => { if (!enviando) mensaje(''); }));
  form.addEventListener('submit', async evento => {
    evento.preventDefault();
    if (enviando || completado || !form.reportValidity()) return;
    const payload = {email:correo.value.trim(), password:clave.value};
    enviando = true; estado(); mensaje('');
    try {
      const csrf = new FormData(form).get('csrfmiddlewaretoken');
      const respuesta = await fetch(form.action, {
        method: 'POST', cache: 'no-store',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
        body: JSON.stringify(payload),
      });
      let datos;
      try { datos = await respuesta.json(); }
      catch (_) { throw new Error('El servidor no respondió como esperábamos. Inténtalo nuevamente.'); }
      if (!respuesta.ok || !datos?.success) {
        const texto = respuesta.status === 401 ? 'No pudimos iniciar sesión. Revisa tu correo y contraseña o inténtalo más tarde.' : respuesta.status === 429 ? 'Has realizado varios intentos. Espera un momento antes de volver a ingresar.' :
          respuesta.status >= 500 ? 'No pudimos iniciar sesión en este momento. Inténtalo nuevamente.' : typeof datos?.mensaje === 'string' ? datos.mensaje : 'No se pudo iniciar sesión. Inténtalo nuevamente.';
        throw new Error(texto);
      }
      const d = datos.data;
      if (!d || typeof d.access !== 'string' || !d.access || typeof d.refresh !== 'string' || !d.refresh || !Number.isSafeInteger(d.usuario?.id) || d.usuario.id < 1) throw new Error('La respuesta de inicio de sesión está incompleta. Inténtalo nuevamente.');
      try {
        localStorage.setItem('access_token',d.access);
        localStorage.setItem('refresh_token',d.refresh);
        localStorage.setItem('usuario',JSON.stringify(d.usuario));
      } catch (_) {
        for (const key of ['access_token','refresh_token','usuario']) { try { localStorage.removeItem(key); } catch (_) {} }
        throw new Error('No se pudo guardar la sesión. Revisa que tu navegador permita almacenamiento e inténtalo nuevamente.');
      }
      completado = true;
      window.location.href = /^\/[a-z-]+\/$/.test(d.inicio) ? d.inicio : '/';
    } catch (error) {
      mensaje(error instanceof TypeError ? 'No se pudo conectar con SmartStock. Revisa tu conexión e inténtalo nuevamente.' : error.message);
      aviso.focus();
    } finally { enviando = false; estado(); }
  });
  window.addEventListener('pageshow', evento => { if (evento.persisted) { enviando = false; completado = false; estado(); } });
});
