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
import wx.lib.hyperlink as hl
import wx.grid
from urlparse import urljoin
import traceback
from distutils.version import LooseVersion

import dnsproxy
import padherder_sync
import custom_events
from constants import *
from mail_parser import *
import datetime

PH_PROXY_VERSION = "2.4"

parse_host_header = re.compile(r"^(?P<host>[^:]+|\[.+\])(?::(?P<port>\d+))?$")

class PadMaster(flow.FlowMaster):
    def __init__(self, server, main_window, region):
        flow.FlowMaster.__init__(self, server, flow.State())
        self.status_ctrl = main_window.main_tab
        self.mail_tab = main_window.mail_tab
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
                
                cap = open('captured_data.txt', 'w')
                cap.write(content)
                cap.close()
                thread.start_new_thread(padherder_sync.do_sync, (content, self.status_ctrl, self.region))
            elif f.request.path.startswith('/api.php?action=get_user_mail'):
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
                
                cap = open('captured_mail.txt', 'w')
                cap.write(content)
                cap.close()
                
                mails = parse_mail(content)
                mails.reverse()
                evt = custom_events.wxMailEvent(mails=mails)
                wx.PostEvent(self.mail_tab, evt)
                evt = custom_events.wxStatusEvent(message="Got mail data, processing...")            
                wx.PostEvent(self.status_ctrl,evt)
            else:
                config = wx.ConfigBase.Get()
                actions = config.Read("customcapture")
                if actions != "" and actions != None:
                    for act in actions.split(','):
                        act = act.strip()
                        if f.request.path.startswith('/api.php?action=%s' % act):
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
                            
                            cap = open('captured_%s.txt' % act, 'w')
                            cap.write(content)
                            cap.close()
                            
                            evt = custom_events.wxStatusEvent(message="Got custom capture %s" % act)            
                            wx.PostEvent(self.status_ctrl,evt)
                            
                
        return f

def serve_app(master):
    master.run()

def run_proxy(master):
    master.run()

class MyGridTable(wx.grid.PyGridTableBase):
    def __init__(self, sync_records):
        self.sync_records = sync_records
    
    def GetNumberRows(self):
        return len(self.sync_records)

    def GetNumberCols(self):
        """Return the number of columns in the grid"""
        return 3

    def IsEmptyCell(self, row, col):
        """Return True if the cell is empty"""
        return False

    def GetTypeName(self, row, col):
        """Return the name of the data type of the value in the cell"""
        return None

    def GetValue(self, row, col):
        rec = self.sync_records[row]
        if col == 0:
            if rec.operation == SYNC_ADD:
                return "Add"
            elif rec.operation == SYNC_UPDATE:
                return "Update"
            elif rec.operation == SYNC_UPDATE_MATERIAL:
                return "Material"
            elif rec.operation == SYNC_DELETE:
                return "Delete"
            else:
                return "UNKNOWN"
        elif col == 1:
            return rec.base_data['name']
        elif col == 2:
            return ""
        else:
            return "UNKNOWN"

    def SetValue(self, row, col, value):
        rec = self.sync_records[row]
        rec.action = value
    
    def GetColLabelValue(self, col):
        if col == 0:
            return "Operation"
        elif col == 1:
            return "Name"
        elif col == 2:
            return "Action"
            
    def GetAttr(self, row, col, someExtraParameter ):
        if col != 2:
            attr = wx.grid.wxGridCellAttr()
            attr.SetReadOnly( 1 )
            return attr
        return None
        
class MailGridTable(wx.grid.PyGridTableBase):
    def __init__(self, mails, main_tab):
        wx.grid.PyGridTableBase.__init__(self)
        self.mails = mails
        self.main_tab = main_tab
    
    def GetNumberRows(self):
        return len(self.mails)

    def GetNumberCols(self):
        """Return the number of columns in the grid"""
        return 6

    def IsEmptyCell(self, row, col):
        """Return True if the cell is empty"""
        return False

    def GetValue(self, row, col):
        mail = self.mails[row]
        if col == 0:
            return MAIL_TYPE_MAP[mail.type]
        elif col == 1:
            return mail.get_bonus_contents(self.main_tab.monster_data, self.main_tab.us_to_jp_map)
        elif col == 2:
            if mail.offered == 0:
                return "No"
            else:
                return "Yes"
        elif col == 3:
            if mail.from_id == "0":
                return "Game Admin"
            else:
                return "UserID: %s" % mail.from_id
        elif col == 4:
            return mail.subject
        elif col == 5:
            now = datetime.datetime.now(Pacific)
            diff = now - mail.date
            if diff.days > 0:
                return "%dd" % diff.days
            else:
                return "%dh" % int(diff.seconds / (60 * 60))
        else:
            return "UNKNOWN"

    def SetValue(self, row, col, value):
        pass
    
    def GetColLabelValue(self, col):
        return ['Type', 'Contents', 'Open', 'From', 'Subject', 'Time'][col]
        
        
    def GetAttr(self, row, col, someExtraParameter ):
        attr = wx.grid.GridCellAttr()
        attr.SetReadOnly(True)
        return attr

