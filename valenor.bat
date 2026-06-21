@echo off
rem VALENOR - bootstrap para Windows. / Windows bootstrap.
rem Cria/usa um virtualenv (.venv), instala o VALEN e abre.
rem   valenor.bat                  abre o chat / open chat
rem   valenor.bat "um app ..."     execucao unica / one-shot
rem   valenor.bat skills where     qualquer subcomando / any subcommand
setlocal
cd /d "%~dp0"

echo VALENOR . Windows

rem --- 1) Escolhe o Python / pick python ---
where python >nul 2>nul
if %errorlevel%==0 (
  set "PY=python"
) else (
  where py >nul 2>nul
  if %errorlevel%==0 (
    set "PY=py"
  ) else (
    echo Python nao encontrado. / Python not found. Instale de https://python.org
    exit /b 1
  )
)

rem --- 2) Cria/usa o virtualenv / create-or-reuse venv ---
if not exist ".venv\Scripts\activate.bat" (
  echo Criando ambiente virtual / creating venv ^(.venv^)...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Falha ao criar o venv. / Failed to create venv.
    exit /b 1
  )
)
call ".venv\Scripts\activate.bat"

rem --- 3) Instala o VALEN se necessario / install if missing ---
python -m pip show valenor >nul 2>nul
if errorlevel 1 (
  echo Instalando dependencias / installing dependencies...
  python -m pip install --quiet --upgrade pip
  python -m pip install --quiet -e "%~dp0"
)

rem --- 4) Abre o VALENOR / launch ---
valenor %*
endlocal
