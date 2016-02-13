from flask import Flask, request
from flask_restful import reqparse, Resource, Api
from flask.ext.cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask.ext.compress import Compress
from datetime import datetime
import os
import settings
import logging
import hs3db

SERVER = None
User = None
Series = None
Season = None
Episode = None
UserSeries = None
UserSeason = None
SeriesMeta = None

class Server(object):

    def __init__(self):
        self.app = Flask(__name__)
        self.cors = CORS(self.app, resources={r"/*": {"origins": "*"}})
        Compress(self.app)
        self.api = Api(self.app)
        self.app.config.from_object('settings')
        self.app.config['SQLALCHEMY_DATABASE_URI'] = (
            'mysql://%s:%s@localhost/haveiseenit' %
            (settings.MYSQL_USER, settings.MYSQL_PWD))
        self.db = SQLAlchemy(self.app)

        global User, Series, Season, Episode, UserSeries, UserSeason, SeriesMetag
        hs3db_cls = hs3db.init_db(self.db)
        User, Series, Season, Episode, UserSeries, UserSeason, SeriesMeta = [
            hs3db_cls[x]
            for x in [
                'user_cls', 'series_cls', 'season_cls', 'episode_cls',
                'userseries_cls', 'userseason_cls', 'seriesmeta_cls']]

        self.api.add_resource(self.SeriesListResource, '/series')
        self.api.add_resource(self.SeriesResource, '/series/<series_id>')
        self.api.add_resource(self.SeasonResource, '/series/<series_id>/<season_nr>')
        self.api.add_resource(self.EpisodeResource, '/series/<series_id>/<season_nr>/<episode_nr>')

        self.api.add_resource(self.UserSetSeasonResource, '/user/set_season')
        self.api.add_resource(self.UserUpdateEpisodesResource, '/user/update_episodes')
        self.api.add_resource(self.UserSubscribeResource, '/user/subscribe')
        self.api.add_resource(self.UserInfoResource, '/user/info')

        self.db.create_all()

    def seen_from_user_season(self, user_season):
        """ Given a user_season, return the seen episodes """
        res = []

        def process(bits, ofs):
            for i in range(32):
                if (bits & (1 << i)):
                    res.append(i + ofs)

        process(user_season.bits0, 0)
        process(user_season.bits1, 32)
        process(user_season.bits2, 64)
        process(user_season.bits3, 96)
        return res

    class SeriesResource(Resource):
        def get(self, series_id):
            return 'Nothing to see here'

    class SeriesListResource(Resource):
        """ Return list of all series """
        def get(self):
            res = []
            for s in self.Series.query.all():
                res.append({
                    'name': s.name,
                    'desc': s.desc,
                    'num_seasons': len(s.seasons),
                    'id': s.series_id
                })
            return res

    class SeasonResource(Resource):
        def get(self, series_id, season_nr):
            pass

        def put(self, season_id):
            pass

    class EpisodeResource(Resource):
        def get(self, series_id, season_nr, episode_nr):
            db = SERVER.db

            try:
                episode = (
                    db.session.query(Episode).
                    filter(Episode.season_id == Season.season_id).
                    filter(Season.series_id == Series.series_id).
                    filter(Episode.episode_nr == episode_nr).
                    filter(Season.season_nr == season_nr).
                    filter(Series.series_id == series_id).one())

                res = {
                    'name': episode.name,
                    'desc': episode.desc,
                    'airdate': str(episode.airdate)
                }
                return res
            except Exception:
                logging.exception('error')

    class UserSubscribeResource(Resource):
        parser = reqparse.RequestParser()
        parser.add_argument('user_id', action='append')
        parser.add_argument('season_nr')
        parser.add_argument('series_id')

    def episode_info_for_season(self, season_id):
        """ Get episode desc and airdate for all episodes for the given season_id """
        episode_descs = {}
        episode_dates = {}
        now = datetime.now()
        for episode in Episode.query.filter(Episode.season_id == season_id):

            if episode.airdate > now:
                desc = episode.airdate.strftime('(Airs %d, %b %Y)') + '\n' + episode.desc
            else:
                desc = episode.airdate.strftime('(Aired %d, %b %Y)') + '\n' + episode.desc

            episode_descs[episode.episode_nr] = desc

            # convert time to epoch
            airdate = (episode.airdate - datetime(1970, 1, 1)).total_seconds()
            episode_dates[episode.episode_nr] = airdate

        return episode_descs, episode_dates

    class UserSetSeasonResource(Resource):
        """ Set the current season for the series. Returns new season episodes """
        parser = reqparse.RequestParser()
        parser.add_argument('user_id', action='append')
        parser.add_argument('season_nr')
        parser.add_argument('series_id')

        def post(self):
            args = Server.UserSetSeasonResource.parser.parse_args()
            logging.debug('UserSetSeasonResource: %r', args)

            series_id = args['series_id']
            season_nr = args['season_nr']

            try:
                # update the current season
                user_series = UserSeries.query.filter(UserSeries.series_id == series_id).one()
                if user_series:
                    user_series.cur_season = season_nr
                    SERVER.db.session.commit()

                # get the season id
                season = (
                    Season.query.
                    filter(Season.series_id == series_id).
                    filter(Season.season_nr == season_nr).
                    one())

                season_id = season.season_id

                # get episodes seen for new season
                user_season = UserSeason.query.filter(UserSeason.season_id == season_id).one()
                desc, airdate = SERVER.episode_info_for_season(season_id)

                return {
                    'season_id': season_id,
                    'num_episodes': len(season.episodes),
                    'episode_descs': desc,
                    'episode_dates': airdate,
                    'seen': SERVER.seen_from_user_season(user_season),
                }

            except Exception:
                logging.exception('error')

    class UserUpdateEpisodesResource(Resource):
        """ Mark episodes as seen/unseen for the given season """
        parser = reqparse.RequestParser()
        parser.add_argument('user_id', action='append')
        parser.add_argument('season_id')
        parser.add_argument('add', action='append')
        parser.add_argument('del', action='append')

        def post(self):
            args = Server.UserUpdateEpisodesResource.parser.parse_args()
            logging.debug('UserUpdateEpisodesResource: %r', args)

            season_id = args['season_id']
            adds = map(int, args['add'] or [])
            dels = map(int, args['del'] or [])

            try:
                u = UserSeason.query.filter(UserSeason.season_id == season_id).one()
                bits = [u.bits0, u.bits1, u.bits2, u.bits3]

                for x in adds:
                    bits[x/32] |= 1 << (x % 32)

                for x in dels:
                    bits[x/32] &= ~(1 << (x % 32))

                u.bits0, u.bits1, u.bits2, u.bits3 = bits
                SERVER.db.session.commit()
            except Exception:
                logging.exception('error')


    def add_default_user_data(self, missing_series, user_id):
        """ Add default entries for the UserSeries/UserSeason for the given series """
        for series_id, series in missing_series.iteritems():
            self.db.session.add(UserSeries(user_id=user_id, series_id=series_id, cur_season=1))

            for season in Season.query(Season.season_id).filter(Season.series_id == series_id):
                self.db.session.add(UserSeason(user_id=user_id, season_id=season.season_id))

        self.db.session.commit()

    class UserInfoResource(Resource):
        def get(self):

            user_id = 1
            db = SERVER.db

            # create the user if they don't exist
            if (
                db.session.query(User.user_id).
                filter(User.user_id == user_id).
                count() == 0
            ):
                db.session.add(User(user_id=user_id, name='mange'))
                db.session.commit()

            # get all user series
            user_series_ids = set()
            for user_series in (
                db.session.query(UserSeries).
                filter(UserSeries.user_id == user_id)
            ):
                user_series_ids.add(user_series.series_id)

            # create any missing user series
            all_series = {}
            for series in Series.query.all():
                all_series[series.series_id] = series

            missing_ids = set(all_series.keys()) - user_series_ids
            SERVER.add_default_user_data({k:all_series[k] for k in missing_ids}, user_id)

            res = []
            for series, season, user_series, user_season in (
                db.session.query(Series, Season, UserSeries, UserSeason).
                filter(Season.series_id == Series.series_id).
                filter(Season.series_id == UserSeries.series_id).
                filter(Season.season_nr == UserSeries.cur_season).
                filter(UserSeason.season_id == Season.season_id)
            ):
                desc, airdate = SERVER.episode_info_for_season(season.season_id)

                res.append({
                    'name': series.name,
                    'id': series.series_id,
                    'imdb_id': series.imdb_id,
                    'num_seasons': len(series.seasons),
                    'num_episodes': len(season.episodes),
                    'episode_descs': desc,
                    'episode_dates': airdate,
                    'cur_season': user_series.cur_season,
                    'season_id': season.season_id,
                    'seen': SERVER.seen_from_user_season(user_season),
                    })

            return res


    def run(self):
        self.app.run()

if __name__ == '__main__':
    SERVER = Server()
    SERVER.run()
