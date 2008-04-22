#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import stat
import sys

import fastcgi
import twistedfcgi
import handler

import twisted.internet.reactor as reactor

def test():
    if stat.S_ISSOCK(os.fstat(fastcgi.FCGI_LISTENSOCK_FILENO)[stat.ST_MODE]):
        raise Exception('using pre-set fastcgi environment is not yet supported')
    
    fac = twistedfcgi.FastCGIFactory(handler.handler)
    
    #reactor.listenTCP(8030, fac)
    reactor.listenUNIX('fcgi.socket', fac)
    reactor.run()

if __name__ == '__main__':
    test()
