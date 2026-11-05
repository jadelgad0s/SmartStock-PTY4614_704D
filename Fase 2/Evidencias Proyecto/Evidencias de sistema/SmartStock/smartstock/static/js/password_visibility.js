/* Permite mostrar u ocultar contraseñas sin alterar formularios ni sus valores. */
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-password-toggle]').forEach((button) => {
    const campo = document.getElementById(button.dataset.passwordToggle);
    if (!campo || campo.tagName !== 'INPUT' || campo.type !== 'password') return;

    button.addEventListener('click', () => {
      const visible = campo.type === 'password';
      campo.type = visible ? 'text' : 'password';
      button.setAttribute('aria-pressed', String(visible));

      const descripcion = visible ? 'Ocultar contraseña' : 'Mostrar contraseña';
      button.setAttribute('aria-label', descripcion);
      button.title = descripcion;

      const icono = button.querySelector('i');
      if (icono) {
        icono.classList.toggle('fa-eye', !visible);
        icono.classList.toggle('fa-eye-slash', visible);
      }
    });
  });
});
