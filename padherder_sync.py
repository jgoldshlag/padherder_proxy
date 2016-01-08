import requests
import os
import time
import cPickle
import sys
import json
import wx
import custom_events
import traceback

__version__ = '0.1'

API_ENDPOINT = 'https://www.padherder.com/user-api'
URL_MONSTER_DATA = 'https://www.padherder.com/api/monsters/'
URL_ACTIVE_SKILLS = 'https://www.padherder.com/api/active_skills/'
URL_USER_DETAILS = '%s/user/%%s/' % (API_ENDPOINT)
URL_MONSTER_CREATE = '%s/monster/' % (API_ENDPOINT)


# Horrifying XP tables, woo
XP_TABLES = {
	1000000: [0, 11, 59, 164, 337, 588, 927, 1364, 1904, 2556, 3326, 4221, 5247, 6409, 7714, 9166, 10770, 12533, 14458, 16551, 18815, 21256, 23878, 26684, 29680, 32869, 36255, 39842, 43634, 47635, 51849, 56278, 60927, 65799, 70898, 76226, 81788, 87587, 93625, 99907, 106435, 113213, 120243, 127528, 135072, 142878, 150949, 159287, 167895, 176777, 185934, 195371, 205089, 215092, 225382, 235962, 246834, 258001, 269467, 281232, 293301, 305675, 318357, 331349, 344655, 358276, 372216, 386475, 401058, 415966, 431201, 446767, 462664, 478897, 495466, 512375, 529625, 547220, 565160, 583449, 602088, 621080, 640427, 660131, 680194, 700619, 721408, 742562, 764085, 785977, 808241, 830880, 853895, 877288, 901062, 925217, 949758, 974685, 1000000],
	1500000: [0, 16, 89, 246, 505, 882, 1391, 2045, 2856, 3834, 4989, 6332, 7870, 9614, 11570, 13748, 16156, 18800, 21687, 24826, 28223, 31884, 35816, 40026, 44520, 49303, 54383, 59763, 65452, 71453, 77773, 84417, 91390, 98699, 106347, 114339, 122682, 131380, 140438, 149861, 159653, 169819, 180364, 191292, 202609, 214317, 226423, 238930, 251843, 265165, 278902, 293057, 307634, 322638, 338073, 353943, 370251, 387002, 404200, 421848, 439951, 458512, 477535, 497024, 516983, 537415, 558323, 579713, 601587, 623949, 646802, 670150, 693997, 718345, 743199, 768563, 794438, 820829, 847740, 875173, 903132, 931620, 960640, 990196, 1020292, 1050929, 1082112, 1113844, 1146127, 1178965, 1212362, 1246320, 1280842, 1315932, 1351592, 1387826, 1424637, 1462027, 1500000],
	2000000: [0, 21, 119, 328, 673, 1176, 1855, 2727, 3808, 5112, 6652, 8442, 10493, 12818, 15427, 18331, 21541, 25066, 28917, 33102, 37630, 42512, 47755, 53368, 59360, 65738, 72510, 79685, 87269, 95271, 103697, 112556, 121854, 131598, 141795, 152453, 163577, 175174, 187251, 199814, 212870, 226425, 240485, 255056, 270145, 285756, 301897, 318573, 335790, 353553, 371869, 390742, 410179, 430184, 450764, 471923, 493668, 516003, 538933, 562464, 586601, 611349, 636713, 662699, 689310, 716553, 744431, 772951, 802116, 831931, 862402, 893533, 925329, 957794, 990933, 1024750, 1059251, 1094439, 1130320, 1166897, 1204175, 1242159, 1280853, 1320262, 1360389, 1401239, 1442816, 1485125, 1528169, 1571954, 1616483, 1661760, 1707790, 1754576, 1802123, 1850435, 1899516, 1949369, 2000000],
	2500000: [0, 26, 149, 410, 841, 1470, 2319, 3409, 4760, 6390, 8315, 10553, 13117, 16023, 19284, 22914, 26926, 31333, 36146, 41377, 47038, 53140, 59694, 66711, 74200, 82172, 90638, 99606, 109086, 119088, 129622, 140695, 152317, 164498, 177244, 190566, 204471, 218967, 234064, 249768, 266088, 283031, 300606, 318820, 337681, 357196, 377372, 398217, 419738, 441942, 464836, 488428, 512723, 537730, 563455, 589904, 617085, 645003, 673666, 703080, 733251, 764187, 795892, 828373, 861638, 895691, 930539, 966188, 1002645, 1039914, 1078003, 1116916, 1156661, 1197242, 1238666, 1280938, 1324063, 1368049, 1412900, 1458621, 1505219, 1552699, 1601067, 1650327, 1700486, 1751548, 1803520, 1856406, 1910212, 1964942, 2020603, 2077200, 2134737, 2193220, 2252654, 2313044, 2374395, 2436712, 2500000],
	3000000: [0, 32, 178, 492, 1010, 1764, 2782, 4091, 5712, 7668, 9978, 12663, 15740, 19227, 23141, 27497, 32311, 37599, 43375, 49652, 56446, 63768, 71633, 80053, 89040, 98607, 108765, 119527, 130903, 142906, 155546, 168834, 182781, 197397, 212693, 228679, 245365, 262761, 280876, 299721, 319305, 339638, 360728, 382584, 405217, 428635, 452846, 477860, 503685, 530330, 557803, 586113, 615268, 645276, 676146, 707885, 740502, 774004, 808400, 843696, 879902, 917024, 955070, 994048, 1033965, 1074829, 1116647, 1159426, 1203174, 1247897, 1293603, 1340300, 1387993, 1436690, 1486399, 1537125, 1588876, 1641659, 1695480, 1750346, 1806263, 1863239, 1921280, 1980393, 2040583, 2101858, 2164224, 2227687, 2292254, 2357931, 2424724, 2492640, 2561684, 2631864, 2703185, 2775652, 2849274, 2924054, 3000000],
	3500000:[0,37,208,574,1178,2058,3246,4773,6664,8946,11641,14774,18364,22432,26997,32080,37697,43866,50604,57928,65853,74396,83572,93395,103880,115041,126893,139448,152721,166724,181470,196973,213244,230297,248142,266792,286259,306554,327689,349675,372523,396244,420849,446348,472753,500074,528320,557503,587633,618718,650771,683799,717813,752822,788837,825866,863919,903005,943133,984312,1026552,1069861,1114249,1159723,1206293,1253967,1302755,1352664,1403703,1455880,1509204,1563683,1619325,1676139,1734132,1793313,1853689,1915269,1978060,2042070,2107307,2173779,2241494,2310458,2380680,2452168,2524928,2598968,2674296,2750919,2828845,2908080,2988632,3070508,3153715,3238261,3324152,3411396,3500000],
	4000000: [0, 42, 238, 656, 1346, 2352, 3710, 5454, 7616, 10224, 13304, 16884, 20987, 25636, 30854, 36663, 43082, 50132, 57833, 66203, 75261, 85024, 95511, 106737, 118720, 131475, 145020, 159369, 174538, 190542, 207395, 225112, 243708, 263196, 283591, 304905, 327153, 350348, 374502, 399628, 425740, 452850, 480970, 510112, 540289, 571513, 603795, 637147, 671580, 707107, 743738, 781484, 820358, 860368, 901528, 943847, 987336, 1032005, 1077866, 1124928, 1173202, 1222699, 1273427, 1325398, 1378621, 1433106, 1488863, 1545901, 1604232, 1663863, 1724805, 1787066, 1850657, 1915587, 1981865, 2049500, 2118502, 2188878, 2260639, 2333794, 2408351, 2484319, 2561707, 2640523, 2720777, 2802477, 2885632, 2970250, 3056339, 3143908, 3232966, 3323520, 3415579, 3509152, 3604246, 3700870, 3799031, 3898739, 4000000],
	5000000: [0, 53, 297, 820, 1683, 2940, 4637, 6818, 9520, 12779, 16630, 21105, 26234, 32045, 38568, 45828, 53852, 62665, 72291, 82754, 94076, 106280, 119388, 133421, 148400, 164344, 181275, 199211, 218172, 238177, 259244, 281390, 304635, 328995, 354488, 381132, 408941, 437934, 468127, 499535, 532175, 566063, 601213, 637641, 675362, 714391, 754744, 796433, 839475, 883883, 929672, 976855, 1025447, 1075461, 1126910, 1179809, 1234170, 1290007, 1347333, 1406160, 1466503, 1528373, 1591784, 1656747, 1723276, 1791382, 1861078, 1932377, 2005290, 2079829, 2156006, 2233833, 2313322, 2394484, 2477331, 2561875, 2648127, 2736098, 2825799, 2917243, 3010439, 3105399, 3202134, 3300654, 3400972, 3503097, 3607040, 3712812, 3820423, 3929885, 4041207, 4154400, 4269474, 4386440, 4505308, 4626087, 4748789, 4873423, 5000000],
	6000000:[0,63,357,984,2019,3528,5565,8181,11424,15335,19957,25326,31480,38454,46281,54994,64623,75198,86750,99305,112891,127536,143266,160105,178080,197213,217530,239054,261807,285812,311092,337668,365562,394794,425386,457358,490730,525521,561753,599443,638610,679275,721455,765169,810434,857269,905692,955720,1007370,1060660,1115607,1172226,1230536,1290553,1352292,1415770,1481004,1548008,1616799,1687392,1759804,1834048,1910140,1988096,2067931,2149658,2233294,2318852,2406347,2495794,2587207,2680600,2775986,2873381,2972798,3074250,3177752,3283317,3390959,3500691,3612526,3726478,3842560,3960785,4081166,4203716,4328448,4455374,4584508,4715862,4849448,4985280,5123369,5263728,5406369,5551305,5698547,5848108,6000000],
	9999999:[0,105,595,1640,3366,5880,9275,13636,19040,25559,33261,42210,52467,64090,77136,91656,107705,125331,144583,165508,188152,212561,238776,266842,296799,328689,362550,398423,436345,476354,518487,562780,609270,657990,708977,762263,817883,875869,936254,999071,1064351,1132125,1202425,1275281,1350724,1428782,1509487,1592867,1678950,1767767,1859344,1953710,2050894,2150921,2253820,2359617,2468339,2580013,2694665,2812320,2933006,3056746,3183567,3313494,3446551,3582764,3722156,3864753,4010579,4159657,4312011,4467665,4626643,4788968,4954662,5123750,5296253,5472195,5651598,5834485,6020877,6210797,6404267,6601308,6801943,7006193,7214079,7425623,7640846,7859769,8082413,8308799,8538947,8772879,9010614,9252174,9497578,9746846,9999999]
}

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
20: 9, # dark resist
18: 10, # light resist
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

