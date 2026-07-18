import { defineConfig } from 'vite'

// Configuracion Vite vanilla para el sitio "AeroLatam".
// Sin plugins de React ni Tailwind. La salida del build va a dist/.
export default defineConfig({
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
