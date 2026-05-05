import { defineConfig } from 'vite';

export default defineConfig({
  build: {
    // v0.8.2 KM-a (Spec Ek A.19 #4): maplibre-gl 5.24.0 single-file UMD
    // ESM (`main: dist/maplibre-gl.js`, ~1002 KB minified) tree-shake'i
    // desteklemiyor — tek dosya. App code'umuz toplam ~50 KB (gzip ~22).
    // Tek bundle <600 KB hedef bu paket boyutuyla imkansız.
    // Optimizasyon stratejisi: vendor split + cache benefit.
    //   • App chunk küçük → ilk parse hızlı
    //   • Vendor chunk değişmiyor (maplibre upgrade nadir) → cache hit
    //     2. ziyarette sadece app indirilir (~22 KB gzip)
    //   • HTTP/2 multiplex ile paralel iletim (tek bundle'a göre 3G'de
    //     measurable kazanç — TCP slow-start single-stream darboğazı yok)
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          if (id.includes('node_modules/maplibre-gl')) return 'maplibre';
        },
      },
    },
    // Vendor chunk ~1000 KB, default 500 KB threshold üzerinde — bilinçli
    // tolerans (paket boyutu sabit). 1100 KB üstü gerçek regression olur.
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
