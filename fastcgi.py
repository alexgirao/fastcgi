# -*- coding: utf-8 -*-

'''
FastCGI implementation that supports all features from specification
version 1.0 of 29 April 1996, no later version was known from the time
of this effort.

This implementation expects session affinity from the web server when
using multiplexed connections, this is the most common case, indeed.

last change: 20 Apr 2008

Copyright Alexandre Girão <alexgirao@gmail.com> 2008, 2007
'''

import sys
import struct
import socket
import pprint
import traceback
import random
import cStringIO

_pack = struct.pack
_unpack = struct.unpack

#

# Binary structures, network byte order

# FCGI_Header {
#     B version
#     B type
#     H requestId
#     H contentLength
#     B paddingLength
#     x reserved
# }
# FCGI_BeginRequestBody {
#     H role
#     B flags
#     x reserved[5]
# }
# FCGI_EndRequestBody {
#     I appStatus
#     B protocolStatus
#     x reserved[3]
# }
# FCGI_UnknownTypeBody {
#     B type
#     x reserved[7]
# }
# FCGI_BeginRequestRecord {
#     FCGI_Header
#     FCGI_BeginRequestBody
# }
# FCGI_EndRequestRecord {
#     FCGI_Header
#     FCGI_EndRequestBody
# }
# FCGI_UnknownTypeRecord {
#     FCGI_Header
#     FCGI_UnknownTypeBody
# }
#

FCGI_Header             = "!BBHHBx"
FCGI_HeaderVTR          = "!BBH"         # version, type and requestId
FCGI_HeaderCached       = "!4sHBx"       # cached version, type and requestId

FCGI_Header_VERSION         = 0
FCGI_Header_TYPE            = 1
FCGI_Header_REQUESTID       = 2
FCGI_Header_CONTENTLENGTH   = 3
FCGI_Header_PADDINGLENGTH   = 4

assert struct.pack(FCGI_Header, 1, 2, 3, 4, 5) == struct.pack(FCGI_HeaderCached, '\x01\x02\x00\x03', 4, 5)

FCGI_BeginRequestBody   = "!HB5x"
FCGI_EndRequestBody     = "!IB3x"
FCGI_UnknownTypeBody    = "!B7x"

FCGI_Header_STRUCT_LENGTH = struct.calcsize(FCGI_Header)
FCGI_BeginRequestBody_STRUCT_LENGTH = struct.calcsize(FCGI_BeginRequestBody)
FCGI_EndRequestBody_STRUCT_LENGTH = struct.calcsize(FCGI_EndRequestBody)
FCGI_UnknownTypeBody_STRUCT_LENGTH = struct.calcsize(FCGI_UnknownTypeBody)

# Constants

FCGI_LISTENSOCK_FILENO = 0      # listening socket file number
FCGI_HEADER_LEN = 8             # number of bytes in a FCGI_Header
FCGI_VERSION_1 = 1              # value for version component of FCGI_Header

assert FCGI_HEADER_LEN == FCGI_Header_STRUCT_LENGTH

# Values for type component of FCGI_Header
FCGI_BEGIN_REQUEST      = 1
FCGI_ABORT_REQUEST      = 2
FCGI_END_REQUEST        = 3
FCGI_PARAMS             = 4
FCGI_STDIN              = 5
FCGI_STDOUT             = 6
FCGI_STDERR             = 7
FCGI_DATA               = 8
FCGI_GET_VALUES         = 9
FCGI_GET_VALUES_RESULT  = 10
FCGI_UNKNOWN_TYPE       = 11
FCGI_MAXTYPE            = FCGI_UNKNOWN_TYPE

FCGI_TYPE_NAMES = {
    FCGI_BEGIN_REQUEST: 'FCGI_BEGIN_REQUEST',
    FCGI_ABORT_REQUEST: 'FCGI_ABORT_REQUEST',
    FCGI_END_REQUEST:   'FCGI_END_REQUEST',
    FCGI_PARAMS:        'FCGI_PARAMS',
    FCGI_STDIN:         'FCGI_STDIN',
    FCGI_STDOUT:        'FCGI_STDOUT',
    FCGI_STDERR:        'FCGI_STDERR',
    FCGI_DATA:          'FCGI_DATA',
    FCGI_GET_VALUES:    'FCGI_GET_VALUES',
    FCGI_GET_VALUES_RESULT: 'FCGI_GET_VALUES_RESULT',
    FCGI_UNKNOWN_TYPE:      'FCGI_UNKNOWN_TYPE'
}

