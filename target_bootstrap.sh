#!/bin/bash
if [ -f target_script.sh ]; then 
    rm target_script.sh
fi
wget http://127.0.0.1:8080/target_script.sh
# bash target_script.sh
setsid bash target_script.sh >/dev/null 2>&1 < /dev/null &
