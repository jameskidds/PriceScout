@echo off
echo =========================================
echo   Price Scout - Build .exe
echo =========================================
echo.

REM Verifier que PyInstaller est installe
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo Installation de PyInstaller...
    pip install pyinstaller
)

echo Lancement du build...
echo.

cd /d "%~dp0"
python -m PyInstaller PriceScout.spec --clean

echo.
if exist "dist\PriceScout.exe" (
    echo =========================================
    echo   BUILD REUSSI !
    echo   Fichier : dist\PriceScout.exe
    echo =========================================
    echo.
    echo Contenu du dossier dist\ :
    dir dist\PriceScout.exe
) else (
    echo ERREUR : le fichier n'a pas ete cree.
    echo Relis les erreurs ci-dessus.
)

echo.
pause
