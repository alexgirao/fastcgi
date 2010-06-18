# -*- coding: utf-8 -*-

'''a low-level fastcgi server using only twisted core
'''

import twisted.internet.protocol as protocol
import fastcgi

FastCGIConnectionState = fastcgi.FastCGIConnectionState

def _w2(w1, w2, d):
    w1(d)
    w2(d)

class FastCGIProtocol(protocol.Protocol):
    '''handles a connection with the web server
    '''

    def connectionMade(self):
        self.processor = self.factory.fcgiProcessor
        write0 = self.transport.write
        if self.factory.dumpfile:
            write1 = self.factory.dumpfile.write
            write = lambda data: _w2(write1, write0, data)
        else:
            write = write0
        self.connectionState = FastCGIConnectionState(self.transport.loseConnection, write)

    def dataReceived(self, data):
        self.processor.processRawInput(self.connectionState, data)
        self.processor.generateOutput(self.factory.handler)

    def connectionLost(self, reason):
        self.connectionState.cleanup()
        self.connectionState = None
        self.processor = None

class FastCGIFactory(protocol.Factory):
    protocol = FastCGIProtocol

    def __init__(self, handler, dumpfile=None):
        self.handler = handler
        self.dumpfile = dumpfile

    def startFactory(self):
        self.fcgiProcessor = fastcgi.FastCGIProcessor()
