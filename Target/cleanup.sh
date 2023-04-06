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

# function kill_process {

# }
