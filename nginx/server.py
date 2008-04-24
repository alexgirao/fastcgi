#!/usr/bin/python
# -*- coding: utf-8 -*-

'''a simple fastcgi application using only twisted core, fast,
light and allow requests multiplexing
'''

# NO_PROXY=\* curl --header 'Expect:' --data a=1 --data b=2 http://localhost:8020/fcgi-inet
# NO_PROXY=\* curl --header 'Expect:' --get --data a=1 --data b=2 http://localhost:8020/fcgi-inet
# NO_PROXY=\* curl --header 'Expect:' --data-binary @server.py http://localhost:8020/fcgi-inet
# NO_PROXY=\* curl --header 'Expect:' --form 'server.py=@server.py;type=text/plain' http://localhost:8020/fcgi-inet

import sys
import os
import stat
import pprint

import twisted.internet.reactor as reactor

import atma.fastcgi as fastcgi
import atma.twistedfcgi as twistedfcgi

displaysize = 30

def endrequest(request):
    if not request.stdout:
        # request ended already
        return
    request.end(0)

def handler(processor, request, type, content):
    if type == fastcgi.FCGI_ABORT_REQUEST:
        print 'request was aborted'
        return

    if type == fastcgi.FCGI_PARAMS:
        # at this point we received all params and we
        # can do our logic, this happens once per request
        
        request.write('content-type: text/plain\r\n')
        request.write('\r\n')
        request.write('request id: %i\n' % request.requestId)
        request.write('role: %s\n' % fastcgi.FCGI_ROLE_NAMES[request.role])
        request.write(pprint.pformat(request.params))
        request.write('\n')

    if content:
        length = len(content)
        if length > displaysize:
            content = content[0:displaysize] + ' ...'
    else:
        content = ''
        length = 0

    s = '%i: %s: (%i bytes) %r\n' % (
        request.callCount,
        fastcgi.FCGI_TYPE_NAMES[type],
        length,
        content)

    print s,
    request.write(s)

    if type == fastcgi.FCGI_STDIN and not content:
        request.write('we\'re done, received %i calls\n' % (request.callCount,))
        #return

        # nginx requires this, think it is a little dumb
        reactor.callLater(0.1, endrequest, request)
        return 1

    return 1        # not done yet

def test():

    if stat.S_ISSOCK(os.fstat(fastcgi.FCGI_LISTENSOCK_FILENO)[stat.ST_MODE]):
        raise Exception('using pre-set fastcgi environment is not yet supported')

    fac = twistedfcgi.FastCGIFactory(handler)
    
    reactor.listenTCP(8030, fac)
    #reactor.listenUNIX('fcgi.socket', fac)
    reactor.run()

if __name__ == '__main__':
    test()
