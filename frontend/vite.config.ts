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
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false
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
          // Heavy viz / graph libraries (ForceGraph etc.) if used in EntityNetwork
          'vendor-graph': ['react-force-graph-2d', 'd3', 'd3-force', 'd3-zoom', 'd3-drag', 'd3-color', 'd3-scale', 'd3-interpolate'],
        }
      }
    }
  }
});
