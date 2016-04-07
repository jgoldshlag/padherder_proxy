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

__version__ = '0.1'

API_ENDPOINT = 'https://www.padherder.com/user-api'
URL_MONSTER_DATA = 'https://www.padherder.com/api/monsters/'
URL_ACTIVE_SKILLS = 'https://www.padherder.com/api/active_skills/'
URL_USER_DETAILS = '%s/user/%%s/' % (API_ENDPOINT)
URL_USER_PROFILE = '%s/profile/%%s/' % (API_ENDPOINT)
URL_MONSTER_CREATE = '%s/monster/' % (API_ENDPOINT)


def xp_at_level(xp_curve, level):
    curve = XP_TABLES.get(xp_curve)
    if level > len(curve) - 1:
        return curve[-1]
    else:
        return curve[level - 1]

headers = {
    'accept': 'application/json',
    'user-agent': 'ts-sync %s' % (__version__),
}


def we_are_frozen():
    """Returns whether we are frozen via py2exe.
    This will affect how we find out where we are located."""

    return hasattr(sys, "frozen")

def module_path():
    """ This will get us the program's directory,
    even if we are frozen using py2exe"""

    if we_are_frozen():
        return os.path.dirname(unicode(sys.executable, sys.getfilesystemencoding()))

    return os.path.dirname(unicode(__file__, sys.getfilesystemencoding()))

def get_cached_data(session, cache_time, cache_path, url):
    cache_old = time.time() - (cache_time * 60 * 60)
    if os.path.exists(cache_path) and os.stat(cache_path).st_mtime > cache_old:
        # Use cached data
        ret = cPickle.load(open(cache_path, 'rb'))
    else:
        # Retrieve API data
        sys.stdout.flush()
        
        r = session.get(url)
        if r.status_code != requests.codes.ok:
            print 'failed: %s' % (r.status_code)
            return
        
        ret = json.loads(r.content)
        
        # Cache it
        cPickle.dump(ret, open(cache_path, 'wb'))
    return ret

#{"id": 6478849, "url": "https://www.padherder.com/user-api/monster/6478849/", "pad_id": 85462, "monster": 2516, "note": "", "priority": 1, "current_xp": 656, "current_skill": 1, "current_awakening": 0, "target_level": 99, "target_evolution": null, "plus_hp": 0, "plus_atk": 0, "plus_rcv": 1, "latent1": 0, "latent2": 0, "latent3": 0, "latent4": 0, "latent5": 0}

LATENT_BIT_TO_PH_ID = {
2: 1, # +hp
4: 2, # +atk
6: 3, # +rcv ????
8: 4, # move time
10: 5, # auto-heal
12: 6, # fire resist
14: 7, # water resist
16: 8, # green resist
18: 9, # dark resist
20: 10, # light resist
22: 11, # skill block resist
}

def get_latents(num):
    num = num >> 3
    latents = []
    while num > 0:
        l = num & 31
        num = num >> 5
        if not l in LATENT_BIT_TO_PH_ID:
            print "Unknown latent %d" % l
            continue
        latents.append(LATENT_BIT_TO_PH_ID[l])
    
    ret = {}
    for i in range(5):
        if i < len(latents):
            ret[u"latent%d" % (i+1)] = latents[i]
        else:
            ret[u"latent%d" % (i+1)] = 0
    return ret

#{u'priority': 3, u'plus_rcv': 1, u'monster': 1223, u'current_skill': 1, u'url': u'https://www.padherder.com/user-api/monster/6497838/', u'latent1': 1, u'latent2': 3, u'note': u'For A Freyja', u'plus_hp': 0, u'latent3': 8, u'plus_atk': 0, u'current_awakening': 0, u'latent4': 4, u'pad_id': 85628, u'current_xp': 0, u'latent5': 5, u'target_level': 2, u'id': 6497838, u'target_evolution': None}

