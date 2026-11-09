/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  server: {
    proxy: { '/api': process.env.API_URL ?? 'http://localhost:8000' },
  },
  test: { environment: 'jsdom' },
})
