#!/usr/bin/python
# -*- coding: utf-8 -*-

'''a simple fastcgi application using only twisted core, fast,
light and allow requests multiplexing
'''

# NO_PROXY=\* curl http://localhost:8020/fcgi-inet

import pprint

import twisted.internet.reactor as reactor

import atma.fastcgi as fastcgi
import atma.twistedfcgi as twistedfcgi

displaysize = 30

class Handler(object):

    def step1(self, request, msg):
        if not request.stdout:
            # request ended
            return
        request.write(msg)
        print 'wrote: %r' % msg
        reactor.callLater(1, self.step2, request, 'second time\n')

    def step2(self, request, msg):
        if not request.stdout:
            # request ended
            return
        request.write(msg)
        print 'wrote: %r' % msg
        reactor.callLater(1, self.step3, request, 'third time\n')

    def step3(self, request, msg):
        if not request.stdout:
            # request ended
            return
        request.write(msg)
        print 'wrote: %r' % msg
        reactor.callLater(1, self.enough, request, 'ENOUGH!!!\n')

    def enough(self, request, msg):
        if not request.stdout:
            # request ended
            return
        request.write(msg)
        print 'wrote: %r' % msg
        request.end(0)

    def __call__(self, processor, request, type, content):
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

            reactor.callLater(1, self.step1, request, 'first time\n')

        if content:
            length = len(content)
            if length > displaysize:
                content = content[0:displaysize] + ' ...'
        else:
            content = ''
            length = 0

        request.write('%i: %s: (%i bytes) %r\n' % (
            request.callCount,
            fastcgi.FCGI_TYPE_NAMES[type],
            length,
            content)
        )

        if type == fastcgi.FCGI_STDIN and not content:
            request.write('we\'re done, received %i calls\n' % (request.callCount,))

        return 1        # not done yet

def test():
    import os
    import stat
    import sys

    if stat.S_ISSOCK(os.fstat(fastcgi.FCGI_LISTENSOCK_FILENO)[stat.ST_MODE]):
        raise Exception('using pre-set fastcgi environment is not yet supported')
    
    fac = twistedfcgi.FastCGIFactory(Handler())
    
    reactor.listenTCP(8030, fac)
    #reactor.listenUNIX('fcgi.socket', fac)
    reactor.run()

if __name__ == '__main__':
    test()
