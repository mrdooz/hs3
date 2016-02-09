from flask import Flask, request
from flask_restful import reqparse, Resource, Api
from flask_restful import reqparse
from flask.ext.cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask.ext.compress import Compress
from datetime import datetime
import os
import settings

app = Flask(__name__)
cors = CORS(app, resources={r"/*": {"origins": "*"}})
Compress(app)
api = Api(app)
app.config.from_object('settings')
app.config['SQLALCHEMY_DATABASE_URI'] = (
    'mysql://%s:%s@localhost/haveiseenit' %
    (settings.MYSQL_USER, settings.MYSQL_PWD))
db = SQLAlchemy(app)

import hs3db
User, Series, Season, Episode, UserSeries, UserSeason, SeriesMeta = hs3db.init_db(db)


def seen_from_user_season(s):
    res = []

    def process(b, ofs):
        for i in range(32):
            if (b & (1 << i)):
                res.append(i + ofs)

    process(s.bits0, 0)
    process(s.bits1, 32)
    process(s.bits2, 64)
    process(s.bits3, 96)
    return res


class SeriesResource(Resource):
    def get(self, series_id):
        return 'Nothing to see here'


class SeriesListResource(Resource):
    def get(self):
        res = []
        for s in Series.db.session.query(Series):
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
        #     def put(self, todo_id):
        # todos[todo_id] = request.form['data']
        # return {todo_id: todos[todo_id]}
        pass


class EpisodeResource(Resource):
    def get(self, series_id, season_nr, episode_nr):
        for episode in (
            db.session.query(Episode).
            filter(Episode.season_id == Season.season_id).
            filter(Season.series_id == Series.series_id).
            filter(Episode.episode_nr == episode_nr).
            filter(Season.season_nr == season_nr).
            filter(Series.series_id == series_id)
        ):
            res = {
                'name': episode.name,
                'desc': episode.desc,
                'airdate': str(episode.airdate)
            }
            return res


class UserSubscribeResource(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('user_id', action='append')
    parser.add_argument('season_nr')
    parser.add_argument('series_id')


def get_episode_info(season_id):
    episode_descs = {}
    episode_dates = {}
    now = datetime.now()
    for episode in db.session.query(Episode).filter(Episode.season_id == season_id):

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

    parser = reqparse.RequestParser()
    parser.add_argument('user_id', action='append')
    parser.add_argument('season_nr')
    parser.add_argument('series_id')

    def post(self):
        # TODO(magnus): add session concept, to keep track of multiple users
        args = UserSetSeasonResource.parser.parse_args()

        print args
        series_id = args['series_id']
        season_nr = args['season_nr']

        # update the current season
        for u in (
            db.session.query(UserSeries).
            filter(UserSeries.series_id == series_id)
        ):
            u.cur_season = season_nr
            db.session.commit()

        # get the season id
        for season in (
            db.session.query(Season).
            filter(Season.series_id == series_id).
            filter(Season.season_nr == season_nr)
        ):
            season_id = season.season_id

            # get episodes seen for new season
            for user_season in (
                db.session.query(UserSeason).
                filter(UserSeason.season_id == season_id)
            ):
                desc, airdate = get_episode_info(season.season_id)

                return {
                    'season_id': season.season_id,
                    'num_episodes': len(season.episodes),
                    'episode_descs': desc,
                    'episode_dates': airdate,
                    'seen': seen_from_user_season(user_season),
                }


class UserUpdateEpisodesResource(Resource):

    parser = reqparse.RequestParser()
    parser.add_argument('user_id', action='append')
    parser.add_argument('season_id')
    parser.add_argument('add', action='append')
    parser.add_argument('del', action='append')

    def post(self):
        # TODO(magnus): add session concept, to keep track of multiple users
        args = UserUpdateEpisodesResource.parser.parse_args()

        print args
        season_id = args['season_id']
        adds = args['add']
        dels = args['del']

        add_mask = [0, 0, 0, 0]
        del_mask = [0xffffffff for _ in range(4)]

        for x in adds or []:
            x = int(x)
            add_mask[x/32] |= 1 << (x % 32)

        for x in dels or []:
            x = int(x)
            del_mask[x/32] &= ~(1 << (x % 32))

        for u in (
            db.session.query(UserSeason).
            filter(UserSeason.season_id == season_id)
        ):
            u.bits0 |= add_mask[0]
            u.bits0 &= del_mask[0]
            u.bits1 |= add_mask[1]
            u.bits1 &= del_mask[1]
            u.bits2 |= add_mask[2]
            u.bits2 &= del_mask[2]
            u.bits3 |= add_mask[3]
            u.bits3 &= del_mask[3]

            db.session.commit()


def add_default_user_data(missing_series, user_id):

    for series_id, series in missing_series.iteritems():
        db.session.add(UserSeries(user_id=user_id, series_id=series_id, cur_season=1))

        for season in db.session.query(Season).filter(Season.series_id == series_id):
            db.session.add(UserSeason(user_id=user_id, season_id=season.season_id))

    db.session.commit()


class UserInfoResource(Resource):
    def get(self):

        user_id = 1

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
        add_default_user_data({k:all_series[k] for k in missing_ids}, user_id)

        res = []
        for series, season, user_series, user_season in (
            db.session.query(Series, Season, UserSeries, UserSeason).
            filter(Season.series_id == Series.series_id).
            filter(Season.series_id == UserSeries.series_id).
            filter(Season.season_nr == UserSeries.cur_season).
            filter(UserSeason.season_id == Season.season_id)
        ):
            desc, airdate = get_episode_info(season.season_id)

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
                'seen': seen_from_user_season(user_season),
                })

        return res

api.add_resource(SeriesListResource, '/series')
api.add_resource(SeriesResource, '/series/<series_id>')
api.add_resource(SeasonResource, '/series/<series_id>/<season_nr>')
api.add_resource(EpisodeResource, '/series/<series_id>/<season_nr>/<episode_nr>')

api.add_resource(UserSetSeasonResource, '/user/set_season')
api.add_resource(UserUpdateEpisodesResource, '/user/update_episodes')
api.add_resource(UserSubscribeResource, '/user/subscribe')
api.add_resource(UserInfoResource, '/user/info')

if __name__ == '__main__':
    db.create_all()
    app.run()
