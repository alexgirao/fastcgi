
import pprint
import fastcgi

def handler(processor, request, type, content):
    if type == fastcgi.FCGI_ABORT_REQUEST:
        print 'request was aborted'
        return

    if type == fastcgi.FCGI_PARAMS:
        # at this point we received all params and we
        # can do our logic, this happens once per request

        if request.params['SERVER_SOFTWARE'].startswith('lighttpd/'):
            request.write('content-type: t')
            request.write('ext/plain\r\n\r\n')
        else:
            # nginx requires that the header comes within a single record
            request.write('content-type: text/plain\r\n\r\n')

        request.write('request id: %i\n' % request.requestId)
        request.write('role: %s\n' % fastcgi.FCGI_ROLE_NAMES[request.role])
        request.write(pprint.pformat(request.params))
        request.write('\n')

    if content:
        length = len(content)
        if length > 30:
            content = content[0:30] + ' ...'
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
        return

    return 1        # not done yet