class MainTab(wx.Panel):
    def __init__(self, parent):
        self.us_to_jp_map = {}
        self.monster_data = {}
        wx.Panel.__init__(self, parent)
        grid = wx.GridBagSizer(hgap=5, vgap=10)

        config = wx.ConfigBase.Get()
        host = config.Read("host") or socket.gethostbyname(socket.gethostname())

        start_instructions = wx.StaticText(self, label="Just the first time, you need to add the HTTPS certificate to your iOS/Android device. To do this, go to your wifi settings and set up a manual HTTP proxy. Set the server to '%s' and the port to 8080. Then visit http://mitm.it in Safari/Chrome, click the link for your device, and install the configuration profile when asked. After this is done, turn off the HTTP proxy." % host)
        start_instructions.Wrap(580)
        grid.Add(start_instructions, pos=(0,0))
        
        dns_instructions = wx.StaticText(self, label="To synchronize your box with padherder, enter your padherder username and password in Settings. Then go to your wifi settings and change your DNS server to '%s'. Then press the home button. If you switch to the DNS Proxy Log tab, you should see a bunch of log lines. Make sure Puzzle and Dragons is completely closed, and re-open it. Once you get in game, close PAD completely again and restore your DNS settings." % host)
        dns_instructions.Wrap(580)
        grid.Add(dns_instructions, pos=(1,0))
        
        status_label = wx.StaticText(self, label="Status:")
        grid.Add(status_label, pos=(2,0))
        
        self.status_ctrl = wx.TextCtrl(self, wx.ID_ANY, size=(400,300),
                          style = wx.TE_MULTILINE|wx.TE_READONLY)
        self.Bind(custom_events.EVT_STATUS_EVENT, self.onStatusEvent)
        if not config.Read("username"):
            self.status_ctrl.AppendText("You need to set your padherder username in Settings\n")
        if not config.Read("password"):
            self.status_ctrl.AppendText("You need to set your padherder password in Settings\n")
        
        grid.Add(self.status_ctrl, pos=(3,0), span=(1,2))
        
        if is_out_of_date(self):
            updateCtrl = hl.HyperLinkCtrl(self, wx.ID_ANY, label="An updated version is available", URL="https://github.com/jgoldshlag/padherder_proxy")
            grid.Add(updateCtrl, pos=(4,0), span=(1,2))
        
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
        host = config.Read("host") or socket.gethostbyname(socket.gethostname())
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

        lblHost = wx.StaticText(self, label="IP Address to bind to:")
        grid.Add(lblHost, pos=(2,0))
        self.editHost = wx.TextCtrl(self, value=config.Read("host"), size=(140,-1))
        self.Bind(wx.EVT_TEXT, self.onHostChange, self.editHost)
        grid.Add(self.editHost, pos=(2,1))
        
        lblHostHelp = wx.StaticText(self, label="Leave blank, unless your computer has multiple IPs. Restart app after changing this")
        lblHostHelp.Wrap(580)
        grid.Add(lblHostHelp, pos=(3,0), span=(1,2))
        
        lblDNSPort = wx.StaticText(self, label="Port for DNS Proxy:")
        grid.Add(lblDNSPort, pos=(4,0))
        self.editDNSPort = wx.TextCtrl(self, value=config.Read("dnsport"), size=(140,-1))
        self.Bind(wx.EVT_TEXT, self.onDNSPortChange, self.editDNSPort)
        grid.Add(self.editDNSPort, pos=(4,1))

        export = config.Read("dnsport") or "<padproxydnsport>"
        lblDNSPortHelp = wx.StaticText(self, label="Leave blank, unless you need to bind the DNS Proxy to a different port (ie: for non-root use on a *nix system.) You will need to have a proxy to pass DNS requests from UDP port 53 to this port (ex: sudo dnsmasq -R -a=%s -S=%s#%s). Restart app after changing this." % (host, host, export))
        lblDNSPortHelp.Wrap(580)
        grid.Add(lblDNSPortHelp, pos=(5,0), span=(1,2))

        lblHTTPSPort = wx.StaticText(self, label="Port for HTTPS Proxy:")
        grid.Add(lblHTTPSPort, pos=(6,0))
        self.editHTTPSPort = wx.TextCtrl(self, value=config.Read("httpsport"), size=(140,-1))
        self.Bind(wx.EVT_TEXT, self.onHTTPSPortChange, self.editHTTPSPort)
        grid.Add(self.editHTTPSPort, pos=(6,1))

        export = config.Read("httpsport") or "<padproxyhttpsport>"
        lblHTTPSPortHelp = wx.StaticText(self, label="Leave blank, unless you need to bind the HTTPS Proxy a different port (ie: for non-root use on a *nix system.) You will need to have some way to forward TCP port 443 to the this port (ex: sudo socat TCP4-LISTEN:443,bind=%s,su=nobody,fork TCP4:%s:%s). Restart app after changing this." % (host, host, export))
        lblHTTPSPortHelp.Wrap(580)
        grid.Add(lblHTTPSPortHelp, pos=(7,0), span=(1,2))

        lblCustomCapture = wx.StaticText(self, label="Custom URLs to capture")
        grid.Add(lblCustomCapture, pos=(8,0))
        self.editCustomCapture = wx.TextCtrl(self, value=config.Read("customcapture"), size=(140,-1))
        self.Bind(wx.EVT_TEXT, self.onCustomCaptureChange, self.editCustomCapture)
        grid.Add(self.editCustomCapture, pos=(8,1))

        lblCustomCaptureHelp = wx.StaticText(self, label="Leave blank, unless you are raijinili. Comma separated list of actions to capture.")
        lblCustomCaptureHelp.Wrap(580)
        grid.Add(lblCustomCaptureHelp, pos=(9,0), span=(1,2))
        
        self.SetSizer(grid)
        
    def onUsernameChange(self, event):
        config = wx.ConfigBase.Get()
        config.Write("username", event.GetString())
        
    def onPasswordChange(self, event):
        config = wx.ConfigBase.Get()
        config.Write("password", event.GetString())
    
    def onHostChange(self, event):
        config = wx.ConfigBase.Get()
        config.Write("host", event.GetString())

    def onDNSPortChange(self, event):
        config = wx.ConfigBase.Get()
        config.Write("dnsport", event.GetString())
    
    def onHTTPSPortChange(self, event):
        config = wx.ConfigBase.Get()
        config.Write("httpsport", event.GetString())
        
    def onCustomCaptureChange(self, event):
        config = wx.ConfigBase.Get()
        config.Write("customcapture", event.GetString())