class SyncRecord:
    def __init__(self, operation, base_data, data=None, url=None):
        self.operation = operation
        self.data = data
        self.url = url
        self.base_data = base_data
        self.action = SYNC_ACTION_ALLOW
        
    def run(self, session):
        verb = ""
        if self.operation == SYNC_ADD:
            r = session.post(URL_MONSTER_CREATE, self.data)
            if r.status_code == requests.codes.ok or r.status_code == 201:
                return 'Created monster %s: %s' % (self.base_data['name'], ', '.join(k for k in self.data.keys() if k != 'monster'))
            else:
                return 'Failed creating monster %s: %s %s' % (self.base_data['name'], r.status_code, r.content)
        elif self.operation == SYNC_UPDATE:
            r = session.patch(self.url, self.data)
            if r.status_code == requests.codes.ok:
                return 'Updated monster %s: %s' % (self.base_data['name'], ', '.join(k for k in self.data.keys() if k != 'monster'))
            else:
                return 'Failed updating monster %s: %s %s' % (self.base_data['name'], r.status_code, r.content)
        elif self.operation == SYNC_UPDATE_MATERIAL:
            r = session.patch(self.url, dict(count=self.data['count']))
            if r.status_code == requests.codes.ok or r.status_code == 201:
                return 'Updated material %s from %d to %d' % (self.base_data['name'], self.data['old_count'], self.data['count'])
            else:
                return 'Failed updating material %s: %s %s' % (self.base_data['name'], r.status_code, r.content)
        elif self.operation == SYNC_DELETE:
            r = session.delete(self.url)
            if r.status_code == 204:
                return 'Removed monster %s' % (self.base_data['name'])
            else:
                return 'Failed to remove monster %s' % (self.base_data['name'])
        elif self.operation == SYNC_UPDATE_RANK:
            r = session.patch(self.url, dict(rank=self.base_data))
            if r.status_code == requests.codes.ok:
                return 'Updated rank'
            else:
                return 'Failed updating rank'
        else:
            return "Internal error: unknown operation"
        

def add_status_msg(msg, status_ctrl):
    if status_ctrl:
        evt = custom_events.wxStatusEvent(message=msg)            
        wx.PostEvent(status_ctrl, evt)
    else:
        print msg

