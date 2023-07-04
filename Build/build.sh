# python setup.py
# pyinstaller --onefile main.py
# cp dist/main ../Files/target

cd ..
python update_base.py
zip Target.zip -r ./Target
mv Target.zip ./Files
openssl sha256 ./Files/Target.zip > ./Files/Target.zip.sha256
cp target_bootstrap.sh ./Files
cp target_script.sh ./Files
cd Build

scp -r ../Files abhinavyadavdev@34.93.156.166:TheWatcher/
scp -r ../Server abhinavyadavdev@34.93.156.166:TheWatcher/
