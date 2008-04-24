#!/bin/sh

set -e
set -u

umask 022

die(){
    echo $2
    exit $1
}

[ -d logs ] || mkdir logs
[ -f nginx.conf ] || ./update-conf.sh
/usr/local/nginx/sbin/nginx -t -c nginx.conf || die 1 "configuration error"

/usr/local/nginx/sbin/nginx -c nginx.conf
