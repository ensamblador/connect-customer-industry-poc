// main.js: bootstrap de AeroLatam.
//
// Tras el login, actualiza window._connectContactAttrs.email con el email
// del usuario y lo reenvía al widget de Connect. Si no hay cliente con
// sesión, el email se omite por completo del atributo de contacto (el chat
// se inicia sin el atributo email).

import { setActiveEmail, clearActiveEmail, getActiveEmail, getContactAttributes } from './auth.js';
import { initLoginModal, closeLoginModal, showLoginError, clearLoginError, getLoginEmailValue, resetLoginInput } from './ui/modal.js';
import { renderSessionState, initSessionControls } from './ui/header.js';

/** Reenvía los atributos de contacto actuales al widget de Connect. */
function pushContactAttributes() {
  if (typeof window.amazon_connect === 'function') {
    // Omite el email cuando no hay sesión (objeto vacío).
    window.amazon_connect('contactAttributes', getContactAttributes());
  }
}

/** Actualiza el header y el email en los contactAttributes del widget. */
function onSessionChange() {
  const email = getActiveEmail();
  renderSessionState(email);
  // Mutación directa del objeto — el widget lo lee al abrir el chat.
  if (window._connectContactAttrs) {
    if (email) {
      window._connectContactAttrs.email = email;
    } else {
      delete window._connectContactAttrs.email;
    }
  }
  pushContactAttributes();
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
    if (window._connectContactAttrs) {
      window._connectContactAttrs.email = email;
    }
    pushContactAttributes();
    renderSessionState(email);
  } else {
    showLoginError(result.error);
  }
}

/** Maneja el cierre de sesión. */
function handleLogout() {
  try { sessionStorage.removeItem('airline_email'); } catch { /* noop */ }
  // Sin sesión: se omite el email del atributo de contacto.
  clearActiveEmail();
  if (window._connectContactAttrs) {
    delete window._connectContactAttrs.email;
  }
  pushContactAttributes();
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
