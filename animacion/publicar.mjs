// Copia el resultado de `vite build` a docs/animacion/ (lo que sirve GitHub Pages) y empaqueta el
// reproductor con sus dependencias: el navegador no resuelve `@motion-canvas/core` por su cuenta.
import {mkdirSync, readdirSync, readFileSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {build} from 'esbuild';

const destino = join('..', 'docs', 'animacion');
mkdirSync(destino, {recursive: true});
const proyecto = readdirSync(join('dist', 'src')).find((f) => /^project.*\.js$/.test(f));
// Scripts clásicos (no módulos): así la portada también funciona abierta como archivo (file://),
// donde el navegador bloquea los módulos ES. El proyecto va como texto y la página lo carga desde un Blob.
const codigo = readFileSync(join('dist', 'src', proyecto), 'utf8');
writeFileSync(join(destino, 'project.js'), 'window.MC_PROYECTO = ' + JSON.stringify(codigo) + ';\n');
await build({
  entryPoints: [join('node_modules', '@motion-canvas', 'player', 'dist', 'main.js')],
  outfile: join(destino, 'player.js'), bundle: true, format: 'iife', minify: true, logLevel: 'error',
});
console.log('docs/animacion/: project.js + player.js');