def add_status_msg(msg, status_ctrl):
	if status_ctrl:
		evt = custom_events.wxStatusEvent(message=msg)            
		wx.PostEvent(status_ctrl, evt)
	else:
		print msg

def do_sync(raw_captured_data, status_ctrl, region, simulate=False):
	try:
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
				mon_array[3] = min(mon_array[3], base_data['max_skill'])
			
			latents = get_latents(mon_array[10])
			
			if mon_array[0] in existing_monsters:
				existing_data = existing_monsters.get(mon_array[0])
				if mon_array[1] > existing_data['current_xp'] or \
				   mon_array[3] > existing_data['current_skill'] or \
				   mon_array[5] != existing_data['monster'] or \
				   mon_array[6] > existing_data['plus_hp'] or \
				   mon_array[7] > existing_data['plus_atk'] or \
				   mon_array[8] > existing_data['plus_rcv'] or \
				   mon_array[9] > existing_data['current_awakening'] or \
				   len(latents.viewitems() - existing_data.viewitems()) > 0:
					update_data = {}
					update_data['monster'] = mon_array[5]
					if mon_array[1] > existing_data['current_xp']:
						update_data['current_xp'] = mon_array[1]
					if mon_array[3] > existing_data['current_skill']:
						update_data['current_skill'] = mon_array[3]
					if mon_array[5] > existing_data['monster']:
						update_data['current_skill'] = mon_array[3]
						update_data['current_xp'] = mon_array[1]
						update_data['current_awakening'] = mon_array[9]
					if mon_array[6] > existing_data['plus_hp']:
						update_data['plus_hp'] = mon_array[6]
					if mon_array[7] > existing_data['plus_atk']:
						update_data['plus_atk'] = mon_array[7]
					if mon_array[8] > existing_data['plus_rcv']:
						update_data['plus_rcv'] = mon_array[8]
					if mon_array[9] > existing_data['current_awakening']:
						update_data['current_awakening'] = mon_array[9]
					if len(latents.viewitems() - existing_data.viewitems()) > 0:
						update_data.update(latents)
					
					if simulate:
						r = fake_r
					else:
						r = session.patch(existing_data['url'], update_data)
					if r.status_code == requests.codes.ok:
						add_status_msg('Updated monster %s (id %d): %s' % (base_data['name'], existing_data['id'], ', '.join(k for k in update_data.keys() if k != 'monster')), status_ctrl)
						print r.content
					else:
						add_status_msg('Failed updating monster %s (id %d): %s %s' % (base_data['name'], existing_data['id'], r.status_code, r.content), status_ctrl)
					
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
				if found_id is not None:
					del unknown_pad_id_monsters[found_id]
					if simulate:
						r = fake_r
					else:
						r = session.patch(mon_url, update_data)
					if r.status_code == requests.codes.ok:
						add_status_msg('Updated monster %s (id %d): %s' % (monster_data[jp_id]['name'], jp_id, ', '.join(k for k in update_data.keys() if k != 'monster')), status_ctrl)
					else:
						add_status_msg('Failed updating monster %s (id %d): %s %s' % (monster_data[jp_id]['name'], jp_id, r.status_code, r.content), status_ctrl)
				else:
					if simulate:
						r = fake_r
					else:
						r = session.post(URL_MONSTER_CREATE, update_data)
					if r.status_code == requests.codes.ok or r.status_code == 201:
						add_status_msg('Created monster %s: %s' % (monster_data[jp_id]['name'], ', '.join(k for k in update_data.keys() if k != 'monster')), status_ctrl)
					else:
						add_status_msg('Failed creating monster %s: %s %s' % (monster_data[jp_id]['name'], r.status_code, r.content), status_ctrl)
		
		for mon in existing_monsters.values():
			if simulate:
				r = fake_r
			else:
				r = session.delete(mon['url'])

			if r.status_code == 204:
				add_status_msg('Removed monster %s (id %d)' % (monster_data[mon['monster']]['name'], mon['id']), status_ctrl)
			else:
				add_status_msg('Failed to remove monster %s (id %d)' % (monster_data[mon['monster']]['name'], mon['id']), status_ctrl)
		
		# Maybe update materials
		for monster_id, material in material_map.items():
			new_count = material_counts.get(monster_id, 0)
			if new_count != material['count']:
				data = dict(count=new_count)
				if simulate:
					r = fake_r
				else:
					r = session.patch(material['url'], data)
				if r.status_code == requests.codes.ok or r.status_code == 201:
					add_status_msg('Updated material %s from %d to %d' % (monster_data[monster_id]['name'], material['count'], new_count), status_ctrl)
				else:
					add_status_msg('Failed updating material %s: %s %s' % (monster_data[monster_id]['name'], r.status_code, r.content), status_ctrl)


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
	
if __name__ == '__main__':
	f = open(sys.argv[1], "r")
	contents = f.read()
	f.close()
	
	app = wx.App(False)
	config = wx.Config("padherder_proxy_testing")
	wx.ConfigBase.Set(config)
	
	config.Write("username", sys.argv[2])
	config.Write("password", sys.argv[3])

	do_sync(contents, None, "NA", False)
	