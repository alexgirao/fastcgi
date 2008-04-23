# -*- coding: utf-8 -*-

'''a low-level fastcgi server using only twisted core
'''

import sys
import struct

import twisted.internet.protocol as protocol
import fastcgi

_FCGI_Header = fastcgi.FCGI_Header
_FCGI_HEADER_LEN = fastcgi.FCGI_HEADER_LEN

_pack = struct.pack
_unpack = struct.unpack

class FastCGIProtocol(protocol.Protocol):
    '''handles a connection with the web server
    '''

    def __init__(self):
        self.pendingData = None

    def connectionMade(self):
        self.processor = self.factory.fcgiProcessor
        self.associatedRequestState = None

    def dataReceived(self, data):
        processor = self.processor
        processor.setStdoutStderrStream(self.transport, self.transport)
        processor.processRawInput(self.transport.loseConnection, data)
        processor.generateOutput(self.factory.handler)

    def connectionLost(self, reason):
        if self.associatedRequestState:
            self.associatedRequestState.end(0)
        del self.processor
        del self.associatedRequestState

class FastCGIFactory(protocol.Factory):
    protocol = FastCGIProtocol

    def __init__(self, handler):
        self.handler = handler

    def startFactory(self):
        self.fcgiProcessor = fastcgi.FastCGIProcessor()
