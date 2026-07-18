// Punto único de re-exportación de los módulos de UI de "AeroLatam".
// main.js importa desde aquí para cablear el comportamiento.

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
