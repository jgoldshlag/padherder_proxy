#!/usr/bin/python


import json
import os
import requests
import sys
import time
import cPickle
import select, socket, SocketServer, thread, urlparse, cStringIO
import signal
import re
from libmproxy import controller, proxy, flow, dump, cmdline, contentviews
from libmproxy.proxy.server import ProxyServer
import wx
from urlparse import urljoin

import dnsproxy
import padherder_sync
import custom_events

parse_host_header = re.compile(r"^(?P<host>[^:]+|\[.+\])(?::(?P<port>\d+))?$")

class PadMaster(flow.FlowMaster):
	def __init__(self, server, status_ctrl, region):
		flow.FlowMaster.__init__(self, server, flow.State())
		self.status_ctrl = status_ctrl
		self.region = region
		#self.start_app('mitm.it', 80)


	def run(self):
		try:
			return flow.FlowMaster.run(self)
		except KeyboardInterrupt:
			self.shutdown()

	def handle_request(self, f):
		if f.client_conn.ssl_established:
			f.request.scheme = "https"
			sni = f.client_conn.connection.get_servername()
			port = 443
		else:
			f.request.scheme = "http"
			sni = None
			port = 80

		host_header = f.request.pretty_host
		m = parse_host_header.match(host_header)
		if m:
			host_header = m.group("host").strip("[]")
			if m.group("port"):
				port = int(m.group("port"))

		f.request.host = sni or host_header
		f.request.port = port
		
		evt = custom_events.wxStatusEvent(message="Got HTTPS request, forwarding")            
		wx.PostEvent(self.status_ctrl,evt)
		
		flow.FlowMaster.handle_request(self, f)
		if f:
			f.reply()
		return f
		
	def handle_response(self, f):
		flow.FlowMaster.handle_response(self, f)
		if f:
			f.reply()
			if f.request.path.startswith('/api.php?action=get_player_data'):
				evt = custom_events.wxStatusEvent(message="Got box data, processing...")            
				wx.PostEvent(self.status_ctrl,evt)
				resp = f.response.content
				type, lines = contentviews.get_content_view(
					contentviews.get("Raw"),
					f.response.content,
					headers=f.response.headers)

				def colorful(line):
					for (style, text) in line:
						yield text
						
				content = u"\r\n".join(
					u"".join(colorful(line)) for line in lines
				)
				thread.start_new_thread(padherder_sync.do_sync, (content, self.status_ctrl, self.region))
		return f

def serve_app(master):
	master.run()

def run_proxy(master):
	master.run()

class MainTab(wx.Panel):
	def __init__(self, parent):
		wx.Panel.__init__(self, parent)
		grid = wx.GridBagSizer(hgap=5, vgap=10)

		ip = socket.gethostbyname(socket.gethostname())
		start_instructions = wx.StaticText(self, label="Just the first time, you need to add the HTTPS certificate to your iOS device.\nTo do this, go to your wifi settings and set up a manual HTTP proxy.\nSet the server to '%s' and the port to 8080. Then visit http://mitm.it in Safari,\nclick the iOS link, and install the configuration profile when asked.\nAfter this is done, turn off the HTTP proxy." % ip)
		grid.Add(start_instructions, pos=(0,0))
		
		dns_instructions = wx.StaticText(self, label="To synchronize your box with padherder, enter your padherder username and password in Settings.\nThen go to your wifi settings and change your DNS server to '%s'. Then press the home button.\nIf you switch to the DNS Proxy Log tab, you should see a bunch of log lines.\nMake sure Puzzle and Dragons is completely closed, and re-open it.\nOnce you get in game, close PAD completely again and restore your DNS settings." % ip)
		grid.Add(dns_instructions, pos=(1,0))
		
		status_label = wx.StaticText(self, label="Status:")
		grid.Add(status_label, pos=(2,0))
		
		self.status_ctrl = wx.TextCtrl(self, wx.ID_ANY, size=(400,300),
						  style = wx.TE_MULTILINE|wx.TE_READONLY)
		self.Bind(custom_events.EVT_STATUS_EVENT, self.onStatusEvent)
		
		grid.Add(self.status_ctrl, pos=(3,0), span=(1,2))
		
		self.SetSizer(grid)
		
	def onStatusEvent(self,event):
		msg = event.message.strip("\r")+"\n"
		self.status_ctrl.AppendText(msg)
		event.Skip()

