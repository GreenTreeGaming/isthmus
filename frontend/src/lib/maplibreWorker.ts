// maplibre-gl v6 finds its worker relative to its own module URL, which breaks once Vite
// bundles it (dev pre-bundle and prod build). Point it at an explicitly emitted copy instead.
import { setWorkerUrl } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'

setWorkerUrl(workerUrl)
