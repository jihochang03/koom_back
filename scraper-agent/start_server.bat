@echo off
title [Watchdog] Scraper Agent
cd /d "%~dp0"

if not exist "logs" mkdir logs
set "LOG=logs\server.log"

:restart
echo [%date% %time%] 서버 시작 중...

if not exist "web\dist\index.html" (
    echo [%date% %time%] 프론트엔드 빌드 중...
    cd web
    call npm install
    call npm run build
    cd ..
)

if not exist "node_modules" (
    echo [%date% %time%] npm install 중...
    call npm install
)

echo [%date% %time%] npm run web 시작 >> "%LOG%"
call npm run web >> "%LOG%" 2>&1

echo [%date% %time%] 서버 종료 (exit %ERRORLEVEL%). 10초 후 재시작...
timeout /t 10 /nobreak
goto restart
