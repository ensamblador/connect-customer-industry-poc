// Punto único de re-exportación de los módulos de UI de "Latam Telco".
// main.js (tarea 5.2) importa desde aquí para cablear el comportamiento.

export {
  openLoginModal,
  closeLoginModal,
  showLoginError,
  clearLoginError,
  getLoginEmailValue,
  resetLoginInput,
  initLoginModal,
} from './modal.js';

export {
  renderSessionState,
  initSessionControls,
} from './header.js';

export { initSections } from './sections.js';
