import hs3db

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

MYSQL_USER = os.environ['HS3_MYSQL_USER']
MYSQL_PWD = os.environ['HS3_MYSQL_PWD']

engine = create_engine(
    'mysql://%s:%s@localhost/haveiseenit' % (MYSQL_USER, MYSQL_PWD),
    echo=True)
Session = sessionmaker(bind=engine)
session = Session()

from flask import Flask, request
from flask_restful import reqparse, Resource, Api
from flask_restful import reqparse
from flask.ext.cors import CORS
from datetime import datetime

app = Flask(__name__)
cors = CORS(app, resources={r"/*": {"origins": "*"}})
api = Api(app)


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


class Series(Resource):
    def get(self, series_id):
        return 'Nothing to see here'


class SeriesList(Resource):
    def get(self):
        res = []
        for s in session.query(hs3db.Series):
            res.append({
                'name': s.name,
                'desc': s.desc,
                'num_seasons': len(s.seasons),
                'id': s.series_id
            })
        return res


class Season(Resource):
    def get(self, series_id, season_nr):
        pass

    def put(self, season_id):
        #     def put(self, todo_id):
        # todos[todo_id] = request.form['data']
        # return {todo_id: todos[todo_id]}
        pass


class Episode(Resource):
    def get(self, series_id, season_nr, episode_nr):
        for episode in (
            session.query(hs3db.Episode).
            filter(hs3db.Episode.season_id == hs3db.Season.season_id).
            filter(hs3db.Season.series_id == hs3db.Series.series_id).
            filter(hs3db.Episode.episode_nr == episode_nr).
            filter(hs3db.Season.season_nr == season_nr).
            filter(hs3db.Series.series_id == series_id)
        ):
            res = {
                'name': episode.name,
                'desc': episode.desc,
                'airdate': str(episode.airdate)
            }
            return res


class UserSubscribe(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('user_id', action='append')
    parser.add_argument('season_nr')
    parser.add_argument('series_id')


def get_episode_info(season_id):
    episode_descs = {}
    episode_dates = {}
    now = datetime.now()
    for episode in session.query(hs3db.Episode).filter(hs3db.Episode.season_id == season_id):

        if episode.airdate > now:
            desc = episode.airdate.strftime('(Airs %d, %b %Y)') + '\n' + episode.desc
        else:
            desc = episode.airdate.strftime('(Aired %d, %b %Y)') + '\n' + episode.desc

        episode_descs[episode.episode_nr] = desc

        # convert time to epoch
        airdate = (episode.airdate - datetime(1970, 1, 1)).total_seconds()
        episode_dates[episode.episode_nr] = airdate

    return episode_descs, episode_dates


class UserSetSeason(Resource):

    parser = reqparse.RequestParser()
    parser.add_argument('user_id', action='append')
    parser.add_argument('season_nr')
    parser.add_argument('series_id')

    def post(self):
        # TODO(magnus): add session concept, to keep track of multiple users
        args = UserSetSeason.parser.parse_args()

        print args
        series_id = args['series_id']
        season_nr = args['season_nr']

        # update the current season
        for u in (
            session.query(hs3db.UserSeries).
            filter(hs3db.UserSeries.series_id == series_id)
        ):
            u.cur_season = season_nr
            session.commit()

        # get the season id
        for season in (
            session.query(hs3db.Season).
            filter(hs3db.Season.series_id == series_id).
            filter(hs3db.Season.season_nr == season_nr)
        ):
            season_id = season.season_id

            # get episodes seen for new season
            for user_season in (
                session.query(hs3db.UserSeason).
                filter(hs3db.UserSeason.season_id == season_id)
            ):
                desc, airdate = get_episode_info(season.season_id)

                return {
                    'season_id': season.season_id,
                    'num_episodes': len(season.episodes),
                    'episode_descs': desc,
                    'episode_dates': airdate,
                    'seen': seen_from_user_season(user_season),
                }


class UserUpdateEpisodes(Resource):

    parser = reqparse.RequestParser()
    parser.add_argument('user_id', action='append')
    parser.add_argument('season_id')
    parser.add_argument('add', action='append')
    parser.add_argument('del', action='append')

    def post(self):
        # TODO(magnus): add session concept, to keep track of multiple users
        args = UserUpdateEpisodes.parser.parse_args()

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
            session.query(hs3db.UserSeason).
            filter(hs3db.UserSeason.season_id == season_id)
        ):
            u.bits0 |= add_mask[0]
            u.bits0 &= del_mask[0]
            u.bits1 |= add_mask[1]
            u.bits1 &= del_mask[1]
            u.bits2 |= add_mask[2]
            u.bits2 &= del_mask[2]
            u.bits3 |= add_mask[3]
            u.bits3 &= del_mask[3]

            session.commit()


def add_default_user_data(missing_series, user_id):

    for series_id, series in missing_series.iteritems():
        session.add(hs3db.UserSeries(user_id=user_id, series_id=series_id, cur_season=1))

        for season in session.query(hs3db.Season).filter(hs3db.Season.series_id == series_id):
            session.add(hs3db.UserSeason(user_id=user_id, season_id=season.season_id))

    session.commit()


class UserInfo(Resource):
    def get(self):
        res = []

        user_id = 1

        # create the user if they don't exist
        if (
            session.query(hs3db.User.user_id).
            filter(hs3db.User.user_id == user_id).
            count() == 0
        ):
            session.add(hs3db.User(user_id=user_id, name='mange'))
            session.commit()

        # get all user series
        user_series_ids = set()
        for user_series in (
            session.query(hs3db.UserSeries).
            filter(hs3db.UserSeries.user_id == user_id)
        ):
            user_series_ids.add(user_series.series_id)

        # create any missing user series
        all_series = {}
        for series in session.query(hs3db.Series):
            all_series[series.series_id] = series

        missing_ids = set(all_series.keys()) - user_series_ids
        add_default_user_data({k:all_series[k] for k in missing_ids}, user_id)

        for result in (
            session.query(hs3db.Series, hs3db.Season, hs3db.UserSeries, hs3db.UserSeason).
            filter(hs3db.Season.series_id == hs3db.Series.series_id).
            filter(hs3db.Season.series_id == hs3db.UserSeries.series_id).
            filter(hs3db.Season.season_nr == hs3db.UserSeries.cur_season).
            filter(hs3db.UserSeason.season_id == hs3db.Season.season_id)
        ):
            series = result[0]
            season = result[1]
            user_series = result[2]
            user_season = result[3]

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


api.add_resource(SeriesList, '/series')
api.add_resource(Series, '/series/<series_id>')
api.add_resource(Season, '/series/<series_id>/<season_nr>')
api.add_resource(Episode, '/series/<series_id>/<season_nr>/<episode_nr>')

api.add_resource(UserSetSeason, '/user/set_season')
api.add_resource(UserUpdateEpisodes, '/user/update_episodes')
api.add_resource(UserSubscribe, '/user/subscribe')
api.add_resource(UserInfo, '/user/info')


if __name__ == '__main__':
    hs3db.Base.metadata.create_all(engine)
    app.run(debug=True)
