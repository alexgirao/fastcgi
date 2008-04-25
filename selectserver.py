#!/usr/bin/env python

'''
an asynchronous select based server and a basic protocol api (inspired
by twisted matrix framework)
'''

# nc -q1 localhost 8030 < file.in > file.out && sha1sum file.in file.out

import sys
import select
import socket
import signal
import traceback

class Protocol(object):
    sock = None
    address = None
    outputbuffer = None
    disconnecting = None        # state after disconnect() transition
    
    def __init__(self, sock, address):
        self.sock = sock
        self.address = address
        self.outputbuffer = None
        self.disconnecting = False

    def handleConnect(self, server):
        '''called after server accepts client connection
        '''
        print 'client connected'

    def handleDisconnect(self, closedByPeer):
        '''called when client disconnects or protocol
        disconnect (closedByPeer  argument tells the case)
        '''
        print 'client disconnected, closed by peer? %s' % closedByPeer

    def handleInput(self):
        '''called when there is data to be read
        '''
        read = self.read(16384)
        print 'read %i bytes, writing back' % len(read)
        self.write(read)

    def handleSocketError(self, errcode, errmsg):
        '''socket errors
        '''
        print 'socket error code: %i = %s' % (errcode, errmsg)

    def handleUnknownException(self, e):
        '''called when a non-socket exception occured in input handling
        '''
        print 'unknown exception: %r' % str(e)

    # the methods below may not be overrided, unless you really know
    # what you are doing

    def fileno(self):
        return self.sock.fileno()

    def read(self, amount):
        '''read protocol data, calling more than once
        may block
        '''
        return self.sock.recv(amount)

    def write(self, data):
        '''write protocol data
        '''
        if self.outputbuffer:
            # do a fifo
            if data:
                self.outputbuffer.append(data)
           
            data = ''
            sent = 0
            
            while self.outputbuffer and sent == len(data):
                data = self.outputbuffer.pop(0)
                sent = self.sock.send(data)
            
            if sent < len(data):
                self.outputbuffer.insert(0, data[sent:])
            else:
                # successfully wrote all output buffer
                self.outputbuffer = None
        else:
            sent = self.sock.send(data)
            if sent < len(data):
                self.outputbuffer = [data[sent:]]

    def flush(self):
        '''try to flush all pending data, may not send
        all data at once, must be called later if there
        is still data remaining to be sent
        '''
        data = ''
        sent = 0
        while self.outputbuffer and sent == len(data):
            data = self.outputbuffer.pop(0)
            sent = self.sock.send(data)
        if sent < len(data):
            self.outputbuffer.insert(0, data[sent:])

    def disconnect(self):
        '''prepare the protocol to be disconnected
        '''
        self.disconnecting = True

    #def __del__(self):
    #    print 'omg, im dying!'

class Server(object):

    host = ''
    port = None
    backlog = 5
    
    protocol = Protocol

    # a future enchancement would be the ability to listen
    # for various server sockets, but for now, i only need
    # one server socket
    serversocket = None
    
    # used for debug
    raiseAllErrors = True
    outputTraceback = True

    def createServerSocket(self):
        if not self.port:
            raise Exception('port to listen to is not defined')
        
        if isinstance(self.port, (str, unicode)):
            sock = socket.socket(socket.AF_UNIX)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(self.port)
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))

        sock.listen(self.backlog)

        return sock

    def numProtocols(self):
        return len(self._input) - 1

    def run(self):
        self.serversocket = self.createServerSocket()
        server = self.serversocket

        input = [server]
        output = []
        exception = []

        self._input = input

        protocol = self.protocol

        while 1:
            inputready, outputready, _ = select.select(input, output, exception)

            for s in inputready:

                if s == server:
                    p = protocol(*server.accept())
                    p.handleConnect(self)
                    if p.outputbuffer:
                        output.append(p)
                    elif p.disconnecting:
                        p.sock.close()

                        try:
                            p.handleDisconnect(False)
                        except:
                            if self.raiseAllErrors:
                                raise
                            if self.outputTraceback:
                                traceback.print_exc(file=sys.stdout)

                    else:
                        input.append(p)
                else:
                    try:
                        if not s.sock.recv(1, socket.MSG_PEEK):
                            # client closed connection
                            input.remove(s)
                            s.sock.close()

                            try:
                                s.handleDisconnect(True)
                            except:
                                if self.raiseAllErrors:
                                    raise
                                if self.outputTraceback:
                                    traceback.print_exc(file=sys.stdout)

                            continue

                        s.handleInput()

                        if s.outputbuffer:
                            # input -> output
                            input.remove(s)
                            output.append(s)
                        elif s.disconnecting:
                            input.remove(s)
                            s.sock.close()

                            try:
                                s.handleDisconnect(False)
                            except:
                                if self.raiseAllErrors:
                                    raise
                                if self.outputTraceback:
                                    traceback.print_exc(file=sys.stdout)
                    
                    except socket.error, (errcode, errmsg):
                        input.remove(s)

                        if self.raiseAllErrors:
                            raise
                        if self.outputTraceback:
                            traceback.print_exc(file=sys.stdout)

                        try:
                            s.handleDisconnect(False)
                        except:
                            if self.raiseAllErrors:
                                raise
                            if self.outputTraceback:
                                traceback.print_exc(file=sys.stdout)

                        try:
                            s.handleSocketError(errcode, errmsg)
                        except:
                            if self.raiseAllErrors:
                                raise
                            if self.outputTraceback:
                                traceback.print_exc(file=sys.stdout)

                    except Exception, e:
                        if self.raiseAllErrors:
                            raise
                        if self.outputTraceback:
                            traceback.print_exc(file=sys.stdout)

                        try:
                            s.handleDisconnect(False)
                        except:
                            if self.raiseAllErrors:
                                raise
                            if self.outputTraceback:
                                traceback.print_exc(file=sys.stdout)

                        try:
                            s.handleUnknownException(e)
                        except:
                            if self.raiseAllErrors:
                                raise
                            if self.outputTraceback:
                                traceback.print_exc(file=sys.stdout)

            for s in outputready:
                s.flush()
                if s.outputbuffer:
                    continue
                
                # output -> input
                output.remove(s)
                if s.disconnecting:
                    s.sock.close()

                    try:
                        s.handleDisconnect(False)
                    except:
                        if self.raiseAllErrors:
                            raise
                        if self.outputTraceback:
                            traceback.print_exc(file=sys.stdout)

                else:
                    input.append(s)

        # end loop

        server.close()

    def stop(self):
        if self.serversocket:
            self.serversocket.close()


if __name__ == '__main__':
    def sigterm_handler(signum, frame):
        print 'received term signal'
        s.stop()

    signal.signal(signal.SIGTERM, sigterm_handler)

    s = Server()
    s.port = 8030
    
    try:
        s.run()
    except Exception, e:
        traceback.print_exc(file=sys.stdout)
        s.stop()
