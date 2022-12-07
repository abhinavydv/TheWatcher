# setup the server for file downloads
if [ ! -d /srv/fileShare ]
then
    sudo mkdir -p /srv/fileShare && sudo chmod -R 1777 /srv/fileShare
fi
cd /srv/fileShare && python3 -m http.server 8080