import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],

  // Base path for asset URLs - FastAPI serves static at /static/
  base: '/static/',

  // Output to multirig/static for FastAPI serving
  build: {
    outDir: path.resolve(__dirname, '../static'),
    emptyOutDir: false, // Don't delete rig_models.json
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
      },
    },
  },

  // Development server proxies API to FastAPI
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
      '/static/rig_models.json': 'http://localhost:8000',
    },
  },

  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});
