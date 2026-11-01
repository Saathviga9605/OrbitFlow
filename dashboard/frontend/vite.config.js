import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Relative base: the build runs from any static host, or from FastAPI at /
export default defineConfig({ plugins: [react()], base: './', build: { chunkSizeWarningLimit: 900 },
  preview: { proxy: { '/api': 'http://localhost:8000' } }, server: { proxy: { '/api': 'http://localhost:8000' } } });
