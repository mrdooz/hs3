# downloads series metadata
import gevent.monkey
import gevent.pool
gevent.monkey.patch_socket()
import requests

from datetime import datetime
import gevent
import unicodedata
from collections import *
from bs4 import BeautifulSoup
import argparse
import functools
import copy
import os
import shutil
import json

from hs3db import Base, Series, Season, Episode, UserSeries, User

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine('mysql://root:@localhost/haveiseenit')
Session = sessionmaker(bind=engine)
session = Session()

SERIES = json.loads(open('series.json').read())
IMDB_BASE = 'http://www.imdb.com'
IMDB_LANDING_SUFFIX = 'title/%s'
IMDB_EPISODES_SUFFIX = 'title/%s/episodes'
SAVE_DIR = 'pages'
THUMBNAIL_DIR = 'thumbnails'
REQUEST_QUEUE = []
OUTSTANDING_REQUESTS = 0

VERBOSE = 10


def add_request(url, cb):
    REQUEST_QUEUE.append({'url': url, 'cb': cb})


def on_thumbnail_loaded(params, response, *args, **kwargs):
    if response.status_code != 200:
        return

    f = os.path.join(THUMBNAIL_DIR, params['imdb_id'] + params['ext'])
    with open(f, 'wb') as out_file:
        shutil.copyfileobj(response.raw, out_file)


def dump_info():
    for series in session.query(Series):
        print '%s - num seasons: %d' % (series.name, len(series.seasons))

        for season in series.seasons:
            print '%d - num eps: %d' % (season.season_nr, len(season.episodes))


def on_landing_page_loaded(params, response, *args, **kwargs):
    # Get the series description, and request the episode page
    if VERBOSE:
        print 'on_landing_page_loaded: %s (%s)' % (params, response.url)
    desc = None
    body = response.content
    soup = BeautifulSoup(body, "html.parser")
    imdb_id = params['imdb_id']

    # download thumbnail, if available
    img_elem = soup.select('#img_primary > div.image > a > img')
    if img_elem:
        img_path = img_elem[0]['src']
        _, ext = os.path.splitext(img_path)
        p = { 'imdb_id': params['imdb_id'], 'ext': ext }
        add_request(img_path, functools.partial(on_thumbnail_loaded, p))

    tmp = soup.select('#overview-top')
    try:
        for _, p in enumerate(tmp[0].find_all('p')):
            if p.text:
                desc = p.text.strip()
                params['desc'] = desc
                add_request(
                    IMDB_EPISODES_SUFFIX % imdb_id,
                    functools.partial(on_episode_page_loaded, params))
                return
    except IndexError:
        pass

    print 'No description found for: %s' % name


def on_episode_page_loaded(params, response, *args, **kwargs):
    # Get # seasons, and create the series if needed
    body = response.content
    soup = BeautifulSoup(body, "html.parser")
    # extract the episode links. this is based on the current
    # imdb page layout, so it might break in the future
    num_seasons = None
    try:
        episode_drop_down = soup.select('#bySeason > option')
        num_seasons = len(episode_drop_down)
        if VERBOSE:
            print 'Num seasons: %d (%s)' % (num_seasons, response.url)

        if not num_seasons:
            print 'Unable to parse #seasons. Skipping'
            return

        imdb_id = params['imdb_id']
        name = params['name']
        desc = params['desc']
        series_id = None

        # check if the series already exists
        for s in session.query(Series).filter(Series.imdb_id == imdb_id).limit(1):
            series_id = s.series_id

        if not series_id:
            new_series = Series(
                imdb_id=imdb_id, name=name, desc=desc, ended=False)
            session.add(new_series)

            session.commit()
            series_id = new_series.series_id

        # check which seasons we have
        existing_seasons = []
        if not params.get('force'):
            for s in session.query(Season).filter(Season.series_id == series_id):
                existing_seasons.append(s.season_nr)

        url = IMDB_EPISODES_SUFFIX % imdb_id

        if VERBOSE > 2:
            print 'existing seasons: %s' % existing_seasons

        # update any seasons we don't have, and scan the last 3 again
        for i in range(1, num_seasons + 1):

            scan = (i not in existing_seasons) or num_seasons - i < 3
            if not scan:
                continue

            pp = copy.deepcopy(params)
            pp['series_id'] = series_id
            pp['season_nr'] = i

            r = {
                'url': url,
                'payload': {'season': str(i)},
                'cb': functools.partial(on_season_page_loaded, pp)
            }
            REQUEST_QUEUE.append(r)
    except IOError:
        # TODO(magnus): what are the parsing exceptions?
        print 'Error parsing landing page. Skipping'


