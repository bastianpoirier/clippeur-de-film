@echo off
rem Double-cliquer sur ce fichier ouvre l'interface du Clippeur de film dans le navigateur.
cd /d "%~dp0"
.venv\Scripts\python.exe -m clippeur interface
pause
