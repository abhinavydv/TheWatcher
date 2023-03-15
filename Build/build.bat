python ./setup.py
pyinstaller --onefile main.py
copy dist\main.exe ..\Files\target.exe
scp -r ../Files abhinav@20.204.81.140:TheWatcher/
scp -r ../Server abhinav@20.204.81.140:TheWatcher/
