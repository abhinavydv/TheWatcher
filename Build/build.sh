python setup.py
# pyinstaller --onefile main.py
# cp dist/main ../Files/target

cd ..
zip Target.zip -r ./Target
mv Target.zip ./Files
cd Build

scp -r ../Files abhinav@20.204.81.140:TheWatcher/
scp -r ../Server abhinav@20.204.81.140:TheWatcher/
