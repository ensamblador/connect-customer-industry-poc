// Comportamiento del modal de inicio de sesión de "Latam Telco".
//
// Contrato de marcado (lo provee index.html — tarea 4.1):
//   - El modal raíz tiene id="login-modal" y atributo hidden cuando está cerrado.
//   - Un overlay/elementos con [data-login-close] cierran el modal al hacer clic.
//   - Botones con [data-login-open] abren el modal.
//   - El input de email tiene id="login-email".
//   - El contenedor de error tiene id="login-error".
//
// Estas funciones son puras respecto del DOM (no conocen auth ni el widget);
// main.js (tarea 5.2) las cablea con la lógica de sesión.

const MODAL_ID = 'login-modal';
const OPEN_CLASS = 'is-open';
const EMAIL_INPUT_ID = 'login-email';
const ERROR_ID = 'login-error';

/** Devuelve el elemento del modal o null si aún no está en el DOM. */
function getModal() {
  return document.getElementById(MODAL_ID);
}

/** Abre el modal de login y enfoca el input de email. */
export function openLoginModal() {
  const modal = getModal();
  if (!modal) return;
  modal.hidden = false;
  modal.classList.add(OPEN_CLASS);
  modal.setAttribute('aria-hidden', 'false');
  document.body.classList.add('modal-open');
  const input = document.getElementById(EMAIL_INPUT_ID);
  if (input) {
    input.focus();
  }
}

/** Cierra el modal de login y limpia el mensaje de error. */
export function closeLoginModal() {
  const modal = getModal();
  if (!modal) return;
  modal.hidden = true;
  modal.classList.remove(OPEN_CLASS);
  modal.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('modal-open');
  clearLoginError();
}

/** Muestra un mensaje de error en español dentro del modal. */
export function showLoginError(message) {
  const errorEl = document.getElementById(ERROR_ID);
  if (!errorEl) return;
  errorEl.textContent = message;
  errorEl.hidden = false;
}

/** Limpia el mensaje de error del modal. */
export function clearLoginError() {
  const errorEl = document.getElementById(ERROR_ID);
  if (!errorEl) return;
  errorEl.textContent = '';
  errorEl.hidden = true;
}

/** Devuelve el valor actual del input de email (cadena, sin recortar). */
export function getLoginEmailValue() {
  const input = document.getElementById(EMAIL_INPUT_ID);
  return input ? input.value : '';
}

/** Vacía el input de email del modal. */
export function resetLoginInput() {
  const input = document.getElementById(EMAIL_INPUT_ID);
  if (input) {
    input.value = '';
  }
}

/**
 * Cablea los disparadores de apertura/cierre del modal.
 *
 * Registra:
 *   - clic en [data-login-open] -> openLoginModal()
 *   - clic en [data-login-close] -> closeLoginModal()
 *   - tecla Escape -> closeLoginModal()
 *
 * Es idempotente respecto del DOM: si los elementos no existen, no hace nada.
 * Devuelve una función para remover los listeners registrados.
 */
export function initLoginModal() {
  const openButtons = document.querySelectorAll('[data-login-open]');
  const closeButtons = document.querySelectorAll('[data-login-close]');

  const onOpen = (event) => {
    event.preventDefault();
    openLoginModal();
  };
  const onClose = (event) => {
    event.preventDefault();
    closeLoginModal();
  };
  const onKeydown = (event) => {
    if (event.key === 'Escape') {
      closeLoginModal();
    }
  };

  openButtons.forEach((btn) => btn.addEventListener('click', onOpen));
  closeButtons.forEach((btn) => btn.addEventListener('click', onClose));
  document.addEventListener('keydown', onKeydown);

  return function teardown() {
    openButtons.forEach((btn) => btn.removeEventListener('click', onOpen));
    closeButtons.forEach((btn) => btn.removeEventListener('click', onClose));
    document.removeEventListener('keydown', onKeydown);
  };
}