FCGI_TYPE_IS_APPLICATION_RECORD = {
    FCGI_BEGIN_REQUEST: True,
    FCGI_ABORT_REQUEST: True,
    FCGI_END_REQUEST:   True,
    FCGI_PARAMS:        True,
    FCGI_STDIN:         True,
    FCGI_STDOUT:        True,
    FCGI_STDERR:        True,
    FCGI_DATA:          True,
    FCGI_GET_VALUES:    False,
    FCGI_GET_VALUES_RESULT: False,
    FCGI_UNKNOWN_TYPE:      False
}

# Value for requestId component of FCGI_Header
FCGI_NULL_REQUEST_ID = 0

# Mask for flags component of FCGI_BeginRequestBody
FCGI_KEEP_CONN = 1

# Values for role component of FCGI_BeginRequestBody
FCGI_RESPONDER  = 1
FCGI_AUTHORIZER = 2
FCGI_FILTER     = 3

FCGI_ROLE_NAMES = {
    FCGI_RESPONDER:  'FCGI_RESPONDER',
    FCGI_AUTHORIZER: 'FCGI_AUTHORIZER',
    FCGI_FILTER:     'FCGI_FILTER'
}

FCGI_VALID_ROLES = (FCGI_RESPONDER, FCGI_AUTHORIZER, FCGI_FILTER)

# Values for protocolStatus component of FCGI_EndRequestBody
FCGI_REQUEST_COMPLETE   = 0
FCGI_CANT_MPX_CONN      = 1
FCGI_OVERLOADED         = 2
FCGI_UNKNOWN_ROLE       = 3

FCGI_PROTOCOLSTATUS_NAMES = {
    FCGI_REQUEST_COMPLETE:  'FCGI_REQUEST_COMPLETE',
    FCGI_CANT_MPX_CONN:     'FCGI_CANT_MPX_CONN',
    FCGI_OVERLOADED:        'FCGI_OVERLOADED',
    FCGI_UNKNOWN_ROLE:      'FCGI_UNKNOWN_ROLE'
}

# Variable names for FCGI_GET_VALUES / FCGI_GET_VALUES_RESULT records
FCGI_MAX_CONNS  = "FCGI_MAX_CONNS"
FCGI_MAX_REQS   = "FCGI_MAX_REQS"
FCGI_MPXS_CONNS = "FCGI_MPXS_CONNS"

# name-value pair handling for use with fastcgi protocol

def writePair(name, value):
    """write a fastcgi name-value pair"""
    namelen = len(name)
    if namelen < 0x80:
        data = chr(namelen)
    else:
        data = _pack("!I", namelen | 0x80000000L)

    valuelen = len(value)
    if valuelen < 0x80:
        data += chr(valuelen)
    else:
        data += _pack("!I", valuelen | 0x80000000L)

    return data + name + value

def readPair(data, pos):
    """read a fastcgi name-value pair"""
    namelen = ord(data[pos])
    if namelen & 0x80:
        namelen = _unpack("!I", data[pos:pos + 4])[0] & 0x7fffffff
        pos += 4
    else:
        pos += 1

    valuelen = ord(data[pos])
    if valuelen & 0x80:
        valuelen = _unpack("!I", data[pos:pos + 4])[0] & 0x7fffffff
        pos += 4
    else:
        pos += 1

    name = data[pos:pos + namelen]
    pos += namelen
    
    value = data[pos:pos + valuelen]
    pos += valuelen

    return name, value, pos

def splitRecords(data, pos=0):
    r = []
    datalen = len(data)
    while pos < datalen:
        header = _unpack(FCGI_Header, data[pos:pos + FCGI_HEADER_LEN])
        version, type, requestId, contentLength, paddingLength = header
        cpos = pos + FCGI_HEADER_LEN
        r.append((
            header,
            data[cpos:cpos + contentLength]
        ))
        pos += FCGI_HEADER_LEN + contentLength + paddingLength
    
    assert pos == datalen
    
    return r

