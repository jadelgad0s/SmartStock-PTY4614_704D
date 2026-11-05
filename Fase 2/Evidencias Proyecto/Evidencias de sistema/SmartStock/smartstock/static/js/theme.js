/* Tema de las vistas autenticadas. Preferencia local por navegador. */
(() => {
  const KEY = 'smartstock-theme';
  const root = document.documentElement;

  // Los demás módulos usan esto al cerrar sesión para no borrar la
  // preferencia de visualización junto con los tokens de autenticación.
  window.smartstockClearSession = function () {
    let preferencia = null;
    try { preferencia = localStorage.getItem(KEY); } catch (_) {}
    localStorage.clear();
    if (preferencia === 'dark' || preferencia === 'light') {
      try { localStorage.setItem(KEY, preferencia); } catch (_) {}
    }
  };

  document.addEventListener('DOMContentLoaded', () => {
    if (!document.querySelector('.ss-app-layout')) return;
    const controles = [...document.querySelectorAll('.ss-theme-toggle')];
    if (!controles.length) return;

    const aplicar = (modo, guardar) => {
      const oscuro = modo === 'dark';
      root.setAttribute('data-bs-theme', oscuro ? 'dark' : 'light');
      for (const control of controles) {
        const accion = oscuro ? 'Activar modo claro' : 'Activar modo oscuro';
        control.setAttribute('aria-label', accion);
        control.setAttribute('title', accion);
        control.setAttribute('aria-pressed', String(oscuro));
        const icono = control.querySelector('i');
        if (icono) icono.className = oscuro ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
        const texto = control.querySelector('.ss-theme-label');
        if (texto) texto.textContent = oscuro ? 'Claro' : 'Oscuro';
      }
      if (guardar) {
        try { localStorage.setItem(KEY, oscuro ? 'dark' : 'light'); } catch (_) {}
      }
      window.dispatchEvent(new CustomEvent('smartstock:themechange', {
        detail: {theme: oscuro ? 'dark' : 'light'}
      }));
    };

    aplicar(root.getAttribute('data-bs-theme') === 'dark' ? 'dark' : 'light', false);
    for (const control of controles) {
      control.addEventListener('click', () => {
        aplicar(root.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark', true);
      });
    }
    window.addEventListener('storage', (evento) => {
      if (evento.key === KEY) aplicar(evento.newValue === 'dark' ? 'dark' : 'light', false);
    });
  });
})();
