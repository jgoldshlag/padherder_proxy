"""http://code.activestate.com/recipes/491264-mini-fake-dns-server/"""
from __future__ import print_function

import socket, sys
import binascii,copy,struct, time
from dnslib import DNSRecord,RR,QTYPE,RCODE,parse_time,A
from dnslib.server import DNSServer,DNSHandler,BaseResolver,DNSLogger
from dnslib.label import DNSLabel
import wx

import custom_events

class MyDNSLogger(DNSLogger):
    def __init__(self, wxDest):
        DNSLogger.__init__(self, "request,reply,truncated,error", False)
        self.wxDest = wxDest

    def send_log_event(self, msg):
        evt = custom_events.wxLogEvent(message=msg)            
        wx.PostEvent(self.wxDest,evt)
        
    def log_recv(self,handler,data):
        self.send_log_event("%sReceived: [%s:%d] (%s) <%d> : %s" % (
                    self.log_prefix(handler),
                    handler.client_address[0],
                    handler.client_address[1],
                    handler.protocol,
                    len(data),
                    binascii.hexlify(data)))

    def log_send(self,handler,data):
        self.send_log_event("%sSent: [%s:%d] (%s) <%d> : %s" % (
                    self.log_prefix(handler),
                    handler.client_address[0],
                    handler.client_address[1],
                    handler.protocol,
                    len(data),
                    binascii.hexlify(data)))

    def log_request(self,handler,request):
        self.send_log_event("%sRequest: [%s:%d] (%s) / '%s' (%s)" % (
                    self.log_prefix(handler),
                    handler.client_address[0],
                    handler.client_address[1],
                    handler.protocol,
                    request.q.qname,
                    QTYPE[request.q.qtype]))
        self.log_data(request)

    def log_reply(self,handler,reply):
        self.send_log_event("%sReply: [%s:%d] (%s) / '%s' (%s) / RRs: %s" % (
                    self.log_prefix(handler),
                    handler.client_address[0],
                    handler.client_address[1],
                    handler.protocol,
                    reply.q.qname,
                    QTYPE[reply.q.qtype],
                    ",".join([QTYPE[a.rtype] for a in reply.rr])))
        self.log_data(reply)

    def log_truncated(self,handler,reply):
        self.send_log_event("%sTruncated Reply: [%s:%d] (%s) / '%s' (%s) / RRs: %s" % (
                    self.log_prefix(handler),
                    handler.client_address[0],
                    handler.client_address[1],
                    handler.protocol,
                    reply.q.qname,
                    QTYPE[reply.q.qtype],
                    ",".join([QTYPE[a.rtype] for a in reply.rr])))
        self.log_data(reply)

    def log_error(self,handler,e):
        self.send_log_event("%sInvalid Request: [%s:%d] (%s) :: %s" % (
                    self.log_prefix(handler),
                    handler.client_address[0],
                    handler.client_address[1],
                    handler.protocol,
                    e))

    def log_data(self,dnsobj):
        self.send_log_event("\n" + dnsobj.toZone("    ") + "\n")


class InterceptResolver(BaseResolver):

    """
        Intercepting resolver 
        
        Proxy requests to upstream server optionally intercepting requests
        matching local records
    """

    def __init__(self,address,port,ttl, status_ctrl, main_frame):
        """
            address/port    - upstream server
            ttl             - default ttl for intercept records
        """
        self.address = address
        self.port = port
        self.ttl = parse_time(ttl)
        self.status_ctrl = status_ctrl
        self.main_frame = main_frame

    def resolve(self,request,handler):
        reply = request.reply()
        qname = request.q.qname
        qtype = QTYPE[request.q.qtype]
        if qname.matchGlob("api-*padsv.gungho.jp."):
            config = wx.ConfigBase.Get()
            host = config.Read("host") or socket.gethostbyname(socket.gethostname())
            reply.add_answer(RR(qname,QTYPE.A,rdata=A(host)))
            evt = custom_events.wxStatusEvent(message="Got DNS Request")
            wx.PostEvent(self.status_ctrl,evt)
            evt = custom_events.wxDNSEvent(message=str(qname)[:-1])
            wx.PostEvent(self.main_frame,evt)
            time.sleep(0.5) # we need to sleep until the proxy is up, half a second should do it...
        # Otherwise proxy
        if not reply.rr:
            if handler.protocol == 'udp':
                proxy_r = request.send(self.address,self.port)
            else:
                proxy_r = request.send(self.address,self.port,tcp=True)
            reply = DNSRecord.parse(proxy_r)
        return reply

def serveDNS(logger, status_ctrl, main_frame):
    
    resolver = InterceptResolver('8.8.8.8',
                                 53,
                                 '60s',
                                 status_ctrl,
                                 main_frame)
    
    DNSHandler.log = { 
        'log_request',      # DNS Request
        'log_reply',        # DNS Response
        'log_truncated',    # Truncated
        'log_error',        # Decoding error
    }

    config = wx.ConfigBase.Get()
    host = config.Read("host") or socket.gethostbyname(socket.gethostname())
    dnsport = config.Read("dnsport") or "53"
    try:
        udp_server = DNSServer(resolver,
                           port=int(dnsport),
                           address=host,
                           logger=logger)
    except Exception as e:
        evt = custom_events.wxStatusEvent(message='Error starting DNS proxy: %s' % e)
        wx.PostEvent(status_ctrl,evt)
        return

    udp_server.start_thread()

    evt = custom_events.wxStatusEvent(message="proxy started")            
    wx.PostEvent(status_ctrl,evt)

    try:
        while udp_server.isAlive():
            time.sleep(1)
    except KeyboardInterrupt:
        sys.exit()