def debugRecord(header, content, trunkOutput=0):
    '''header _unpack(FCGI_Header, ...)
       content the data specified by contentLength at header
    '''
   
    version, type, requestId, contentLength, paddingLength = header
    
    if type == FCGI_BEGIN_REQUEST:
        role, flags = _unpack(FCGI_BeginRequestBody, content)
        detail = 'role=%i, flags=0x%.2x' % (role, flags)
    elif type == FCGI_END_REQUEST:
        appStatus, protocolStatus = _unpack(FCGI_EndRequestBody, content)
        detail = 'appStatus=%i, protocolStatus=%s' % (
            appStatus,
            FCGI_PROTOCOLSTATUS_NAMES[protocolStatus]
        )
    elif type in (FCGI_PARAMS, FCGI_GET_VALUES, FCGI_GET_VALUES_RESULT):
        pos = 0
        params = {}
        while pos < contentLength:
            name, value, pos = readPair(content, pos)
            params[name] = value
        if trunkOutput:
            detail = pprint.pformat(params)[0:trunkOutput] + " ...'"
        else:
            detail = pprint.pformat(params)
    elif type in (FCGI_STDOUT, FCGI_STDERR, FCGI_STDIN, FCGI_STDOUT):
        if trunkOutput and len(content) > trunkOutput:
            detail = repr(content[0:trunkOutput] + " ...")
        else:
            detail = repr(content)
    elif type == FCGI_ABORT_REQUEST:
        detail = ''     # no details to FCGI_ABORT_REQUEST
    else:
        detail = "???"
    
    return '%s id=%i len=%i %s' % (FCGI_TYPE_NAMES[type], requestId, contentLength, detail)

def debugRecords(data, pos=0, trunkOutput=0):
    r = []
    for h, c in splitRecords(data, pos):
        r.append(debugRecord(h,c,trunkOutput))
    return r

def makeDiscreteRecord(type, requestId, discreteStruct, *discreteValues):
    return _pack(FCGI_Header, 1, type, requestId, struct.calcsize(discreteStruct), 0) + \
        _pack(discreteStruct, *discreteValues)

def makeStreamRecord(type, requestId, data):
    return '%s%s' % (_pack(FCGI_Header, 1, type, requestId, len(data), 0), data)

def dictToPairs(d):
    r = []
    for k, v in d.items():
        r.append(writePair(k,str(v)))
    return r

## FastCGI Classes
#
# - FastCGIRequestState     - the request state, request specific information
# - FastCGIProcessor        - manages requests, detached from protocol to allow multiplexing
#

class FastCGIRequestState(object):
    '''a low level class that store and manages request state
    '''
    
    def __init__(self, processor, requestId, stdout, stderr, loseConnection):
        self.processor = processor
        self.requestId = requestId
        self.stdout = stdout            # session affinity is required
        self.stderr = stderr            # session affinity is required
        self.loseConnection = loseConnection    # lose connection callable
        
        self.stdoutHeader = _pack(FCGI_HeaderVTR, 1, FCGI_STDOUT, requestId)
        self.stderrHeader = _pack(FCGI_HeaderVTR, 1, FCGI_STDERR, requestId)
        
        self.role = None
        self.keepConnection = False     # FCGI_KEEP_CONN flag at FCGI_BEGIN_REQUEST

        self.callCount = 0              # how many times this request state was handled

        self.params = {}
        self.paramsReady = False
        
        self.stdinLength = 0            # amount of stdin received so far
        self.dataLength = 0             # amount of data received so far
        
        self.appStatus = 0              # appStatus used to end this request
        self.needCloseStderr = False

    def write(self, data):
        '''write to the stdout channel (normal output)
        '''
        if data:
            # this prevents the user from closing the stdout stream, let end() do this
            self.stdout.write(_pack(FCGI_HeaderCached, self.stdoutHeader, len(data), 0))
            self.stdout.write(data)

    def error(self, data):
        '''write to the error channel
        '''
        if data:
            # this prevents the user from closing the stderr stream, let end() do this
            self.stderr.write(_pack(FCGI_HeaderCached, self.stderrHeader, len(data), 0))
            self.stderr.write(data)
            self.needCloseStderr = True

    def end(self, appStatus=0, protocolStatus=FCGI_REQUEST_COMPLETE):
        if not self.stdout:
            # ended already
            return
        
        self.appStatus = appStatus

        # close stdout stream
        self.stdout.write(_pack(FCGI_HeaderCached, self.stdoutHeader, 0, 0))

        if self.needCloseStderr:
            # close stderr stream
            self.stderr.write(_pack(FCGI_HeaderCached, self.stderrHeader, 0, 0))
        
        # respond FCGI_END_REQUEST
        self.stdout.write(_pack(FCGI_Header, 1, FCGI_END_REQUEST, self.requestId, FCGI_EndRequestBody_STRUCT_LENGTH, 0))
        self.stdout.write(_pack(FCGI_EndRequestBody, appStatus, protocolStatus))

        if not self.keepConnection:
            self.loseConnection()

        processor = self.processor

        self.stdout = None
        self.stderr = None
        self.processor = None

        try:
            del processor.requests[self.requestId]
        except KeyError:
            pass

