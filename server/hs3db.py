def init_db(db):

    class User(db.Model):
        # TODO(magnus): figure out how to call these guys "id" instead of "user_id" et al
        user_id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(128), nullable=False)

    class Series(db.Model):
        series_id = db.Column(db.Integer, primary_key=True)
        imdb_id = db.Column(db.String(32), nullable=False, unique=True)
        name = db.Column(db.String(128), nullable=False)
        desc = db.Column(db.String(1024), nullable=False)
        ended = db.Column(db.Boolean, default=False)
        active = db.Column(db.Boolean, default=True)

    class Season(db.Model):
        season_id = db.Column(db.Integer, primary_key=True)
        season_nr = db.Column(db.Integer, nullable=False)

        # season start, season end
        season_start = db.Column(db.DateTime)
        season_end = db.Column(db.DateTime)

        series_id = db.Column(
            db.Integer,
            db.ForeignKey('series.series_id', onupdate='CASCADE', ondelete='CASCADE'))
        series = db.relationship("Series", backref=db.backref('seasons', order_by=series_id))
        db.UniqueConstraint('series_id', 'season_nr')

    class Episode(db.Model):
        episode_id = db.Column(db.Integer, primary_key=True)
        episode_nr = db.Column(db.Integer, nullable=False)
        name = db.Column(db.String(128), nullable=False)
        desc = db.Column(db.String(1024))
        airdate = db.Column(db.DateTime, nullable=False)

        season_id = db.Column(
            db.Integer,
            db.ForeignKey('season.season_id', onupdate='CASCADE', ondelete='CASCADE'))
        season = db.relationship("Season", backref=db.backref('episodes', order_by=episode_id))

        db.UniqueConstraint('season_id', 'episode_nr')

    class UserSeries(db.Model):
        cur_season = db.Column(db.Integer, nullable=False)

        user_id = db.Column(
            db.Integer,
            db.ForeignKey('user.user_id', onupdate='CASCADE', ondelete='CASCADE'),
            primary_key=True
        )

        series_id = db.Column(
            db.Integer,
            db.ForeignKey('series.series_id', onupdate='CASCADE', ondelete='CASCADE'),
            primary_key=True
        )

    class UserSeason(db.Model):
        offset = db.Column(db.Integer, default=0)
        bits0 = db.Column(db.Integer, default=0)
        bits1 = db.Column(db.Integer, default=0)
        bits2 = db.Column(db.Integer, default=0)
        bits3 = db.Column(db.Integer, default=0)

        user_id = db.Column(
            db.Integer,
            db.ForeignKey('user.user_id', onupdate='CASCADE', ondelete='CASCADE'),
            primary_key=True)
        season_id = db.Column(
            db.Integer,
            db.ForeignKey('season.season_id', onupdate='CASCADE', ondelete='CASCADE'),
            primary_key=True)

        user = db.relationship("User", backref=db.backref('userseasons', order_by=user_id))

    class SeriesMeta(db.Model):
        series_meta_id = db.Column(db.Integer, primary_key=True)
        current_season = db.Column(db.Integer, nullable=False)
        next_update = db.Column(db.Integer)

    return {
        'user_cls': User,
        'series_cls': Series,
        'season_cls': Season,
        'episode_cls': Episode,
        'userseries_cls': UserSeries,
        'userseason_cls': UserSeason,
        'seriesmeta_cls': SeriesMeta
    }
