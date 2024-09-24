export JSON_PATH="$HOME/mnt/bark_chromebook.json"
mnt_point="$HOME/mnt/"
if [ -z "$( ls -A $mnt_point )" ]; then
  sshfs home:/var/www/html $mnt_point
fi
. start.sh
