# -*- coding: utf-8 -*-

'''FastCGI server using selectserver module
'''

import sys
import os
import socket
import _socket
import errno
import struct
import stat

import selectserver
import fastcgi
import cStringIO

StringIO = cStringIO.StringIO

_FCGI_Header = fastcgi.FCGI_Header
_FCGI_HEADER_LEN = fastcgi.FCGI_HEADER_LEN

_pack = struct.pack
_unpack = struct.unpack

class FastCGIProtocol(selectserver.Protocol):
    '''handles a connection with the web server
    '''

    # used for non multiplexed connections
    associatedRequestState = None
    processor = None
    server = None

    def handleConnect(self, server):
        self.server = server
        self.processor = server.fcgiProcessor
        self.associatedRequestState = None

    def handleInput(self):
        data = self.read(65536)
        processor = self.processor
        processor.setStdoutStderrStream(self, self)
        processor.processRawInput(self.disconnect, data)
        processor.generateOutput(self.server.handler)

    def handleDisconnect(self, closedByPeer):
        #sys.stdout.write(' *%i' % self.server.numProtocols())
        pass

    def cleanup(self):
        del self.server
        del self.processor
        del self.associatedRequestState
        selectserver.Protocol.cleanup(self)

class FastCGIServer(selectserver.Server):
    """Handle FastCGI requests"""

    host = ''
    port = None
    backlog = 10

    handler = None

    protocol = FastCGIProtocol

    def __init__(self, listensocket, handler):
        '''listensocket can be an integer or a socket object,
           socket is expected to be a non-blocking socket
        '''

        if listensocket is None:
            pass
        elif isinstance(listensocket, int):
            if not stat.S_ISSOCK(os.fstat(listensocket)[stat.ST_MODE]):
                raise ValueError('file descriptor %i must be a socket (unix or inet)' % listensocket)
            
            if not hasattr(socket, 'fromfd'):
                raise Exception('socket.fromfd is not available for this platform')

            s = socket.fromfd(listensocket, socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.getpeername()
            except socket.error, (err, errmsg):
                if err != errno.ENOTCONN:
                    # no connection is an expected error, other's are not
                    raise

            self.serversocket = s
        elif isinstance(listensocket, (socket.socket, _socket.socket)):
            self.serversocket = listensocket
        else:
            raise RuntimeError('invalid argument')
            
        if not callable(handler):
            raise RuntimeError('handler is not callable')

        self.handler = handler

    def createServerSocket(self):
        if not self.serversocket:
            self.serversocket = selectserver.Server.createServerSocket(self)
            if isinstance(self.port, (str, unicode)):
                print 'opening an AF_UNIX (%r) socket for fastcgi server' % (self.port)
            else:
                print 'opening an AF_INET (%r, %i) socket for fastcgi server' % (self.host, self.port)
        return self.serversocket

    def run(self):
        self.fcgiProcessor = fastcgi.FastCGIProcessor()
        selectserver.Server.run(self)
