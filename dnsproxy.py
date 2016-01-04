"""http://code.activestate.com/recipes/491264-mini-fake-dns-server/"""
from __future__ import print_function

import socket, sys
import binascii,copy,struct, time
from dnslib import DNSRecord,RR,QTYPE,RCODE,parse_time,A
from dnslib.server import DNSServer,DNSHandler,BaseResolver,DNSLogger
from dnslib.label import DNSLabel

class InterceptResolver(BaseResolver):

    """
        Intercepting resolver 
        
        Proxy requests to upstream server optionally intercepting requests
        matching local records
    """

    def __init__(self,address,port,ttl,d):
        """
            address/port    - upstream server
            ttl             - default ttl for intercept records
        """
        self.address = address
        self.port = port
        self.ttl = parse_time(ttl)
        self.d = d

    def resolve(self,request,handler):
        reply = request.reply()
        qname = request.q.qname
        qtype = QTYPE[request.q.qtype]
        if qname.matchGlob("api-*padsv.gungho.jp."):# or qname.matchGlob('mitm.it'):
            reply.add_answer(RR(qname,QTYPE.A,rdata=A(socket.gethostbyname(socket.gethostname()))))
            self.d['api'] = str(qname)[:-1]
        else:
            self.d['api'] = ''
        # Otherwise proxy
        if not reply.rr:
            if handler.protocol == 'udp':
                proxy_r = request.send(self.address,self.port)
            else:
                proxy_r = request.send(self.address,self.port,tcp=True)
            reply = DNSRecord.parse(proxy_r)
        return reply

def serveDNS(d):
    
    resolver = InterceptResolver('8.8.8.8',
                                 53,
                                 '60s', d)
    logger = DNSLogger("request,reply,truncated,error",False)


    DNSHandler.log = { 
        'log_request',      # DNS Request
        'log_reply',        # DNS Response
        'log_truncated',    # Truncated
        'log_error',        # Decoding error
    }

    udp_server = DNSServer(resolver,
                           port=53,
                           address=socket.gethostbyname(socket.gethostname()),
                           logger=logger)
    udp_server.start_thread()

    while udp_server.isAlive():
        time.sleep(1)