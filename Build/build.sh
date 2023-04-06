# python setup.py
# pyinstaller --onefile main.py
# cp dist/main ../Files/target

cd ..
zip Target.zip -r ./Target
mv Target.zip ./Files
openssl sha256 ./Files/Target.zip > ./Files/Target.zip.sha256
cp target_bootstrap.sh ./Files
cp target_script.sh ./Files
python update_base.py
cd Build

scp -r ../Files abhinav@watcher.centralindia.cloudapp.azure.com:TheWatcher/
scp -r ../Server abhinav@watcher.centralindia.cloudapp.azure.com:TheWatcher/
