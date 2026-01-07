import {
    defineConfig
} from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [react()],
    server: {
        host: '0.0.0.0',
        port: 5173,
        proxy: {
            '/api': {
                target: 'https://tereasa-unanaemic-kaydence.ngrok-free.dev/',
                changeOrigin: true,
                secure: false,
                configure: (proxy, _options) => {
                    proxy.on('proxyReq', (proxyReq, req, _res) => {
                        // Add ngrok-skip-browser-warning header to bypass warning page
                        proxyReq.setHeader('ngrok-skip-browser-warning', 'true');
                    });
                },
            }
        }
    }
})