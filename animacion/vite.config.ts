import {defineConfig} from 'vite';
import mcPlugin from '@motion-canvas/vite-plugin';

// el plugin es CJS: bajo "type": "module" el import por defecto es el espacio de nombres del módulo
const motionCanvas = ((mcPlugin as any).default ?? mcPlugin) as typeof mcPlugin;

export default defineConfig({
  plugins: [motionCanvas({project: './src/project.ts'})],
  build: {outDir: 'dist'},
});
