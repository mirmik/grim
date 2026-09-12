import { defineConfig } from '@playwright/test';
export default defineConfig({testDir:'tests/ui',workers:1,timeout:30000,use:{baseURL:'http://127.0.0.1:8001',viewport:{width:1440,height:1000}},webServer:{command:'python3 scripts/serve_test_book.py',url:'http://127.0.0.1:8001/api/library',reuseExistingServer:false,timeout:20000}});
