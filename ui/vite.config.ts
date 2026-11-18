import {defineConfig} from 'vite';
export default defineConfig({server:{host:'127.0.0.1',port:5187,strictPort:true,proxy:{'/api':{target:'http://127.0.0.1:18787',changeOrigin:false}}},build:{target:'es2022'}});
