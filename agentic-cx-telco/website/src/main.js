// main.js: bootstrap de Latam Telco.
//
// Tras el login, actualiza window._connectContactAttrs.email con el email
// del usuario. El widget de Connect lee esa propiedad cuando el usuario
// abre el chat — igual que en el proyecto React de referencia.

import { setActiveEmail, getActiveEmail } from './auth.js';
import { initLoginModal, closeLoginModal, showLoginError, clearLoginError, getLoginEmailValue, resetLoginInput } from './ui/modal.js';
import { renderSessionState, initSessionControls } from './ui/header.js';

/** Actualiza el header y el email en los contactAttributes del widget. */
function onSessionChange() {
  const email = getActiveEmail();
  renderSessionState(email);
  // Mutación directa del objeto — el widget lo lee al abrir el chat.
  if (window._connectContactAttrs) {
    window._connectContactAttrs.email = email || 'example@example.com';
  }
}

/** Maneja el envío del formulario de login. */
function handleLoginSubmit(event) {
  event.preventDefault();
  clearLoginError();

  const email = getLoginEmailValue().trim();
  const result = setActiveEmail(email);

  if (result.ok) {
    resetLoginInput();
    closeLoginModal();
    // Actualizar email en el objeto global que el widget lee.
    window._connectContactAttrs.email = email;
    renderSessionState(email);
  } else {
    showLoginError(result.error);
  }
}

/** Maneja el cierre de sesión. */
function handleLogout() {
  try { sessionStorage.removeItem('telco_email'); } catch { /* noop */ }
  window._connectContactAttrs.email = 'example@example.com';
  renderSessionState(null);
}

// Inicialización al cargar el DOM.
document.addEventListener('DOMContentLoaded', () => {
  // Restaurar estado de sesión desde sessionStorage y sincronizar widget.
  onSessionChange();

  // Cablear modal (botones open/close, tecla Escape).
  initLoginModal();

  // Cablear formulario de login.
  const form = document.getElementById('login-form');
  if (form) form.addEventListener('submit', handleLoginSubmit);

  // Cablear botón de cerrar sesión.
  initSessionControls(handleLogout);
});
