import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import './styles.css'

// Element Plus 组件与样式的按需引入由 vite 插件（unplugin-vue-components / auto-import）完成
const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')