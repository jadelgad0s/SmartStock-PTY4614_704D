/* Estado de envío de formularios de recuperación con POST nativo y CSRF. */
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('form[data-auth-submit]').forEach(form => {
    const boton = form.querySelector('button[type="submit"]');
    if (!boton) return;
    const texto = boton.textContent;
    let enviando = false;
    const estado = activo => {
      enviando = activo;
      boton.disabled = activo;
      boton.textContent = activo ? form.dataset.authSubmit : texto;
      form.setAttribute('aria-busy', String(activo));
      form.querySelectorAll('input:not([type="hidden"])').forEach(campo => { campo.readOnly = activo; });
    };
    form.addEventListener('submit', evento => {
      if (enviando || evento.defaultPrevented) { evento.preventDefault(); return; }
      if (!form.checkValidity()) { evento.preventDefault(); form.reportValidity(); return; }
      estado(true);
    });
    window.addEventListener('pageshow', evento => { if (evento.persisted) estado(false); });
  });
});
