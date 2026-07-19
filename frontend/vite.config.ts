import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    // jsdom 環境でブラウザ API をエミュレート
    environment: 'jsdom',
    // @testing-library/jest-dom のカスタムマッチャを自動読み込み
    setupFiles: ['./tests/setup.ts'],
    globals: true,
  },
})
