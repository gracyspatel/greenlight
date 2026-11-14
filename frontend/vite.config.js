import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
// /api calls go to the FastAPI server on :8000 during development
export default defineConfig({
  plugins: [react()],
  server: { host: true, proxy: { '/api': 'http://localhost:8000' } },
})