def do_sync(raw_captured_data, status_ctrl, region, simulate=False):
    try:
        sync_records = []
        config = wx.ConfigBase.Get()
        session = requests.Session()
        session.auth = (config.Read("username"), config.Read("password"))
        #session.verify = 'cacert.pem'
        session.headers = headers
        # Limit the session to a single concurrent connection
        session.mount('http://', requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=1))
        session.mount('https://', requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=1))

        raw_active_skills = get_cached_data(session, 8, os.path.join(module_path(), 'active_skills.pickle'), URL_ACTIVE_SKILLS)
        max_skill = {}
        # build a map of active skill name to max skill
        for skill in raw_active_skills:
            max_skill[skill['name']] = skill['max_cooldown'] - skill['min_cooldown']
        
        raw_monster_data = get_cached_data(session, 8, os.path.join(module_path(), 'monster_data.pickle'), URL_MONSTER_DATA)
        # Build monster data map and us->jp mapping
        us_to_jp_map = {}
        monster_data = {}
        for monster in raw_monster_data:
            if region != 'JP' and 'us_id' in monster:
                us_to_jp_map[monster['us_id']] = monster['id']
            if monster['active_skill'] in max_skill:
                monster['max_skill'] = max_skill[monster['active_skill']]
            monster_data[monster['id']] = monster
        add_status_msg("Downloaded full monster data", status_ctrl)
        
        
        r = session.get(URL_USER_DETAILS % (session.auth[0]))
        fake_r = r
        if r.status_code != requests.codes.ok:
            print 'failed: %s' % (r.status_code)
            return
        
        raw_user_data = json.loads(r.content)
        existing_monsters = {}
        unknown_pad_id_monsters = {}
        for monster in raw_user_data['monsters']:
            if monster['pad_id'] == 0:
                unknown_pad_id_monsters[monster['id']] = monster
            else:
                existing_monsters[monster['pad_id']] = monster
                
        material_map = {}
        for material in raw_user_data['materials']:
            material_map[material['monster']] = material

        add_status_msg("Downloaded current padherder box", status_ctrl)
        captured_data = json.loads(raw_captured_data)
        
        material_counts = {}
        for mon_array in captured_data['card']:
            jp_id = us_to_jp_map.get(mon_array[5], mon_array[5])
            # Update material counts
            if jp_id in material_map:
                material_counts[jp_id] = material_counts.get(jp_id, 0) + 1
                
            if not jp_id in monster_data:
                if mon_array[0] in existing_monsters:
                    del existing_monsters[mon_array[0]]
                add_status_msg('Got monster in box that is not in padherder: id = %d' % (jp_id), status_ctrl)
                continue
                
            base_data = monster_data[jp_id]
                
            if base_data['type'] in (0, 12, 14):
                continue

            # Cap card XP to monster's max XP
            mon_array[1] = min(mon_array[1], xp_at_level(base_data['xp_curve'], base_data['max_level']))
            # Cap card awakening to monster's max awoken level
            mon_array[9] = min(mon_array[9], len(base_data['awoken_skills']))
            # cap skill to monster's max skill
            if 'max_skill' in base_data:
                mon_array[3] = min(mon_array[3], base_data['max_skill'] + 1)
            
            latents = get_latents(mon_array[10])
            
            if mon_array[0] in existing_monsters:
                existing_data = existing_monsters.get(mon_array[0])
                if mon_array[1] != existing_data['current_xp'] or \
                   mon_array[3] != existing_data['current_skill'] or \
                   jp_id != existing_data['monster'] or \
                   mon_array[6] != existing_data['plus_hp'] or \
                   mon_array[7] != existing_data['plus_atk'] or \
                   mon_array[8] != existing_data['plus_rcv'] or \
                   mon_array[9] != existing_data['current_awakening'] or \
                   len(latents.viewitems() - existing_data.viewitems()) > 0:
                    update_data = {}
                    update_data['monster'] = jp_id
                    if mon_array[1] != existing_data['current_xp']:
                        update_data['current_xp'] = mon_array[1]
                    if mon_array[3] != existing_data['current_skill']:
                        update_data['current_skill'] = mon_array[3]
                    if mon_array[5] != existing_data['monster']:
                        update_data['current_skill'] = mon_array[3]
                        update_data['current_xp'] = mon_array[1]
                        update_data['current_awakening'] = mon_array[9]
                    if mon_array[6] != existing_data['plus_hp']:
                        update_data['plus_hp'] = mon_array[6]
                    if mon_array[7] != existing_data['plus_atk']:
                        update_data['plus_atk'] = mon_array[7]
                    if mon_array[8] != existing_data['plus_rcv']:
                        update_data['plus_rcv'] = mon_array[8]
                    if mon_array[9] != existing_data['current_awakening']:
                        update_data['current_awakening'] = mon_array[9]
                    if len(latents.viewitems() - existing_data.viewitems()) > 0:
                        update_data.update(latents)
                    
                    sync_records.append(SyncRecord(SYNC_UPDATE, base_data, update_data, existing_data['url']))
                    
                del existing_monsters[mon_array[0]]
            else:
                # first, we need to try matching against the non-id monsters
                found_id = None
                mon_url = None
                for mon_id, mon in unknown_pad_id_monsters.items():
                    if mon['monster'] == jp_id:
                        found_id = mon_id
                        mon_url = mon['url']
                        break
                update_data = {'monster': jp_id, 'pad_id': mon_array[0], 'current_xp': mon_array[1], 'current_skill': mon_array[3], 'plus_hp': mon_array[6], 'plus_atk': mon_array[7], 'plus_rcv': mon_array[8], 'current_awakening': mon_array[9]}
                update_data.update(latents)
                if found_id is not None:
                    del unknown_pad_id_monsters[found_id]
                    
                    sync_records.append(SyncRecord(SYNC_UPDATE, base_data, update_data, mon_url))
                else:
                    sync_records.append(SyncRecord(SYNC_ADD, base_data, update_data, None))
        
        for mon in existing_monsters.values():
            base_data = monster_data[mon['monster']]
            sync_records.append(SyncRecord(SYNC_DELETE, base_data, None, mon['url']))
        
        # Maybe update materials
        for monster_id, material in material_map.items():
            new_count = material_counts.get(monster_id, 0)
            if new_count != material['count']:
                sync_records.append(SyncRecord(SYNC_UPDATE_MATERIAL, monster_data[monster_id], dict(count=new_count, old_count=material['count']), material['url']))

        # Maybe update rank
        if captured_data['lv'] != raw_user_data['profile']['rank']:
            sync_records.append(SyncRecord(SYNC_UPDATE_RANK, captured_data['lv'], url=URL_USER_PROFILE % raw_user_data['profile']['id']))


        # and run the syncs
        for rec in sync_records:
            add_status_msg(rec.run(session), status_ctrl)
        
        add_status_msg('Done', status_ctrl)
    except:
        add_status_msg('Error doing sync:\n' + traceback.format_exc() + '\n\nPlease report this error on github', status_ctrl)

            
