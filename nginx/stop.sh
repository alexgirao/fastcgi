#!/bin/sh

if [ -f logs/nginx.pid ]; then
    kill `cat logs/nginx.pid`
else
    echo seems not to be running
fi
