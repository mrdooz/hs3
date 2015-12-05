from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy import ForeignKey, UniqueConstraint, PrimaryKeyConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, backref

Base = declarative_base()


class User(Base):
    __tablename__ = 'user'

    # TODO(magnus): figure out how to call these guys "id" instead of "user_id" et al
    user_id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)


class Series(Base):
    __tablename__ = 'series'

    series_id = Column(Integer, primary_key=True)
    imdb_id = Column(String(32), nullable=False, unique=True)
    name = Column(String(128), nullable=False)
    desc = Column(String(1024), nullable=False)
    ended = Column(Boolean, default=False)
    active = Column(Boolean, default=True)


class Season(Base):
    __tablename__ = 'season'

    season_id = Column(Integer, primary_key=True)
    season_nr = Column(Integer, nullable=False)

    # season start, season end
    season_start = Column(DateTime)
    season_end = Column(DateTime)

    series_id = Column(
        Integer,
        ForeignKey('series.series_id', onupdate='CASCADE', ondelete='CASCADE'))
    series = relationship("Series", backref=backref('seasons', order_by=series_id))
    UniqueConstraint('series_id', 'season_nr')


class Episode(Base):
    __tablename__ = 'episode'

    episode_id = Column(Integer, primary_key=True)
    episode_nr = Column(Integer, nullable=False)
    name = Column(String(128), nullable=False)
    desc = Column(String(1024))
    airdate = Column(DateTime, nullable=False)

    season_id = Column(
        Integer,
        ForeignKey('season.season_id', onupdate='CASCADE', ondelete='CASCADE'))
    season = relationship("Season", backref=backref('episodes', order_by=episode_id))

    UniqueConstraint('season_id', 'episode_nr')


class UserSeries(Base):
    __tablename__ = 'userseries'
    __table_args__ = (
        PrimaryKeyConstraint('user_id', 'series_id'),
    )
    cur_season = Column(Integer, nullable=False)

    user_id = Column(
        Integer,
        ForeignKey('user.user_id', onupdate='CASCADE', ondelete='CASCADE'))

    series_id = Column(
        Integer,
        ForeignKey('series.series_id', onupdate='CASCADE', ondelete='CASCADE'))


class UserSeason(Base):
    __tablename__ = 'userseason'

    offset = Column(Integer, default=0)
    bits0 = Column(Integer, default=0)
    bits1 = Column(Integer, default=0)
    bits2 = Column(Integer, default=0)
    bits3 = Column(Integer, default=0)

    user_id = Column(
        Integer,
        ForeignKey('user.user_id', onupdate='CASCADE', ondelete='CASCADE'),
        primary_key=True)
    season_id = Column(
        Integer,
        ForeignKey('season.season_id', onupdate='CASCADE', ondelete='CASCADE'),
        primary_key=True)

    user = relationship("User", backref=backref('userseasons', order_by=user_id))


class SeriesMeta(Base):
    __tablename__ = 'seriesmeta'
    series_meta_id = Column(Integer, primary_key=True)
    current_season = Column(Integer, nullable=False)
    next_update = Column(Integer)