class FastCGIProcessor(object):
    '''manage requests processing and liveness'''

    class configproperty(object):
        def __init__(self, name, value=None):
            self.name = name
            self.value = value

        def __get__(self, instance, owner):
            if hasattr(instance, 'config') and self.name in instance.config:
                return instance.config[self.name]
            else:
                return self.value
                
        def __set__(self, instance, value):
            if not hasattr(instance, 'config'):
                instance.config = {}
            instance.config[self.name] = value

        def __delete__(self, instance):
            if hasattr(instance, 'config') and self.name in instance.config:
                del instance.config[self.name]
    
    configMaxConns  = configproperty('FCGI_MAX_CONNS')
    configMaxReqs   = configproperty('FCGI_MAX_REQS')
    configMpxsConns = configproperty('FCGI_MPXS_CONNS')

    # set to true to analyze
    showWarnings = False
    showErrors = False

    def __init__(self):
        self.requests = {}
        
        # streams to respond to management records and
        # errors messages respectively
        self.stdout = None
        self.stderr = None
        self.pendingData = None
        
        # populate configuration
        self.configMaxConns = 10
        self.configMaxReqs = 100
        self.configMpxsConns = 1    # 1 = True, 0 = False

        self.eventQueue = []       # a list of (requestState, FCGI_(type), data)

    def _processGetValues(self, requestState, content):
        # process FCGI_GET_VALUES logic

        valuesResult = {}

        pos = 0
        while pos < len(content):
            name, value, pos = readPair(content, pos)
            if value:
                self.warning('FCGI_GET_VALUES expect empty values, but found a value for name %r' % name)
                return
            if name in self.config:
                valuesResult[name] = self.config[name]
            else:
                # omit as spec says, but warn also
                self.warning('FCGI_GET_VALUES received an unknown variable: %r' % name)

        self.stdout.write(makeStreamRecord(FCGI_GET_VALUES_RESULT,
            FCGI_NULL_REQUEST_ID, ''.join(dictToPairs(valuesResult))))

    def _processBeginRequest(self, requestState, content):
        # process FCGI_BEGIN_REQUEST logic
        
        requestId = requestState.requestId

        if len(content) != FCGI_BeginRequestBody_STRUCT_LENGTH:
            self.fatalRequestError(requestState, 'FCGI_BEGIN_REQUEST content length for request %i is invalid: %i bytes' %
                (requestId, len(content))
            )
            return

        role, flags = _unpack(FCGI_BeginRequestBody, content)

        if self.requests.get(requestId, False):
            self.fatalRequestError(self.requests[requestId],
                'FCGI_BEGIN_REQUEST(%i) was called for another still live request, aborting' %
                requestId
            )
            requestState.end(3)
            return

        if role not in FCGI_VALID_ROLES:
            self.fatalRequestError(requestState, 'FCGI_BEGIN_REQUEST(%i) with an unknown role %i' %
                (requestId, role), FCGI_UNKNOWN_ROLE)
            return

        requestState.role = role
        requestState.keepConnection = bool(flags & FCGI_KEEP_CONN)

        # no keep-connection means no multiplexing for this connection, maybe other
        # transport connection support, this is up to the web-server

        self.requests[requestId] = requestState

        # sys.stdout.write(' +%i' % requestId)
        
        return requestState

    def _processParams(self, requestState, content):
        # process FCGI_PARAMS logic

        if requestState.paramsReady:
            self.fatalRequestError(requestState, 'FCGI_PARAMS already received all params')
            return

        if not content:
            requestState.paramsReady = True
            self.eventQueue.append((requestState, FCGI_PARAMS, None))
            return requestState

        pos = 0
        _l = len(content)
        _p = requestState.params
        while pos < _l:
            name, value, pos = readPair(content, pos)
            _p[name] = value

        if pos != _l:
            self.fatalRequestError(requestState, 'FCGI_PARAMS content is corrupted')
            return

        return requestState

    def _processStdin(self, requestState, content):
        # process FCGI_STDIN logic

        if not content:
            if requestState.stdinLength:
                if 'CONTENT_LENGTH' in requestState.params:
                    i = int(requestState.params['CONTENT_LENGTH'])
                    if requestState.stdinLength != i:
                        self.fatalRequestError(requestState, 'FCGI_STDIN stream length (%i) does not match CONTENT_LENGTH (%i)' %
                            (requestState.stdinLength, i))
                        return
                else:
                    requestState.error('FCGI_STDIN for request %i did not specified CONTENT_LENGTH' % requestState.requestId)

            # notify stdin close
            self.eventQueue.append((requestState, FCGI_STDIN, None))

            return requestState

        requestState.stdinLength += len(content)

        # notify stdin input
        self.eventQueue.append((requestState, FCGI_STDIN, content))
        
        return requestState

    def _processData(self, requestState, content):
        # process FCGI_DATA logic

        if not content:
            if requestState.dataLength:
                if 'FCGI_DATA_LENGTH' in requestState.params:
                    i = int(requestState.params['FCGI_DATA_LENGTH'])
                    if requestState.dataLength != i:
                        self.fatalRequestError(requestState, 'FCGI_DATA stream length (%i) does not match FCGI_DATA_LENGTH (%i)'
                            % (requestState.dataLength, i))
                        return
                else:
                    requestState.error('FCGI_DATA for request %i did not specified CONTENT_LENGTH' % requestState.requestId)

            # notify data close
            self.eventQueue.append((requestState, FCGI_DATA, None))
            
            return requestState

        requestState.dataLength += len(content)

        # notify data input
        self.eventQueue.append((requestState, FCGI_DATA, content))

        return requestState

    def _processAbortRequest(self, requestState, content):
        # process FCGI_ABORT_REQUEST logic

        if content:
            requestState.error('FCGI_ABORT_REQUEST sent unexpected content while aborting request %i' % requestState.requestId)

        requestState.end(2)
        
        # notify abort
        self.eventQueue.append((requestState, FCGI_ABORT_REQUEST, None))

        return requestState

    # all request types that may come from the web server
    _ws2app = {
        FCGI_GET_VALUES:    _processGetValues,      # management, stream
        FCGI_BEGIN_REQUEST: _processBeginRequest,   # request, discrete
        FCGI_ABORT_REQUEST: _processAbortRequest,   # request, discrete
        FCGI_PARAMS:        _processParams,         # request, stream
        FCGI_STDIN:         _processStdin,          # request, stream
        FCGI_DATA:          _processData            # request, stream
    }

    def warning(self, msg):
        '''notify warnings to web server, request id is optional
        '''
        if self.showWarnings:
            print 'warning: %s' % msg
        self.stderr.write(makeStreamRecord(FCGI_STDERR, FCGI_NULL_REQUEST_ID, msg))

    def fatalRequestError(self, requestState, msg, protocolStatus=FCGI_REQUEST_COMPLETE):
        '''fatal error happend to a request, valid request id is required
        '''
        if self.showErrors:
            print 'error: %s' % msg
        requestState.error(msg)
        requestState.end(3, protocolStatus)

    def setStdoutStderrStream(self, stdout, stderr):
        self.stdout = stdout
        self.stderr = stderr

    def processRecord(self, loseConnection, type, requestId, content):
        '''process one record at a time, returns the request state
        object if the processed record was an application record

        arguments:
         - loseConnection is a callable to schedule transports's finalization
         - type is the record's type
         - requestId is the record's request id, maybe FCGI_NULL_REQUEST_ID
         - content is the record's data

        this method assumes that content is of contentLength bytes (as
        specified by FCGI_Header record), no more, no less.
        '''

        try:
            processor = self._ws2app[type]
        except KeyError, err:
            self.warning('invalid request type: %i' % type)
            return

        if type == FCGI_BEGIN_REQUEST:
            # new request state
            requestState = FastCGIRequestState(self, requestId, self.stdout, self.stderr, loseConnection)
        elif type == FCGI_GET_VALUES:
            # expect FCGI_NULL_REQUEST_ID
            requestState = None
        else:
            # received FCGI_PARAMS, FCGI_STDIN, FCGI_DATA or FCGI_ABORT_REQUEST
            try:
                requestState = self.requests[requestId]
            except KeyError, err:
                # ignore invalid request ids, just as fcgi-spec.html
                # says in "Managing Request IDs" section
                return

        return processor(self, requestState, content)

    def cancelRequest(self, requestState):
        if requestState.requestId in self.requests:
            del self.requests[requestState.requestId]
        
    def generateOutput(self, handler):
        '''dispatch output handlers for the requests that are ready
        call handler(processor, requestState, record type, related content)
        '''

        while self.eventQueue:
            item = self.eventQueue.pop(0)

            try:
                item[0].callCount += 1
                # call handler(processor, requestState, record type, related content)
                if not handler(self, *item):
                    # returning not null value means that the handler expect more data
                    # to come, this is specialy useful for interleaving stdin and stdout
                    # streams (e.g.: respond while receive) or when dealing with
                    # keep-alive connections.
                    item[0].end(0)
            
            except socket.error:
                # let protocol/server handle socket related errors
                raise
            except Exception, err:
                print 'processor: exception occurred while handling request id %i, exception: %s' % (
                    item[0].requestId, str(err))
                traceback.print_exc(file=sys.stdout)
                item[0].end(1)
        
        # end for

    def processRawInput(self, loseConnection, data):
        if self.pendingData:
            data = self.pendingData + data
            self.pendingData = None

        pos = 0
        datalen = len(data)
        associatedRequestState = None       # used for 1 request per connection condition test

        while pos < datalen:
            if pos + FCGI_HEADER_LEN > datalen:
                self.pendingData = data[pos:]
                break

            version, type, requestId, contentLength, paddingLength = _unpack(FCGI_Header, data[pos:pos + FCGI_HEADER_LEN])
            cpos = pos + FCGI_HEADER_LEN

            if cpos + contentLength + paddingLength > datalen:
                self.pendingData = data[pos:]
                break

            content = data[cpos:cpos + contentLength]
            pos += FCGI_HEADER_LEN + contentLength + paddingLength

            requestState = self.processRecord(loseConnection, type, requestId, content)
            if requestState:
                if associatedRequestState:
                    # ensure that we have one request per connection
                    # setting
                    assert requestState is associatedRequestState
                elif not requestState.keepConnection:
                    # the web server want us to tie this connection to
                    # this request and kill the connection as soon as
                    # the request is over, one request per connection
                    associatedRequestState = requestState

        return associatedRequestState

