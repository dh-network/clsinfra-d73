#!/bin/bash
/usr/local/bin/dockerd-entrypoint.sh &
jupyter lab --ip=* --allow-root --port=8889 --no-browser --notebook-dir=/home/d73/report --NotebookApp.token=''
