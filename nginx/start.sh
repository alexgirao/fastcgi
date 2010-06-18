#!/bin/sh

set -e
set -u

umask 022

die(){
    echo $2
    exit $1
}

NGINX=/usr/sbin/nginx

[ -d logs ] || mkdir logs
[ -f nginx.conf ] || ./update-conf.sh
[ -e $NGINX ] || die 1 "$NGINX not found"

$NGINX -t -c "`pwd`"/nginx.conf || die 1 "configuration error"
$NGINX -c "`pwd`"/nginx.conf