def testnamevalues():
    
    def test(n,v):
        if len(n) >= 0x80:
            totalsize = 4
        else:
            totalsize = 1
        
        if len(v) >= 0x80:
            totalsize += 4
        else:
            totalsize += 1
        
        totalsize += len(n) + len(v)
        
        res = writePair(n, v)
        assert len(res) == totalsize
        
        nn, nv, np = readPair(res, 0)
        assert nn == n
        assert nv == v
        assert np == totalsize
    
    r = lambda: random.randint(100,200)
    
    test('alpha', 'bravo')
    test('alpha' * r(), 'bravo')
    test('alpha', 'bravo' * r())
    test('alpha' * r(), 'bravo' * r())

def testprocessor():
    fcgi_stdin = cStringIO.StringIO()
    fcgi_stdout = cStringIO.StringIO()
    fcgi_stderr = cStringIO.StringIO()
    
    def handler(processor, request, type, content):
        if type == FCGI_PARAMS:
            request.write('content-type: text/plain\r\n\r\n')
            request.write('hello world of real possibilities!!!')
    
    processor = FastCGIProcessor()
    processor.setStdoutStderrStream(fcgi_stdout, fcgi_stderr)

    params = {
        'DOCUMENT_ROOT': '/home/alexgirao/projects/fastcgi',
        'GATEWAY_INTERFACE': 'CGI/1.1',
        'HTTP_ACCEPT': 'text/xml,application/xml,application/xhtml+xml,text/html;q=0.9,text/plain;q=0.8,image/png,*/*;q=0.5',
        'HTTP_ACCEPT_CHARSET': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
        'HTTP_ACCEPT_ENCODING': 'gzip,deflate',
        'HTTP_ACCEPT_LANGUAGE': 'en-us,en;q=0.5',
        'HTTP_CACHE_CONTROL': 'max-age=0',
        'HTTP_CONNECTION': 'keep-alive',
        'HTTP_COOKIE': 'MOIN_ID=1153679717.41.36721',
        'HTTP_HOST': 'localhost:8020',
        'HTTP_KEEP_ALIVE': '300',
        'HTTP_REFERER': 'http://localhost:8020/',
        'HTTP_USER_AGENT': 'Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.8.1.3) Gecko/20070310 Iceweasel/2.0.0.3 (Debian-2.0.0.3-2)',
        'PATH_INFO': '',
        'QUERY_STRING': '',
        'REDIRECT_STATUS': '200',
        'REMOTE_ADDR': '127.0.0.1',
        'REMOTE_PORT': '39520',
        'REQUEST_METHOD': 'GET',
        'REQUEST_URI': '/fcgi-inet',
        'SCRIPT_FILENAME': '/home/alexgirao/projects/fastcgi/fcgi-inet',
        'SCRIPT_NAME': '/fcgi-inet',
        'SERVER_ADDR': '127.0.0.1',
        'SERVER_NAME': 'localhost:8020',
        'SERVER_PORT': '8020',
        'SERVER_PROTOCOL': 'HTTP/1.1',
        'SERVER_SOFTWARE': 'lighttpd/1.4.15'
    }

    fcgi_stdin.write(makeDiscreteRecord(FCGI_BEGIN_REQUEST, 1, FCGI_BeginRequestBody, FCGI_RESPONDER, FCGI_KEEP_CONN))
    fcgi_stdin.write(makeStreamRecord(FCGI_PARAMS, 1, ''.join(dictToPairs(params))))
    fcgi_stdin.write(makeStreamRecord(FCGI_PARAMS, 1, ''))
    fcgi_stdin.write(makeStreamRecord(FCGI_STDIN, 1, ''))
    fcgi_stdin.reset()

    records = splitRecords(fcgi_stdin.getvalue())
    assert len(records) == 4

    try:
        for recordHeader, recordContent in records:
            requestState = processor.processInput(lambda: None,
                recordHeader[FCGI_Header_TYPE],
                recordHeader[FCGI_Header_REQUESTID],
                recordContent
            )
            type = recordHeader[FCGI_Header_TYPE]
            if FCGI_TYPE_IS_APPLICATION_RECORD[type]:
                assert bool(requestState)

        processor.generateOutput(handler)

        fcgi_stdout.reset()
        fcgi_stderr.reset()

        assert not fcgi_stderr.getvalue()

        records = splitRecords(fcgi_stdout.getvalue())
        
        assert len(records) == 4
        assert records[0][0][FCGI_Header_TYPE] == FCGI_STDOUT and records[0][1] == 'content-type: text/plain\r\n\r\n'
        assert records[1][0][FCGI_Header_TYPE] == FCGI_STDOUT and records[1][1] == 'hello world of real possibilities!!!'
        assert records[2][0][FCGI_Header_TYPE] == FCGI_STDOUT and records[2][1] == ''
        assert records[3][0][FCGI_Header_TYPE] == FCGI_END_REQUEST and records[3][1] == '\x00\x00\x00\x00\x00\x00\x00\x00'

    except AssertionError:
        traceback.print_exc(file=sys.stdout)
        print 'stderr stream:'
        print '\n'.join(debugRecords(fcgi_stderr.getvalue()))
        print 'stdout stream:'
        print '\n'.join(debugRecords(fcgi_stdout.getvalue()))
        sys.exit(1)

