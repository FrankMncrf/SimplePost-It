# Novedades

## 1.2.5 — 2026-10-31

- Editor: el título va en su propio campo, separado del cuerpo de la nota (en Simplenote sigue siendo la primera línea).
- Editor: casilla «Privada» junto a Markdown, también al editar una nota existente.
- Editor: botón «☐ Lista de tareas» que convierte las líneas seleccionadas en tareas de Simplenote (o las vuelve texto normal).

## 1.2.4 — 2026-10-30

- Inicio de sesión con un código enviado a tu correo (como en la app de Simplenote). El inicio con contraseña depende de un servidor de Simplenote que a veces no responde.
- macOS: las notas se pueden mover y abrir (antes Finder se quedaba los clics y el doble clic mostraba el escritorio).
- macOS: sin la línea negra alrededor de las notas.
- macOS: Ajustes y el editor reciben el teclado al abrirse.

## 1.2.3 — 2026-10-30

- Se puede usar sin instalar Simplenote: inicia sesión con tu cuenta en Ajustes → Cuenta. La app de Simplenote sigue siendo lo recomendado.
- Windows: compatible con Simplenote de Microsoft Store (lee su sesión y lo abre).
- Windows: también busca Simplenote en Program Files (x86).

## 1.2.2 — 2026-10-30

- macOS: arreglado el inicio de sesión y la conexión con Simplenote (la app no encontraba los certificados HTTPS del sistema).
- macOS: con Simplenote de la Mac App Store, la sesión se lee del Llavero (macOS pide permiso la primera vez: elige «Permitir siempre»).
- Si no se puede conectar al iniciar sesión, se muestra el motivo.

## 1.2.1 — 2026-10-28

- Instalación con una línea también en Linux: instala el paquete de tu distribución (Arch, Debian/Ubuntu, Fedora, openSUSE) o, si no hay, desde el código en ~/.local.
- El paquete .rpm ya se instala en openSUSE (PyQt6 se llama python3-PyQt6 ahí).

## 1.2.0 — 2026-10-28

- Si cierras la ventana de Simplenote, vuelve a abrirse oculto en segundo plano (con «Mantener Simplenote abierto en segundo plano»), sin modificar Simplenote.
- Instalación con una línea en macOS y Windows, sin el bloqueo de Gatekeeper/SmartScreen para apps sin firma de pago.
- Versión para Mac con procesador Intel.

## 1.1.0 — 2026-10-28

- El tablero se puede colocar en cualquier parte: con Ajustes abierto, arrastra un espacio vacío del tablero para moverlo (también a otro monitor).
- Nueva opción «Esquina de referencia»: la posición se mide desde cualquier esquina del monitor.
- Al conectar o quitar un monitor (p. ej. un dock), cambiar el principal o la resolución, el tablero se recoloca solo.

## 1.0.2 — 2026-10-28

- Linux: al iniciar sesión, Simplenote vuelve a arrancar con la ventana oculta (se buscaba una ventana interna de Electron en vez de la principal).
- Linux: cerrar Simplenote mientras SimplePost-It corre ya no puede cerrar SimplePost-It ni dejar procesos zombi.

## 1.0.1 — 2026-10-28

- Clic derecho → «Mover a la papelera» manda la nota entera a la papelera de Simplenote (con confirmación).
- Linux: las notas ya no quedan detrás de conky u otros widgets de escritorio que arrancan después.

## 1.0.0 — 2026-10-27

Primera versión pública, para Linux, Windows y macOS.

- Notas fijadas de Simplenote como post-its en el escritorio: cinta, esquina doblada, inclinación y colores.
- Arrastrar y soltar en un tablero, ordenar en cuadrícula, notas nuevas en un hueco libre.
- Marcar tareas con un clic, contador de tareas en la cinta, enlaces con Ctrl+clic, etiquetas al pie.
- Markdown en las notas que lo tienen activado en Simplenote.
- Mini editor: crear, editar y mandar a la papelera sin abrir Simplenote.
- Notas privadas (texto borroso), minimizadas y con color elegido.
- Usa la sesión de la app de escritorio de Simplenote, o un inicio de sesión propio.
- Mantiene Simplenote abierto en segundo plano con la ventana oculta y la muestra desde la bandeja.
- Ajustes: inicio con la sesión, idioma, atajo global, tamaño y posición del tablero, opacidad, tamaño de las notas, fuente.
- Español e inglés.
