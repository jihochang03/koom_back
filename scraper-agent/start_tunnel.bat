@echo off
title [Watchdog] SSH Tunnel
cd /d "%~dp0"

:: PEM 키 위치 — 이 파일과 같은 폴더에 dkcrawl.pem 두기
set "PEM=%~dp0dkcrawl.pem"

if not exist "%PEM%" (
    echo [ERROR] PEM 파일 없음: %PEM%
    echo dkcrawl.pem 을 이 폴더에 복사하세요.
    pause
    exit /b 1
)

icacls "%PEM%" /inheritance:r /grant:r "%USERNAME%:(R)" >nul 2>&1

if not exist "logs" mkdir logs
set "LOG=logs\tunnel.log"

:restart
echo [%date% %time%] 포트 정리 중...
ssh -i "%PEM%" -o ConnectTimeout=10 -o StrictHostKeyChecking=no ^
    ec2-user@51.21.130.214 "pid=$(sudo ss -Htlnp sport = :3001 2>/dev/null | grep -oP 'pid=\K[0-9]+' | head -1); [ -n \"$pid\" ] && sudo kill -9 $pid; true"

echo [%date% %time%] 터널 시작 (local:3000 -> EC2:3001) >> "%LOG%"
echo [%date% %time%] 터널 시작 중...
ssh -i "%PEM%" ^
    -o ServerAliveInterval=30 ^
    -o ServerAliveCountMax=3 ^
    -o TCPKeepAlive=yes ^
    -o ExitOnForwardFailure=yes ^
    -o ConnectTimeout=10 ^
    -o StrictHostKeyChecking=no ^
    -R 3001:127.0.0.1:3000 ^
    -N ^
    ec2-user@51.21.130.214 >> "%LOG%" 2>&1

echo [%date% %time%] 터널 끊김. 60초 후 재시작...
timeout /t 60 /nobreak
goto restart
