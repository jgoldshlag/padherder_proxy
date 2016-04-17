import requests
import os
import time
import cPickle
import sys
import json
import wx
import custom_events
import traceback
from constants import *
from padherder_sync import *
from datetime import datetime as DT
from datetime import timedelta
from datetime import tzinfo

def first_sunday_on_or_after(dt):
    days_to_go = 6 - dt.weekday()
    if days_to_go:
        dt += timedelta(days_to_go)
    return dt

DSTSTART_2007 = DT(1, 3, 8, 2)
DSTEND_2007 = DT(1, 11, 1, 1)
ZERO = timedelta(0)
HOUR = timedelta(hours=1)

class USTimeZone(tzinfo):

    def __init__(self, hours, reprname, stdname, dstname):
        self.stdoffset = timedelta(hours=hours)
        self.reprname = reprname
        self.stdname = stdname
        self.dstname = dstname

    def __repr__(self):
        return self.reprname

    def tzname(self, dt):
        if self.dst(dt):
            return self.dstname
        else:
            return self.stdname

    def utcoffset(self, dt):
        return self.stdoffset + self.dst(dt)

    def dst(self, dt):
        if dt is None or dt.tzinfo is None:
            # An exception may be sensible here, in one or both cases.
            # It depends on how you want to treat them.  The default
            # fromutc() implementation (called by the default astimezone()
            # implementation) passes a datetime with dt.tzinfo is self.
            return ZERO
        assert dt.tzinfo is self

        dststart, dstend = DSTSTART_2007, DSTEND_2007

        start = first_sunday_on_or_after(dststart.replace(year=dt.year))
        end = first_sunday_on_or_after(dstend.replace(year=dt.year))

        # Can't compare naive to aware objects, so strip the timezone from
        # dt first.
        if start <= dt.replace(tzinfo=None) < end:
            return HOUR
        else:
            return ZERO

Pacific  = USTimeZone(-8, "Pacific",  "PST", "PDT")

class PADMail:
    def __init__(self, json):
        self.type = json['type']
        self.from_id = json['from']
        if self.from_id != 0:
            ID = str(self.from_id)
            self.from_id = ''.join(ID[x-1] for x in [1,5,9,6,3,8,2,4,7])
        else:
            self.from_id = "0"
        self.subject = json['sub']
        self.offered = json['offered']
        self.amount = json['amount']
        self.bonus_id = json['bonus_id']
        self.date = DT.strptime(json['date'], '%y%m%d%H%M%S')
        self.date = self.date.replace(tzinfo=Pacific)
    
    def get_bonus_contents(self, monster_data, us_to_jp_map):
        if self.bonus_id == 0:
            return "None"
        elif self.bonus_id == 9900:
            return "%d coins" % self.amount
        elif self.bonus_id == 9901:
            if self.amount == 1:
                return "1 magic stone"
            else:
                return "%d magic stones" % self.amount
        elif self.bonus_id == 9902:
            return "%d Pal points" % self.amount
        else:
            jp_id = us_to_jp_map.get(self.bonus_id, self.bonus_id)
            return monster_data[jp_id]['name']


def parse_mail(mail_contents):
    mail = json.loads(mail_contents)
    #print mail
    ret = []
    for msg in mail['mails']:
        # Pal pts: {"id":126887704,"from":0,"date":"160417103251","fav":0,"sub":"*Official Twitch Stream Rewards*","type":3,"offered":0,"bonus_id":9902,"amount":1000}
        ret.append(PADMail(msg))
    return ret


if __name__ == '__main__':
    app = wx.App(False)
    config = wx.Config("padherder_proxy_testing")
    wx.ConfigBase.Set(config)

    session = requests.Session()
    session.headers = headers
    # Limit the session to a single concurrent connection
    session.mount('http://', requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=1))
    session.mount('https://', requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=1))
    
    raw_monster_data = get_cached_data(session, 8, os.path.join(module_path(), 'monster_data.pickle'), URL_MONSTER_DATA)
    # Build monster data map and us->jp mapping
    us_to_jp_map = {}
    monster_data = {}
    for monster in raw_monster_data:
        if 'us_id' in monster:
            us_to_jp_map[monster['us_id']] = monster['id']
        monster_data[monster['id']] = monster

    f = open('captured_mail.txt', "r")
    contents = f.read()
    f.close()

    mails = parse_mail(contents)
    
    for mail in mails:
        print mail.get_bonus_contents(monster_data, us_to_jp_map)