def on_season_page_loaded(params, response, *args, **kwargs):

    if VERBOSE > 2:
        print 'on_season_page_loaded: %s' % params

    def get_first(tag, css_path):
        tmp = tag.select(css_path)
        if len(tmp) == 0:
            return None
        return tmp[0]

    text = response.content
    soup = BeautifulSoup(text, "html.parser")

    series_id = params['series_id']
    season_nr = params['season_nr']

    parsed_episodes = {}

    for x in soup.select('#episodes_content > div.clear > div.list.detail.eplist'):
        for y in x.select('div.info'):
            # grab the episode nr
            episode_nr = None
            tmp = get_first(y, 'meta')
            if tmp:
                episode_nr = int(tmp.get('content', None))

            # grab air date
            airdate = None
            tmp = get_first(y, 'div.airdate')
            if tmp:
                # strip any whitespace and convert 'Sep.' to 'Sep'
                tmp = str(tmp.contents[0]).strip()
                if len(tmp) > 0:
                    tmp = tmp.replace('.', '')
                    try:
                        airdate = datetime.strptime(tmp, '%d %b %Y')
                    except:
                        pass

            # name
            name = None
            tmp = get_first(y, 'strong > a')
            if tmp:
                name = unicodedata.normalize(
                    'NFKD', tmp.contents[0]).encode('ascii', 'ignore').strip()

            # description
            desc = None
            tmp = get_first(y, 'div.item_description')
            if tmp:
                desc = unicodedata.normalize(
                    'NFKD', tmp.contents[0]).encode('ascii', 'ignore').strip()

            if episode_nr and airdate and name:
                parsed_episodes[episode_nr] = Episode(
                    season_id=-1,
                    episode_nr=episode_nr,
                    name=name,
                    desc=desc,
                    airdate=airdate
                )
            else:
                print "Unable to parse episode: %s" % episode_nr

    # If the season exists, see if we should update any episodes
    correct_episodes = set()
    season_id = None
    update_needed = False

    if VERBOSE > 3:
        print 'Found episodes: %s' % parsed_episodes.keys()

    for season in (
        session.query(Season).
        filter(Season.season_nr == season_nr).
        filter(Season.series_id == series_id)
    ):
        season_id = season.season_id

        # check if we should update any existing episodes
        for episode in season.episodes:
            correct_episodes.add(episode.episode_nr)
            # check if the episode is newly parsed, and contains updated info
            if episode.episode_nr in parsed_episodes:
                p = parsed_episodes[episode.episode_nr]
                if p.name != episode.name or p.desc != episode.desc or p.airdate != episode.airdate:
                    # print '%s vs %s, %s vs %s, %s vs %s' % (p.name, episode.name, p.desc, episode.desc, p.airdate, episode.airdate)
                    if VERBOSE > 2:
                        print 'Updating episode: %d (%s)' % (episode.episode_nr, episode.name)
                    episode.name = p.name
                    episode.desc = p.desc
                    episode.airdate = p.airdate
                    update_needed = True

    if not season_id:
        new_season = Season(series_id=series_id, season_nr=season_nr)
        session.add(new_season)
        session.commit()
        season_id = new_season.season_id

    for nr, episode in parsed_episodes.iteritems():
        if nr not in correct_episodes:
            episode.season_id = season_id
            if VERBOSE > 2:
                print 'Adding episode: %d (%s)' % (episode.episode_nr, episode.name)
            session.add(episode)
            update_needed = True

    if update_needed:
        session.commit()


def safe_mkdir(path):
    try:
        os.makedirs(path)
    except OSError:
        pass


def download_worker(r, cb):
    global OUTSTANDING_REQUESTS
    url = r['url']
    stream = False
    if url.startswith('http'):
        stream = True
        f = url
    else:
        f = IMDB_BASE + '/' + url
    response = requests.get(f, params=r.get('payload'), stream=stream)
    save_page = False
    imdb_id = r.get('imdb_id')
    if save_page and not stream:
        if not f.endswith('episodes'):
            # landing page
            imdb_id = url[6:]
            p = os.path.join(SAVE_DIR, imdb_id)
            safe_mkdir(p)
            f = os.path.join(p, 'index.html')
            open(f, 'wt').write(response.content)
        else:
            imdb_id = url[6:]
            idx = imdb_id.find('/')
            imdb_id = imdb_id[:idx]
            p = os.path.join(SAVE_DIR, imdb_id)
            safe_mkdir(p)
            if not r.get('payload'):
                # episode list
                f = os.path.join(p, 'seasons.html')
                open(f, 'wt').write(response.content)
            else:
                # specific season
                f = os.path.join(p, 'seasons_%.2d.html' % int(r['payload']['season']))
                open(f, 'wt').write(response.content)
    cb(response)
    OUTSTANDING_REQUESTS -= 1


def runner():
    pool = gevent.pool.Pool(20)
    global REQUEST_QUEUE, OUTSTANDING_REQUESTS
    while OUTSTANDING_REQUESTS > 0 or len(REQUEST_QUEUE) > 0:
        print 'tick: outstanding: %d, queued: %d' % (OUTSTANDING_REQUESTS, len(REQUEST_QUEUE))

        max_spawns = 20
        while len(REQUEST_QUEUE):
            r = REQUEST_QUEUE[0]
            REQUEST_QUEUE = REQUEST_QUEUE[1:]
            OUTSTANDING_REQUESTS += 1
            pool.spawn(download_worker, r, r.get('cb'))
            max_spawns -= 1
            if max_spawns == 0:
                break
        gevent.sleep(1)


parser = argparse.ArgumentParser()
parser.add_argument('--series', '-s', nargs='*')
args = parser.parse_args()

Base.metadata.create_all(engine)

valid_series = {}
for s in args.series or SERIES.keys():
    if s not in SERIES:
        print 'Unknown series: %s' % s
    else:
        valid_series[s] = SERIES[s]
SERIES = valid_series

safe_mkdir(SAVE_DIR)
safe_mkdir(THUMBNAIL_DIR)

for v in SERIES.values():
    imdb_id = v['imdb_id']
    name = v['name']
    print 'Fetching: %s (%s)' % (name, imdb_id)
    # download series landing page, and get # seasons
    params = {
        'imdb_id': imdb_id,
        'name': name
    }
    r = {
        'url': IMDB_LANDING_SUFFIX % imdb_id,
        'cb': functools.partial(on_landing_page_loaded, params)
    }
    REQUEST_QUEUE.append(r)

g = gevent.Greenlet.spawn(runner)
gevent.Greenlet.join(g)
