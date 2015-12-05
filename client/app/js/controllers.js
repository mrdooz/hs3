'use strict';

/* Controllers */

var hs3Controllers = angular.module('hs3Controllers', []);

hs3Controllers.controller('SeriesListCtrl', ['$scope', 'SeriesList', 'User',
  function($scope, SeriesList, User) {

    $scope.now = (new Date()).getTime() / 1000.0;
    $scope.series = SeriesList.query({}, function() {
      var tmp = [];
      _.each($scope.series, function(e) {
        var seen = {};
        _.each(e.seen, function(elem) {
          seen[elem] = true;
        });

        tmp.push({ 
          name: e.name,
          series_id: e.id,
          imdb_id: e.imdb_id,
          episodes: _.range(1, e.num_episodes+1),
          episode_descs: e.episode_descs,
          episode_dates: e.episode_dates,
          seen: seen,
          seasons: _.range(1, e.num_seasons+1),
          cur_season: e.cur_season,
          season_id: e.season_id,
        });
      });
      $scope.series = tmp;
    });

    var findSeries = function(series_id) {
      return _.find($scope.series, function(e) { return e.series_id == series_id });
    };

    $scope.setSeason = function(series_id, season_nr) {
      User.setSeason(series_id, season_nr).then(
          function successCallback(response) {

            var data = response.data;
            var seen = {};
            _.each(data.seen, function(elem) {
              seen[elem] = true;
            });

            var s = findSeries(series_id);
            s.cur_season = season_nr;
            s.season_id = data.season_id;
            s.episodes = _.range(1, data.num_episodes+1);
            s.episode_descs = data.episode_descs;
            s.episode_dates = data.episode_dates;
            s.seen = seen;
          },
          function errorCallback(response) {
              console.log('fail');
          }
      );
    };

    $scope.toggleEpisode = function(series_id, season_id, episode) {
      var s = findSeries(series_id);
      var to_add = !s.seen[episode];
      var adds = [];
      var dels = [];
      if (to_add) {
        adds.push(episode);
      } else {
        dels.push(episode);
      }

      console.log('adds: ', adds, ' dels: ', dels);

      User.updateEpisodes(season_id, adds, dels).then(
          function successCallback(response) {
            if (to_add) {
              s.seen[episode] = true;
            } else {
              delete s.seen[episode];
            }
          },
          function errorCallback(response) {
          }
      );

    };

  }]);

