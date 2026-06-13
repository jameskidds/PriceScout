@echo off
setlocal

REM Lire la version depuis version.txt
set /p VERSION=<version.txt
set FOLDER=PriceScout_v%VERSION%
set ZIPFILE=PriceScout_v%VERSION%.zip

echo =========================================
echo   Price Scout v%VERSION% - Préparer le ZIP acheteur
echo =========================================
echo.

cd /d "%~dp0"

REM Verifier que le .exe existe
if not exist "dist\PriceScout.exe" (
    echo ERREUR : dist\PriceScout.exe introuvable.
    echo Lance d'abord build.bat !
    pause
    exit /b 1
)

REM Supprimer les anciens zips PriceScout
echo Nettoyage des anciens zips...
del /q "PriceScout_v*.zip" 2>nul

REM Créer le dossier de packaging
if exist "%FOLDER%" rmdir /s /q "%FOLDER%"
mkdir "%FOLDER%"

REM Copier l'exe
copy "dist\PriceScout.exe" "%FOLDER%\"

REM Copier le README acheteur
copy "README_ACHETEUR.txt" "%FOLDER%\README.txt"

REM Créer le ZIP
powershell -Command "Compress-Archive -Path '%FOLDER%\*' -DestinationPath '%ZIPFILE%' -Force"

echo.
if exist "%ZIPFILE%" (
    echo =========================================
    echo   ZIP créé : %ZIPFILE%
    echo   Version  : v%VERSION%
    echo   C'est CE fichier que tu envoies a l'acheteur.
    echo =========================================
) else (
    echo Erreur lors de la creation du ZIP.
)

echo.
pause
