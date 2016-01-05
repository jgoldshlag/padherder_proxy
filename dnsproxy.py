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
		self.send_log_event("\n" + dnsobj.toZone("	  ") + "\n")


class InterceptResolver(BaseResolver):

	"""
		Intercepting resolver 
		
		Proxy requests to upstream server optionally intercepting requests
		matching local records
	"""

	def __init__(self,address,port,ttl, status_ctrl):
		"""
			address/port	- upstream server
			ttl				- default ttl for intercept records
		"""
		self.address = address
		self.port = port
		self.ttl = parse_time(ttl)
		self.status_ctrl = status_ctrl

	def resolve(self,request,handler):
		reply = request.reply()
		qname = request.q.qname
		qtype = QTYPE[request.q.qtype]
		if qname.matchGlob("api-*padsv.gungho.jp."):
			reply.add_answer(RR(qname,QTYPE.A,rdata=A(socket.gethostbyname(socket.gethostname()))))
			evt = custom_events.wxStatusEvent(message="Got DNS Request")            
			wx.PostEvent(self.status_ctrl,evt)
		# Otherwise proxy
		if not reply.rr:
			if handler.protocol == 'udp':
				proxy_r = request.send(self.address,self.port)
			else:
				proxy_r = request.send(self.address,self.port,tcp=True)
			reply = DNSRecord.parse(proxy_r)
		return reply

def serveDNS(logger, status_ctrl):
	
	evt = custom_events.wxStatusEvent(message="proxy started")            
	wx.PostEvent(status_ctrl,evt)
	resolver = InterceptResolver('8.8.8.8',
								 53,
								 '60s',
								 status_ctrl)
	
	DNSHandler.log = { 
		'log_request',		# DNS Request
		'log_reply',		# DNS Response
		'log_truncated',	# Truncated
		'log_error',		# Decoding error
	}

	udp_server = DNSServer(resolver,
						   port=53,
						   address=socket.gethostbyname(socket.gethostname()),
						   logger=logger)
	udp_server.start_thread()

	try:
		while udp_server.isAlive():
			time.sleep(1)
	except KeyboardInterrupt:
		sys.exit()