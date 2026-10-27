import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const apiTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Fail instead of silently moving to 5174 while the browser keeps opening 5173
    strictPort: true,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        secure: false,
        autoRewrite: true,
        configure: (proxy) => {
          // Backend down: answer 503 with a readable `detail` (which every page displays)
          // instead of Vite's empty 500. Registered before Vite's own handler, which then skips.
          proxy.on('error', (err, _req, res) => {
            const out = res as any; // http.ServerResponse for normal requests, a Socket for websocket upgrades
            if (typeof out.writeHead !== 'function' || out.headersSent || out.writableEnded) return;
            out.writeHead(503, { 'Content-Type': 'application/json' });
            out.end(JSON.stringify({
              code: 'BACKEND_UNREACHABLE',
              detail: `The FIR VisionAI backend at ${apiTarget} is not reachable (${(err as any).code || err.message}). ` +
                'Start it with start_all.bat, or run diagnose.ps1 to see what is wrong.',
            }));
          });
        }
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
