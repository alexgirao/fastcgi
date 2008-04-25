# -*- coding: utf-8 -*-

'''a low-level fastcgi server using only twisted core
'''

import twisted.internet.protocol as protocol
import fastcgi

FastCGIConnectionState = fastcgi.FastCGIConnectionState

class FastCGIProtocol(protocol.Protocol):
    '''handles a connection with the web server
    '''

    def connectionMade(self):
        self.processor = self.factory.fcgiProcessor
        self.connectionState = FastCGIConnectionState(self.transport.loseConnection, self.transport.write)

    def dataReceived(self, data):
        self.processor.processRawInput(self.connectionState, data)
        self.processor.generateOutput(self.factory.handler)

    def connectionLost(self, reason):
        self.connectionState.cleanup()
        self.connectionState = None
        self.processor = None

class FastCGIFactory(protocol.Factory):
    protocol = FastCGIProtocol

    def __init__(self, handler):
        self.handler = handler

    def startFactory(self):
        self.fcgiProcessor = fastcgi.FastCGIProcessor()
