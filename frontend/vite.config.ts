/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  test: {
    // jsdom 環境でブラウザ API をエミュレート
    environment: 'jsdom',
    // @testing-library/jest-dom のカスタムマッチャを自動読み込み
    setupFiles: ['./tests/setup.ts'],
    globals: true,
  },
})
