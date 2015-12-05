'use strict';

/* Services */

var hs3Services = angular.module('hs3Services', ['ngResource']);

hs3Services.factory('SeriesList', ['$resource',
  function($resource) {
    return $resource('http://localhost:5000/user/info:userId', {}, {
      query: {method:'GET', isArray:true}
    });
  }]);

hs3Services.factory('User', ['$http',
  function($http) {
    return {
        'setSeason': function(series_id, season_nr) {
            return $http({
                method: 'POST',
                data: { series_id: series_id, season_nr: season_nr},
                url: 'http://localhost:5000/user/set_season'}
            );
        },
        'updateEpisodes': function(season_id, adds, dels)
        {
            return $http({
                method: 'POST',
                data: { season_id: season_id, add: adds, del: dels},
                url: 'http://localhost:5000/user/update_episodes'}
            );
        },
    };
  }]);
