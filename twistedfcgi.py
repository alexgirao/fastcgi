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

        if self.pendingData:
            data = self.pendingData + data
            self.pendingData = None

        pos = 0
        datalen = len(data)

        while pos < datalen:
            if pos + _FCGI_HEADER_LEN > datalen:
                self.pendingData = data[pos:]
                break
            
            version, type, requestId, contentLength, paddingLength = _unpack(_FCGI_Header, data[pos:pos + _FCGI_HEADER_LEN])
            cpos = pos + _FCGI_HEADER_LEN
            
            if cpos + contentLength + paddingLength > datalen:
                self.pendingData = data[pos:]
                break
            
            content = data[cpos:cpos + contentLength]
            pos += _FCGI_HEADER_LEN + contentLength + paddingLength

            requestState = processor.processInput(self.transport.loseConnection, type, requestId, content)
            if requestState:
                if self.associatedRequestState:
                    # ensure that we have one request per connection
                    # setting
                    assert requestState is self.associatedRequestState
                elif not requestState.keepConnection:
                    # the web server want us to tie this connection to
                    # this request and kill the connection as soon as
                    # the request is over, one request per connection
                    self.associatedRequestState = requestState

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
