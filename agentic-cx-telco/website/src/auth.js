// auth.js: login por correo electrónico del lado del cliente.
//
// Captura y valida el email del visitante, lo registra como usuario activo y
// lo expone como Atributo_de_Contacto (`window._connectContactAttrs.email`)
// para que el Widget de Amazon Connect lo reciba al iniciar un chat. No hay
// autenticación real: el único efecto funcional es alimentar los atributos de
// contacto del widget (ver requisitos 2.1–2.4).
//
// Las funciones son puras o de estado mínimo para poder probarlas de forma
// aislada con estado inyectado vía `setActiveEmail`.

import { connectConfig } from './connectConfig.js';

// Clave de persistencia ligera en sessionStorage (sobrevive recargas de la
// pestaña, no entre pestañas/sesiones).
const STORAGE_KEY = 'telco_email';

// Mensaje de error en español para envíos con formato inválido (R2.3).
const INVALID_EMAIL_ERROR = 'Ingresa un correo electrónico válido';

// Regex pragmática de email: una o más caracteres sin espacios ni `@`, una
// `@`, dominio sin espacios ni `@`, un punto y un TLD sin espacios ni `@`.
// Rechaza cadena vacía y cadenas de solo espacios por el anclado y `\S`.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Estado de sesión en memoria (única fuente de verdad en runtime).
let activeEmail = null;

/**
 * Resuelve el objeto global donde viven los Atributos_de_Contacto. Usa
 * `window` en el navegador y degrada a `globalThis` en otros entornos (p. ej.
 * pruebas en Node), de modo que el módulo nunca lance por `window` ausente.
 *
 * @returns {typeof globalThis}
 */
function getGlobal() {
  if (typeof window !== 'undefined') return window;
  return globalThis;
}

/**
 * Devuelve el `sessionStorage` disponible o `null` si no existe o lanza al
 * accederse (modo privado, entornos sin DOM). Permite degradar a estado en
 * memoria sin romper.
 *
 * @returns {Storage | null}
 */
function getSessionStorage() {
  try {
    const g = getGlobal();
    return g && g.sessionStorage ? g.sessionStorage : null;
  } catch {
    return null;
  }
}

/**
 * Valida el formato de un email con una regex pragmática.
 * Rechaza `null`/`undefined`, valores no string, cadena vacía y cadenas
 * compuestas solo por espacios en blanco.
 *
 * @param {unknown} value
 * @returns {boolean}
 */
export function isValidEmail(value) {
  if (typeof value !== 'string') return false;
  return EMAIL_RE.test(value);
}

/**
 * Registra un email como usuario activo si su formato es válido.
 * - Válido: guarda `activeEmail`, persiste en `sessionStorage` (clave
 *   `telco_email`, degradando a memoria si no está disponible), actualiza
 *   `window._connectContactAttrs.email` y devuelve `{ ok: true }`.
 * - Inválido: no modifica el estado y devuelve
 *   `{ ok: false, error: 'Ingresa un correo electrónico válido' }`.
 *
 * @param {unknown} value
 * @returns {{ ok: true } | { ok: false, error: string }}
 */
export function setActiveEmail(value) {
  if (!isValidEmail(value)) {
    return { ok: false, error: INVALID_EMAIL_ERROR };
  }

  activeEmail = value;

  const storage = getSessionStorage();
  if (storage) {
    try {
      storage.setItem(STORAGE_KEY, value);
    } catch {
      // sessionStorage no disponible/escribible: degradar a estado en memoria.
    }
  }

  const g = getGlobal();
  const attrs = g._connectContactAttrs ?? {};
  attrs.email = value;
  g._connectContactAttrs = attrs;

  return { ok: true };
}

/**
 * Devuelve el email del usuario activo o `null` si no hay sesión.
 *
 * @returns {string | null}
 */
export function getActiveEmail() {
  return activeEmail;
}

/**
 * Devuelve los Atributos_de_Contacto enviados al Widget de Connect. Incluye
 * el email del usuario activo o, sin sesión, el `defaultEmail` de la config.
 *
 * @returns {{ email: string }}
 */
export function getContactAttributes() {
  return { email: activeEmail ?? connectConfig.defaultEmail };
}

// Restaura el email activo desde sessionStorage al cargar el módulo, para
// sobrevivir recargas dentro de la pestaña. Solo restaura valores válidos.
(function restoreFromSession() {
  const storage = getSessionStorage();
  if (!storage) return;
  try {
    const stored = storage.getItem(STORAGE_KEY);
    if (isValidEmail(stored)) {
      activeEmail = stored;
    }
  } catch {
    // Ignorar: degradar a estado en memoria sin sesión previa.
  }
})();