class MailTab(wx.Panel):
    def __init__(self, parent, main_tab):
        wx.Panel.__init__(self, parent)
        self.Bind(custom_events.EVT_MAIL_EVENT, self.onMailEvent)
        self.grid = wx.grid.Grid(self, wx.ID_ANY, size=(-1,-1))
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.grid, 0, wx.EXPAND)
        self.SetSizer(self.sizer)
        self.SetAutoLayout(1)
        self.sizer.Fit(self)
        self.main_tab = main_tab
        self.grid.Bind(wx.EVT_KEY_DOWN, self.onKeyDown)
        
    def onKeyDown(self, event):
        if event.ControlDown() and event.GetKeyCode() == 67:
            self.copy()
    
    def copy(self):
        if self.grid.GetSelectionBlockTopLeft() == []:
            rows = 1
            cols = 1
            iscell = True
        else:
            rows = self.grid.GetSelectionBlockBottomRight()[0][0] - self.grid.GetSelectionBlockTopLeft()[0][0] + 1
            cols = self.grid.GetSelectionBlockBottomRight()[0][1] - self.grid.GetSelectionBlockTopLeft()[0][1] + 1
            iscell = False
        # data variable contain text that must be set in the clipboard
        data = ''
        # For each cell in selected range append the cell value in the data variable
        # Tabs '\t' for cols and '\r' for rows
        for r in range(rows):
            for c in range(cols):
                if iscell:
                    data += str(self.grid.GetCellValue(self.grid.GetGridCursorRow() + r, self.grid.GetGridCursorCol() + c))
                else:
                    data += str(self.grid.GetCellValue(self.grid.GetSelectionBlockTopLeft()[0][0] + r, self.grid.GetSelectionBlockTopLeft()[0][1] + c))
                if c < cols - 1:
                    data += '\t'
            data += '\n'
        # Create text data object
        clipboard = wx.TextDataObject()
        # Set data object value
        clipboard.SetText(data)
        # Put the data in the clipboard
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(clipboard)
            wx.TheClipboard.Close()
        else:
            wx.MessageBox("Can't open the clipboard", "Error")

    def onMailEvent(self,event):
        mails = event.mails
        self.grid_table = MailGridTable(mails, self.main_tab)
        self.grid.SetTable(self.grid_table)
        self.grid.AutoSize()
        self.grid.SetRowLabelSize(40)
        self.Layout()
        event.Skip()

