import { defineConfig } from 'vite';

export default defineConfig({
  build: {
    // Split maplibre-gl into its own vendor chunk so the small app
    // bundle parses quickly on first visit and the (~1 MB) vendor
    // chunk can be cached across subsequent visits.
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          if (id.includes('node_modules/maplibre-gl')) return 'maplibre';
        },
      },
    },
    // The vendor chunk exceeds the default 500 KB warning threshold;
    // tolerate up to 1100 KB. Anything beyond that is a real regression.
    chunkSizeWarningLimit: 1100,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8010',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8011',
        ws: true,
        changeOrigin: true,
      },
    },
  },
});
