import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import {resolve} from 'path';
export function finderBuild(mode) {
  return defineConfig({plugins:[react()],define:{'process.env.NODE_ENV':JSON.stringify('production')},base:`/assets/illumenate_lighting/product_finder/${mode}/`,build:{outDir:`../../illumenate_lighting/public/product_finder/${mode}`,emptyOutDir:true,lib:{entry:resolve(import.meta.dirname,'src/main.jsx'),name:'IllFinderBundle',formats:['iife'],fileName:()=> 'ill-finder.js'},cssCodeSplit:false,rollupOptions:{output:{assetFileNames:'ill-finder.[ext]'}}}});
}
export default finderBuild('public');
