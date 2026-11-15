import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  build: {
    rolldownOptions: {
      output: {
        // Long-lived vendor chunks: the WebGL map stack and the chart library cache separately from app code.
        codeSplitting: {
          groups: [
            { name: 'map', test: /node_modules[\\/](@deck\.gl|@luma\.gl|@loaders\.gl|@math\.gl|@probe\.gl|maplibre-gl|react-map-gl|@vis\.gl|earcut|@mapbox)/ },
            { name: 'charts', test: /node_modules[\\/](recharts|d3-|victory-vendor|lodash)/ },
            { name: 'react', test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/ },
          ],
        },
      },
    },
    // deck.gl + MapLibre are a single WebGL map stack of ~2 MB minified (~550 kB gzipped); it cannot be split
    // further without breaking its internal module graph, so the warning threshold sits just above it.
    chunkSizeWarningLimit: 2300,
  },
})
