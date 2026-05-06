@echo off
echo Competition Analyzer Frontend starting...
cd /d "%~dp0"
if not exist node_modules (
    echo Installing dependencies...
    npm install
)
npm run dev
