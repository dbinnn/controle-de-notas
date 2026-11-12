@echo off
setlocal
cd /d "%~dp0"
title Controle de Notas - iniciando...

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERRO] Python nao foi encontrado no seu computador.
    echo Instale em https://www.python.org/downloads/
    echo e marque a opcao "Add Python to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

echo Verificando dependencias ^(so demora na primeira vez^)...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao instalar as dependencias. Verifique sua conexao com a internet.
    echo.
    pause
    exit /b 1
)

echo.
echo Iniciando o Controle de Notas em uma nova janela...
start "Controle de Notas (nao feche esta janela)" cmd /k python run_waitress.py

timeout /t 3 /nobreak >nul
start "" http://localhost:5000

echo.
echo Pronto! O site abriu no seu navegador.
echo Pra desligar o Controle de Notas, feche a janela "Controle de Notas".
echo.
pause