class MainWindow(wx.Frame):
    def __init__(self, parent, title):
        wx.Frame.__init__(self, parent, title=title, size=(750,600))
        self.Bind(wx.EVT_CLOSE, self.onClose)
        self.Bind(custom_events.EVT_DNS_EVENT, self.onDNSEvent)
        self.proxy_master = None
        self.app_master = None
        
        p = wx.Panel(self)
        nb = wx.Notebook(p)
        
        self.main_tab = MainTab(nb)
        self.dns_tab = DNSLogTab(nb)
        settings_tab = SettingsTab(nb)
        self.mail_tab = MailTab(nb, self.main_tab)
        
        nb.AddPage(self.main_tab, "Proxy")
        nb.AddPage(self.dns_tab, "DNS Proxy Log")
        nb.AddPage(settings_tab, "Settings")
        nb.AddPage(self.mail_tab, "PAD Mail")
        
        sizer = wx.BoxSizer()
        sizer.Add(nb, 1, wx.EXPAND)
        p.SetSizer(sizer)
        
        self.Show(True)

    def onClose(self, event):
        if self.app_master is not None:
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
        
        config = wx.ConfigBase.Get()
        host = config.Read("host") or socket.gethostbyname(socket.gethostname())
        httpsport = config.Read("httpsport") or "443"

        try:
            proxy_config = proxy.ProxyConfig(port=int(httpsport), host=host, mode='reverse', upstream_server=cmdline.parse_server_spec('https://%s:443/' % event.message))
            proxy_server = ProxyServer(proxy_config)
        except Exception as e:
            evt = custom_events.wxStatusEvent(message='Error starting HTTPS proxy: %s' % e)
            wx.PostEvent(self.main_tab, evt)
            return

        self.proxy_master = PadMaster(proxy_server, self, region)
        thread.start_new_thread(self.proxy_master.run, ())

def is_out_of_date(main_tab):
    session = requests.Session()
    session.headers = { 'accept': 'application/vnd.github.v3+json',
                        'user-agent': 'jgoldshlag-padherder_sync_' + PH_PROXY_VERSION,
                      }
    
    session.mount('https://', requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=1))
    try:
        r = session.get('https://api.github.com/repos/jgoldshlag/padherder_proxy/releases')
    except Exception as e:
        evt = custom_events.wxStatusEvent(message='Error checking for updates: %s' % e)
        wx.PostEvent(main_tab, evt)

    if r.status_code != requests.codes.ok:
        evt = custom_events.wxStatusEvent(message='Error checking for updates: %s %s' % (r.status_code, r.content))            
        wx.PostEvent(main_tab, evt)
    
    releases = json.loads(r.content)
    current_ver = LooseVersion(PH_PROXY_VERSION)
    for rel in releases:
        rel_version = LooseVersion(rel['tag_name'][1:])
        if rel_version > current_ver:
            return True
    
    return False
    
def main():
    app = wx.App(False)
    if len(sys.argv) >= 2 and sys.argv[1] == '-test':
        config = wx.Config("padherder_proxy_test")
        print "In test mode"
    else:
        config = wx.Config("padherder_proxy")
    wx.ConfigBase.Set(config)
    frame = MainWindow(None, "Padherder Proxy v%s" % PH_PROXY_VERSION)
    
    host = config.Read("host") or socket.gethostbyname(socket.gethostname())
    
    logger = dnsproxy.MyDNSLogger(frame.dns_tab)
    thread.start_new_thread(dnsproxy.serveDNS, (logger, frame.main_tab, frame))
    
    try:
        app_config = proxy.ProxyConfig(port=8080, host=host)
        app_server = ProxyServer(app_config)
        app_master = dump.DumpMaster(app_server, dump.Options(app_host='mitm.it', app_port=80, app=True))
        frame.app_master = app_master
        thread.start_new_thread(app_master.run, ())
    except:
        evt = custom_events.wxStatusEvent(message='Error initalizing mitm proxy:\n' + traceback.format_exc() + '\n\nYou probably put in an incorrect IP address in Settings')            
        wx.PostEvent(frame.main_tab, evt)

    app.MainLoop()
    
if __name__ == '__main__':
    main()
