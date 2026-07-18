@echo off

echo Starting Flask Server...
start cmd /k "python app.py"

timeout /t 3 > nul

echo Starting Cloudflare Tunnel...
start cmd /k "C:\cloudflared\cloudflared.exe tunnel --url http://localhost:5000"

echo Done!
pause