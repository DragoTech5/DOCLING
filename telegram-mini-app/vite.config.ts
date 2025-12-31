import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // Base path for production - served at /twa/ from backend
  base: '/twa/',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    host: true,
    allowedHosts: ['localhost', '.trycloudflare.com'],
    // Proxy API requests to backend during development
    proxy: {
      '/api': {
        target: 'http://localhost:8200',
        changeOrigin: true,
        ws: true,
        rewrite: (path) => path,
        configure: (proxy, options) => {
          // Pass through all headers including Telegram init data
          proxy.on('proxyRes', (proxyRes, req, res) => {
            // Ensure CORS headers are passed through
            proxyRes.headers['Access-Control-Allow-Origin'] = '*'
          })
        },
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    minify: 'esbuild',
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
        },
      },
    },
  },
})