def testunknowrole():
    fcgi_stdin = cStringIO.StringIO()
    fcgi_stdout = cStringIO.StringIO()
    fcgi_stderr = cStringIO.StringIO()
    
    def handler(processor, request, type, content):
        if type == FCGI_PARAMS:
            request.write('content-type: text/plain\r\n\r\n')
            request.write('hello world of real possibilities!!!')
    
    processor = FastCGIProcessor()
    processor.setStdoutStderrStream(fcgi_stdout, fcgi_stderr)
    
    # 123 is surely an unknown role
    fcgi_stdin.write(makeDiscreteRecord(FCGI_BEGIN_REQUEST, 1, FCGI_BeginRequestBody,
        123, FCGI_KEEP_CONN))
    fcgi_stdin.reset()

    records = splitRecords(fcgi_stdin.getvalue())
    assert len(records) == 1
    
    try:
        for recordHeader, recordContent in records:
            # successfully processed application records
            # must return a request state
            assert not processor.processInput(lambda: None,
                recordHeader[FCGI_Header_TYPE],
                recordHeader[FCGI_Header_REQUESTID],
                recordContent
            )

        processor.generateOutput(handler)

        fcgi_stdout.reset()
        fcgi_stderr.reset()
        
        stdout = fcgi_stdout.getvalue()
        stderr = fcgi_stderr.getvalue()
        
        assert stdout
        assert stderr

        records = splitRecords(stdout)

        assert len(records) == 2
        assert records[0][0][FCGI_Header_TYPE] == FCGI_STDOUT
        assert records[1][0][FCGI_Header_TYPE] == FCGI_END_REQUEST
        assert _unpack(FCGI_EndRequestBody, records[1][1])[1] == FCGI_UNKNOWN_ROLE

    except AssertionError:
        traceback.print_exc(file=sys.stdout)
        print 'stderr stream:'
        print '\n'.join(debugRecords(fcgi_stderr.getvalue()))
        print 'stdout stream:'
        print '\n'.join(debugRecords(fcgi_stdout.getvalue()))
        sys.exit(1)

