@echo off

:: 1. Verifica se a pasta .venv já existe
if not exist ".venv" (
    echo Criando o ambiente virtual .venv...
    py -m venv .venv
    if errorlevel 1 (
        echo Erro ao criar o ambiente virtual. Verifique se o Python esta instalado no PATH.
        pause
        exit /b 1
    )
)

:: 2. Ativa o ambiente virtual
call .venv\Scripts\activate.bat

if defined VIRTUAL_ENV (
    echo Ambiente virtual ativado com sucesso!
) else (
    echo Falha ao ativar o ambiente virtual.
    pause
    exit /b 1
)

:: 3. Verifica se existe o arquivo requirements.txt e instala as dependencias
if exist "requirements.txt" (
    echo Verificando e instalando dependencias do requirements.txt...
    python -m pip install --upgrade pip
    pip install -r requirements.txt
) else (
    echo Arquivo requirements.txt nao encontrado. Pulando instalacao de dependencias.
)

