import { defineConfig } from 'vitest/config';

// Configuración de pruebas del sitio "Latam Telco".
//
// El widget de Amazon Connect se configura de forma estática en index.html, por
// lo que `connectConfig` solo expone `defaultEmail` y no hay variables VITE_*
// que validar en runtime. La superficie con lógica testeable es `auth.js`
// (validación de email + atributos de contacto). `passWithNoTests` evita que el
// script falle cuando no hay archivos de prueba presentes.
export default defineConfig({
  test: {
    passWithNoTests: true,
  },
});
