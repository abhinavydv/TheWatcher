# A wrapper around main.py that sets the LD_LIBRARY_PATH and PYTHONPATH
# environment variables which are required for tkinter

TARGET_DIR=`pwd`
echo $TARGET_DIR
BASE_DIR=`dirname $TARGET_DIR`
PYTHON_VERSION_NUMBER=`python3 -c "import sys; \
    print(f'{sys.version_info.major}.{sys.version_info.minor}')"`
echo $PYTHON_VERSION_NUMBER
VIRTUALENV="$BASE_DIR/.watchenv$PYTHON_VERSION_NUMBER"
ACTIVATE_FILE="$VIRTUALENV/bin/activate"
echo $VIRTUALENV
export LD_LIBRARY_PATH="$LD_LIBRARY_PATH:$VIRTUALENV/lib:$VIRTUALENV/lib/x86_64-linux-gnu"
echo $LD_LIBRARY_PATH
export PYTHONPATH="$PYTHONPATH:$VIRTUALENV/lib/python$PYTHON_VERSION_NUMBER/lib-dynload"
export PYTHONPATH="$PYTHONPATH:$VIRTUALENV/lib/python$PYTHON_VERSION_NUMBER"
echo "$PYTHONPATH"
python3 depsman.py
source "$ACTIVATE_FILE"
# while true; do
    python3 main.py
    # sleep 10
# done
