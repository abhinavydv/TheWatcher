function kill_process {
    while true; do
        a=( `ps aux | grep boot.py` )
        kill -9 ${a[1]}
        if [ $? -ne 0 ]; then
            break
        fi
    done
    while true; do
        a=( `ps aux | grep target_script.sh` )
        kill -9 ${a[1]}
        if [ $? -ne 0 ]; then
            break
        fi
    done
}

kill_process

if [ -d ~/.cache/watcher ]; then
    rm -rf ~/.cache/watcher
fi

if [ -d ~/.local/share/watcher ]; then
    rm -rf ~/.local/share/watcher
fi

if [ -f ~/.config/autostart/watcher.desktop ]; then
    rm ~/.config/autostart/watcher.desktop
fi

crontab -r
