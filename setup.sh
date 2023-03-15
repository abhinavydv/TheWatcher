rm -r Server/Base Target/Base Watcher/Base
cp -r Base Server/Base
cp -r Base Target/Base
cp -r Base Watcher/Base

# if [[ -n ".watchenv" ]] do
#     virtualenv .watchenv
# done

# source .watchenv3.10/bin/activate
# pip install -r requirements.txt