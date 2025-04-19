DIR=$HOME/bark-monitor/
cd $DIR
. venv/bin/activate
cd bark_monitor
bark-monitor --config ../bark_chromebook.json 2>&1 | ts
