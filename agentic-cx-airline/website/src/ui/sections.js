// Comportamiento de las secciones del sitio "AeroLatam".
//
// Contrato de marcado (lo provee index.html):
//   - Enlaces de navegación con [data-nav-link] cuyo href apunta a un ancla
//     interna (p. ej. href="#productos").
//   - Botón de menú móvil con [data-nav-toggle].
//   - Contenedor de navegación con id="site-nav" (se alterna la clase is-open).
//
// Provee navegación con desplazamiento suave a las secciones (Productos,
// Sucursales, Ayuda) y el toggle del menú en móvil.

const NAV_ID = 'site-nav';
const NAV_OPEN_CLASS = 'is-open';

/** Desplaza suavemente hasta la sección destino indicada por un ancla (#id). */
function scrollToHash(hash) {
  if (!hash || hash === '#') return;
  const target = document.querySelector(hash);
  if (!target) return;
  target.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/** Cierra el menú de navegación móvil si está abierto. */
function closeNav() {
  const nav = document.getElementById(NAV_ID);
  if (nav) {
    nav.classList.remove(NAV_OPEN_CLASS);
  }
}

/**
 * Cablea la navegación de secciones y el menú móvil.
 *
 * @returns {() => void} Función de teardown que remueve los listeners.
 */
export function initSections() {
  const navLinks = document.querySelectorAll('[data-nav-link]');
  const toggle = document.querySelector('[data-nav-toggle]');

  const onLinkClick = (event) => {
    const href = event.currentTarget.getAttribute('href') || '';
    if (href.startsWith('#')) {
      event.preventDefault();
      scrollToHash(href);
      closeNav();
    }
  };

  const onToggle = (event) => {
    event.preventDefault();
    const nav = document.getElementById(NAV_ID);
    if (nav) {
      nav.classList.toggle(NAV_OPEN_CLASS);
    }
  };

  navLinks.forEach((link) => link.addEventListener('click', onLinkClick));
  if (toggle) {
    toggle.addEventListener('click', onToggle);
  }

  return function teardown() {
    navLinks.forEach((link) => link.removeEventListener('click', onLinkClick));
    if (toggle) {
      toggle.removeEventListener('click', onToggle);
    }
  };
}