class DNSLogTab(wx.Panel):
	def __init__(self, parent):
		wx.Panel.__init__(self, parent)
		self.Bind(custom_events.EVT_WX_LOG_EVENT, self.onLogEvent)
		self.log = wx.TextCtrl(self, wx.ID_ANY, size=(-1,500),
						  style = wx.TE_MULTILINE|wx.TE_READONLY)
		self.sizer = wx.BoxSizer(wx.VERTICAL)
		self.sizer.Add(self.log, 0, wx.EXPAND)
		self.SetSizer(self.sizer)
		self.SetAutoLayout(1)
		self.sizer.Fit(self)

	def onLogEvent(self,event):
		msg = event.message.strip("\r")+"\n"
		self.log.AppendText(msg)
		event.Skip()

		
class SettingsTab(wx.Panel):
	def __init__(self, parent):
		wx.Panel.__init__(self, parent)
		
		config = wx.ConfigBase.Get()
		grid = wx.GridBagSizer(hgap=5, vgap=5)
		
		lblUsername = wx.StaticText(self, label="Padherder Username:")
		grid.Add(lblUsername, pos=(0,0))
		self.editUsername = wx.TextCtrl(self, value=config.Read("username"), size=(140,-1))
		self.Bind(wx.EVT_TEXT, self.onUsernameChange, self.editUsername)
		grid.Add(self.editUsername, pos=(0,1))

		lblUsername = wx.StaticText(self, label="Padherder Password:")
		grid.Add(lblUsername, pos=(1,0))
		self.editPassword = wx.TextCtrl(self, value=config.Read("password"), size=(140,-1), style=wx.TE_PASSWORD)
		self.Bind(wx.EVT_TEXT, self.onPasswordChange, self.editPassword)
		grid.Add(self.editPassword, pos=(1,1))

		self.SetSizer(grid)
		
	def onUsernameChange(self, event):
		config = wx.ConfigBase.Get()
		config.Write("username", event.GetString())
		
	def onPasswordChange(self, event):
		config = wx.ConfigBase.Get()
		config.Write("password", event.GetString())
	
class MainWindow(wx.Frame):
	def __init__(self, parent, title):
		wx.Frame.__init__(self, parent, title=title, size=(600,600))
		self.Bind(wx.EVT_CLOSE, self.onClose)
		self.Bind(custom_events.EVT_DNS_EVENT, self.onDNSEvent)
		self.proxy_master = None
		
		p = wx.Panel(self)
		nb = wx.Notebook(p)
		
		self.main_tab = MainTab(nb)
		self.dns_tab = DNSLogTab(nb)
		settings_tab = SettingsTab(nb)
		
		nb.AddPage(self.main_tab, "Proxy")
		nb.AddPage(self.dns_tab, "DNS Proxy Log")
		nb.AddPage(settings_tab, "Settings")
		
		sizer = wx.BoxSizer()
		sizer.Add(nb, 1, wx.EXPAND)
		p.SetSizer(sizer)
		
		self.Show(True)

	def onClose(self, event):
		self.app_master.shutdown()
		if self.proxy_master is not None:
			self.proxy_master.shutdown()
		self.Destroy()
	
	def onDNSEvent(self, event):
		if self.proxy_master is not None:
			self.proxy_master.shutdown()
		
		if event.message.startswith('api-na'):
			region = 'NA'
		else:
			region = 'JP'
		proxy_config = proxy.ProxyConfig(port=443, host=socket.gethostbyname(socket.gethostname()), mode='reverse', upstream_server=cmdline.parse_server_spec('https://%s:443/' % event.message))
		proxy_server = ProxyServer(proxy_config)
		self.proxy_master = PadMaster(proxy_server, self.main_tab, region)
		thread.start_new_thread(self.proxy_master.run, ())


def main():
	app = wx.App(False)
	config = wx.Config("padherder_proxy")
	wx.ConfigBase.Set(config)
	frame = MainWindow(None, "Padherder Proxy")
		
	logger = dnsproxy.MyDNSLogger(frame.dns_tab)
	thread.start_new_thread(dnsproxy.serveDNS, (logger, frame.main_tab, frame))
	
	app_config = proxy.ProxyConfig(port=8080, host=socket.gethostbyname(socket.gethostname()))
	app_server = ProxyServer(app_config)
	app_master = dump.DumpMaster(app_server, dump.Options(app_host='mitm.it', app_port=80, app=True))
	frame.app_master = app_master
	thread.start_new_thread(app_master.run, ())
	
	app.MainLoop()
	
if __name__ == '__main__':
	main()