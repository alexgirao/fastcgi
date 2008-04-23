#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import stat
import sys

import fastcgi
import selectfcgi
import handler

def test():
    if stat.S_ISSOCK(os.fstat(fastcgi.FCGI_LISTENSOCK_FILENO)[stat.ST_MODE]):
        print 'using pre-set fastcgi environment'
        sys.stdout.flush()
        s = fastcgi.FCGI_LISTENSOCK_FILENO
    else:
        s = None

    server = selectfcgi.FastCGIServer(s, handler.handler)
    server.port = 'fcgi.socket'

    try:
        server.run()
    except KeyboardInterrupt:
        os.unlink(server.port)

if __name__ == '__main__':
    test()
