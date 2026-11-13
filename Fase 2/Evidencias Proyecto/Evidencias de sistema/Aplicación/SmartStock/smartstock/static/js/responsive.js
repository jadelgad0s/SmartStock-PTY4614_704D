/* Navegación móvil de SmartStock. Los elementos y clases ya existen en HTML. */
document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.querySelector('.ss-sidebar');
  const toggle = document.querySelector('.ss-menu-toggle');
  const closeButton = document.querySelector('.ss-sidebar-close');
  if (!sidebar || !toggle || !closeButton) return;

  const backdrop = document.createElement('div');
  backdrop.className = 'ss-sidebar-backdrop';
  backdrop.hidden = true;
  document.body.appendChild(backdrop);

  const desktop = window.matchMedia('(min-width: 992px)');
  function openMenu() {
    if (desktop.matches) return;
    sidebar.classList.add('ss-sidebar-open');
    document.body.classList.add('ss-menu-open');
    backdrop.hidden = false;
    toggle.setAttribute('aria-expanded', 'true');
    toggle.setAttribute('aria-label', 'Cerrar menú');
    closeButton.focus();
  }
  function closeMenu(returnFocus = false) {
    const wasOpen = sidebar.classList.contains('ss-sidebar-open');
    sidebar.classList.remove('ss-sidebar-open');
    document.body.classList.remove('ss-menu-open');
    backdrop.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-label', 'Abrir menú');
    if (wasOpen && returnFocus) toggle.focus();
  }

  toggle.addEventListener('click', () => {
    if (sidebar.classList.contains('ss-sidebar-open')) closeMenu(true);
    else openMenu();
  });
  closeButton.addEventListener('click', () => closeMenu(true));
  backdrop.addEventListener('click', () => closeMenu(true));
  sidebar.querySelectorAll('a[href]').forEach(a => a.addEventListener('click', () => closeMenu()));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && sidebar.classList.contains('ss-sidebar-open')) {
      closeMenu(true);
    }
  });
  desktop.addEventListener('change', () => closeMenu());
});
