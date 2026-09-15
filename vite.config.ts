import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
export default defineConfig({plugins:[svelte()],preview:{proxy:{}},server:{proxy:{'/api':'http://127.0.0.1:8000','/book':'http://127.0.0.1:8000','/bridge.js':'http://127.0.0.1:8000','/vendor':'http://127.0.0.1:8000'}}});
