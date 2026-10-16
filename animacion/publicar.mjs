// Copia el resultado de `vite build` a docs/animacion/ (lo que sirve GitHub Pages) y empaqueta el
// reproductor con sus dependencias: el navegador no resuelve `@motion-canvas/core` por su cuenta.
import {copyFileSync, mkdirSync, readdirSync} from 'node:fs';
import {join} from 'node:path';
import {build} from 'esbuild';

const destino = join('..', 'docs', 'animacion');
mkdirSync(destino, {recursive: true});
const proyecto = readdirSync(join('dist', 'src')).find((f) => /^project.*\.js$/.test(f));
copyFileSync(join('dist', 'src', proyecto), join(destino, 'project.js'));
await build({
  entryPoints: [join('node_modules', '@motion-canvas', 'player', 'dist', 'main.js')],
  outfile: join(destino, 'player.js'), bundle: true, format: 'esm', minify: true, logLevel: 'error',
});
console.log('docs/animacion/: project.js + player.js');