def find_unknown_xp_curves(config):
    session = requests.Session()
    session.auth = (config.Read("username"), config.Read("password"))
    #session.verify = 'cacert.pem'
    session.headers = headers
    # Limit the session to a single concurrent connection
    session.mount('http://', requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=1))
    session.mount('https://', requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=1))

    raw_monster_data = get_cached_data(session, 8, os.path.join(module_path(), 'monster_data.pickle'), URL_MONSTER_DATA)
    # Build monster data map and us->jp mapping
    us_to_jp_map = {}
    monster_data = {}
    for monster in raw_monster_data:
        if monster['xp_curve'] not in XP_TABLES:
            print monster

MONSTER_IDS = {
    # Shinra Bansho
     669: dict(us_id=934, pdx_id=934),
     670: dict(us_id=935, pdx_id=935),
     671: dict(us_id=1049, pdx_id=1049),
     672: dict(us_id=1050, pdx_id=1050),
     673: dict(us_id=1051, pdx_id=1051),
     674: dict(us_id=1052, pdx_id=1052),
     675: dict(us_id=1053, pdx_id=1053),
     676: dict(us_id=1054, pdx_id=1054),
     677: dict(us_id=1055, pdx_id=1055),
     678: dict(us_id=1056, pdx_id=1056),
     679: dict(us_id=1057, pdx_id=1057),
     680: dict(us_id=1058, pdx_id=1058),

    # BAO collab 1, ugh
     924: dict(us_id=669, pdx_id=669), # BAO Joker
     925: dict(us_id=670, pdx_id=670), # BAO Joker+A. Blossom
     926: dict(us_id=671, pdx_id=671), # BAO Catwoman
     927: dict(us_id=672, pdx_id=672), # BAO Catwoman+C. Claw
     928: dict(us_id=673, pdx_id=673), # BAO Robin
     929: dict(us_id=674, pdx_id=674), # BAO Robin+E. Stick
     930: dict(us_id=675, pdx_id=675), # BAO Batman+S. Gloves
     931: dict(us_id=676, pdx_id=676), # BAO Batman+S. Gloves Act
     932: dict(us_id=677, pdx_id=677), # BAO Batman+Batarang
     933: dict(us_id=678, pdx_id=678), # BAO Batman+Remote Claw
     934: dict(us_id=679, pdx_id=679), # BAO Batman+Batwing
     935: dict(us_id=680, pdx_id=680), # BAO Batman+BW Attack

    # BAO collab 2
    1049: dict(us_id=924, pdx_id=924),
    1050: dict(us_id=925, pdx_id=925),
    1051: dict(us_id=926, pdx_id=926),
    1052: dict(us_id=927, pdx_id=927),
    1053: dict(us_id=928, pdx_id=928),
    1054: dict(us_id=929, pdx_id=929),
    1055: dict(us_id=930, pdx_id=930),
    1056: dict(us_id=931, pdx_id=931),
    1057: dict(us_id=932, pdx_id=932),
    1058: dict(us_id=933, pdx_id=933),

    # Old PAD Wiki stuff
    # 1924: dict(us_id=924, pdx_id=924),
    # 1925: dict(us_id=925, pdx_id=925),
    # 1926: dict(us_id=926, pdx_id=926),
    # 1927: dict(us_id=927, pdx_id=927),
    # 1928: dict(us_id=928, pdx_id=928),
    # 1929: dict(us_id=929, pdx_id=929),
    # 1930: dict(us_id=930, pdx_id=930),
    # 1931: dict(us_id=931, pdx_id=931),
    # 1932: dict(us_id=932, pdx_id=932),
}

PH_TO_PDX = {k: v['pdx_id'] for k, v in MONSTER_IDS.items() }
PDX_IDS = {v['pdx_id']: k for k, v in MONSTER_IDS.items() }
US_IDS = {v['us_id']: k for k, v in MONSTER_IDS.items() }

if __name__ == '__main__':
    app = wx.App(False)
    config = wx.Config("padherder_proxy_testing")
    wx.ConfigBase.Set(config)
    
    find_unknown_xp_curves(config)
    
    sys.exit(1)
    
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
        
    
    print us_to_jp_map
    print len(us_to_jp_map)
    print US_IDS
    if us_to_jp_map == US_IDS:
        print "equal"
    
    f = open(sys.argv[1], "r")
    contents = f.read()
    f.close()
    
    
    config.Write("username", sys.argv[2])
    config.Write("password", sys.argv[3])

    do_sync(contents, None, "NA", False)
