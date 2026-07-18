// Render del estado de sesión en el header de "AeroLatam".
//
// Contrato de marcado (lo provee index.html):
//   - Contenedor de sesión con id="session-area".
//   - Bloque "sin sesión" con [data-session-logged-out] (contiene el botón
//     "Iniciar sesión" con [data-login-open]).
//   - Bloque "con sesión" con [data-session-logged-in], que incluye:
//       * [data-session-email] -> aquí se escribe el email activo.
//       * [data-logout] -> botón "Cerrar sesión".
//
// El render alterna la visibilidad de ambos bloques según haya o no email.
// main.js llama a renderSessionState() tras cada login/logout.

const SESSION_AREA_ID = 'session-area';
const LOGGED_OUT_SELECTOR = '[data-session-logged-out]';
const LOGGED_IN_SELECTOR = '[data-session-logged-in]';
const EMAIL_SELECTOR = '[data-session-email]';

/**
 * Refleja el estado de sesión en el header.
 *
 * @param {string|null} email Email del usuario activo, o null/'' si no hay sesión.
 */
export function renderSessionState(email) {
  const area = document.getElementById(SESSION_AREA_ID);
  if (!area) return;

  const loggedOut = area.querySelector(LOGGED_OUT_SELECTOR);
  const loggedIn = area.querySelector(LOGGED_IN_SELECTOR);
  const emailEl = area.querySelector(EMAIL_SELECTOR);

  const hasSession = typeof email === 'string' && email.trim() !== '';

  if (hasSession && emailEl) {
    emailEl.textContent = email;
  }

  if (loggedOut) {
    loggedOut.hidden = hasSession;
  }
  if (loggedIn) {
    loggedIn.hidden = !hasSession;
  }
}

/**
 * Cablea el botón de cerrar sesión.
 *
 * @param {() => void} onLogout Callback que main.js usa para limpiar la sesión.
 * @returns {() => void} Función de teardown que remueve los listeners.
 */
export function initSessionControls(onLogout) {
  const area = document.getElementById(SESSION_AREA_ID);
  if (!area) return () => {};

  const logoutButtons = area.querySelectorAll('[data-logout]');
  const handler = (event) => {
    event.preventDefault();
    if (typeof onLogout === 'function') {
      onLogout();
    }
  };

  logoutButtons.forEach((btn) => btn.addEventListener('click', handler));

  return function teardown() {
    logoutButtons.forEach((btn) => btn.removeEventListener('click', handler));
  };
}
