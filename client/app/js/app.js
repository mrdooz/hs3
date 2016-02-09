'use strict';

/* App Module */

var hs3App = angular.module('hs3App', [
  'ngRoute',
  'hs3Controllers',
  'hs3Services',
  '720kb.tooltips',
  'app.config'
]);

hs3App.config(['$routeProvider',
  function($routeProvider) {
    $routeProvider.
      when('/series', {
        templateUrl: 'partials/series-list.html',
        controller: 'SeriesListCtrl'
      }).
      otherwise({
        redirectTo: '/series'
      });
  }]);

