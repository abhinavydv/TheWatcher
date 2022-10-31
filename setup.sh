rm Server/Base Target/Base Watcher/Base
cp -r Base Server/Base
cp -r Base Target/Base
cp -r Base Watcher/Base

if [[ -n ".watchenv" ]] do
    virtualenv .watchenv
done

source .watchenv/bin/activate
pip install requirements.txt