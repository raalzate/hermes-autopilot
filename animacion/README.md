# animacion/

La animación «Una tarea, de punta a punta», hecha con [Motion Canvas](https://motioncanvas.io/). De acá sale
el video del [README](../README.md) (`docs/media/tarea-de-punta-a-punta.mp4` y su GIF). No es parte del
arnés, que sigue sin dependencias: Node solo hace falta para editar la animación.

```bash
cd animacion && pnpm install
pnpm start        # el editor de Motion Canvas: ver, ajustar y renderizar la escena
```

La escena es `src/scenes/flujo.tsx`. Sus pasos son los de la consola interactiva de la portada
(`docs/index.html`, constante `PASOS`): si cambia uno, cambiá el otro.