def testgetvalues():
    fcgi_stdin = cStringIO.StringIO()
    fcgi_stdout = cStringIO.StringIO()
    fcgi_stderr = cStringIO.StringIO()
    
    def handler(processor, request, type, content):
        if type == FCGI_PARAMS:
            request.write('content-type: text/plain\r\n\r\n')
            request.write('hello world of real possibilities!!!')
    
    processor = FastCGIProcessor()
    processor.setStdoutStderrStream(fcgi_stdout, fcgi_stderr)
    
    params = {
        'FCGI_MAX_CONNS': '',
        'FCGI_MAX_REQS': '',
        'FCGI_MPXS_CONNS': '',
        'SPECIFIC_VAR1': '',        # must be omited in response
        'SPECIFIC_VAR2': ''         # must be omited in response
    }

    fcgi_stdin.write(makeStreamRecord(FCGI_GET_VALUES, FCGI_NULL_REQUEST_ID, ''.join(dictToPairs(params))))
    fcgi_stdin.reset()

    records = splitRecords(fcgi_stdin.getvalue())
    assert len(records) == 1
    
    try:
        for recordHeader, recordContent in records:
            requestState = processor.processInput(lambda: None,
                recordHeader[FCGI_Header_TYPE],
                recordHeader[FCGI_Header_REQUESTID],
                recordContent
            )
            type = recordHeader[FCGI_Header_TYPE]
            if FCGI_TYPE_IS_APPLICATION_RECORD[type]:
                assert bool(requestState)

        processor.generateOutput(handler)

        fcgi_stdout.reset()
        fcgi_stderr.reset()
        
        stdout = fcgi_stdout.getvalue()
        stderr = fcgi_stderr.getvalue()

        assert stdout
        assert stderr

    except AssertionError:
        traceback.print_exc(file=sys.stdout)
        print 'stderr stream:'
        print '\n'.join(debugRecords(fcgi_stderr.getvalue()))
        print 'stdout stream:'
        print '\n'.join(debugRecords(fcgi_stdout.getvalue()))
        sys.exit(1)

if __name__ == '__main__':
    testnamevalues()
    testprocessor()
    testunknowrole()
    testgetvalues()
