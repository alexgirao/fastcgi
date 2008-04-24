#!/bin/sh

m4 -Dpwd=`pwd` proxy.conf.m4 > proxy.conf
m4 -Dpwd=`pwd` fastcgi.conf.m4 > fastcgi.conf
m4 -Dpwd=`pwd` nginx.conf.m4 > nginx.conf
