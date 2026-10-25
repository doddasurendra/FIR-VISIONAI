import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: false,
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
        autoRewrite: true
      }
    }
  },
  build: {
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks: {
          // Core React runtime in its own chunk
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          // Lucide icons split into separate vendor chunk
          'vendor-lucide': ['lucide-react'],
          // Heavy viz / graph libraries if used in EntityNetwork
          'vendor-graph': ['vis-network'],
        }
      }
    }
  }
});
