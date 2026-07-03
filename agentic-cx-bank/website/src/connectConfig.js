// connectConfig: configuración estática del sitio Latam Banco.
//
// El widget de Amazon Connect se inicializa directamente en index.html con
// valores hardcodeados. Este módulo expone el email de ejemplo usado como
// marcador de posición en la configuración estática del widget. Los atributos
// de contacto reales omiten el email cuando no hay un cliente con sesión.

export const connectConfig = {
  defaultEmail: 'example@example.com',
};
