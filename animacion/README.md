# animacion/

La animación de la portada ("Una tarea, de punta a punta"), hecha con [Motion Canvas](https://motioncanvas.io/).
No es parte del arnés: el arnés sigue sin dependencias. Esto se compila y **el resultado se commitea** en
`docs/animacion/` (lo que sirve GitHub Pages).

```bash
cd animacion && pnpm install
pnpm start        # el editor de Motion Canvas, para ver y ajustar la escena
pnpm build        # compila y copia project.js + player.js a ../docs/animacion/
```

La escena es `src/scenes/flujo.tsx`; sus pasos son los mismos que los de la consola de la portada
(`docs/index.html`, constante `PASOS`): si cambia uno, cambiá el otro.
