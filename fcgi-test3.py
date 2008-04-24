#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import stat
import sys

import fastcgi
import twistedfcgi
import handler

import twisted.internet.reactor as reactor

import pprint
import time

def delayed(request):
    request.write('content-type: text/plain\r\n\r\n')
    request.write('done, request id: %s %s\n' % (request.requestId, time.time()))
    request.end()

def handler(processor, request, type, content):
    if type == fastcgi.FCGI_ABORT_REQUEST:
        print 'request was aborted'
        return

    if type == fastcgi.FCGI_PARAMS:
        # todo: end request here to see what happens, bug i think
        pass

    if type == fastcgi.FCGI_STDIN and not content:
        reactor.callLater(0.1, delayed, request)

    return 1        # not done yet

def test():
    if stat.S_ISSOCK(os.fstat(fastcgi.FCGI_LISTENSOCK_FILENO)[stat.ST_MODE]):
        raise Exception('using pre-set fastcgi environment is not yet supported')
    
    fac = twistedfcgi.FastCGIFactory(handler)
    
    #reactor.listenTCP(8030, fac)
    reactor.listenUNIX('fcgi.socket', fac)
    reactor.run()

if __name__ == '__main__':
    test()
