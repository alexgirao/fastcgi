#!/bin/sh

for i in `seq 1 100`; do
    curl http://localhost:8020/
    sleep 0.5
done
