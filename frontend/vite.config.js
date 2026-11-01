import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

// 开发期代理：/api/flowai/** -> flowai-api /api/v1/**；/api/industrial/** -> industrial-api /api/v1/**
// 生产由 nginx 做同源反向代理（docs/01 §2、ADR-013 §4）
export default defineConfig({
  plugins: [
    vue(),
    // Element Plus 按需引入，避免整包进入首屏 bundle
    AutoImport({ resolvers: [ElementPlusResolver()], dts: false }),
    Components({ resolvers: [ElementPlusResolver()], dts: false })
  ],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api/flowai': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        rewrite: (path) => '/api/v1' + path.replace(/^\/api\/flowai/, '')
      },
      '/api/industrial': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
        rewrite: (path) => '/api/v1' + path.replace(/^\/api\/industrial/, '')
      }
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: false
  }
})