// Amara, universalsubtitles.org
//
// Copyright (C) 2013 Participatory Culture Foundation
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as
// published by the Free Software Foundation, either version 3 of the
// License, or (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Affero General Public License for more details.
//
// You should have received a copy of the GNU Affero General Public License
// along with this program.  If not, see
// http://www.gnu.org/licenses/agpl-3.0.html.

var angular = angular || null;

(function() {
    var module = angular.module('amara.SubtitleEditor.workflow', []);

    /*
     * App-level Workflow object
     */

    Workflow = function(subtitleList) {
        this.subtitleList = subtitleList;
        this.stageOrder = [ 'typing', 'syncing', 'review' ];
        if(this.subtitleList.isComplete()) {
            this.stage = 'review';
        } else {
            this.stage = 'typing';
        }
    }

    Workflow.prototype = {
        stageIndex: function(stage) {
            var stageIndex = this.stageOrder.indexOf(stage);
            if(stageIndex == -1) {
                throw "invalid stage: " + stage;
            }
            return stageIndex;
        },
        currentStageIndex: function() {
            return this.stageIndex(this.stage);
        },
        nextStage: function() {
            return this.stageOrder[this.currentStageIndex() + 1];
        },
        stageCSSClass: function(stage) {
            return this.stage == stage ? 'active' : 'inactive';
        },
        canChangeTo: function(stage) {
            if(this.stageIndex(stage) < this.currentStageIndex()) {
                return true;
            } else if(stage == 'syncing') {
                return (this.subtitleList.length() > 0 &&
                        !this.subtitleList.needsAnyTranscribed());
            } else if(stage == 'review') {
                return this.subtitleList.isComplete();
            } else {
                return true;
            }
        },
        canCompleteStage: function(stage) {
            var nextStage = this.nextStage();
            return nextStage && this.canChangeTo(nextStage);
        },
        completeStage: function(stage) {
            this.stage = this.nextStage();
        },
        changeTo: function(stage) {
            this.stage = stage;
        }
    };
    module.value('Workflow', Workflow);

    module.controller('NormalWorkflowController', ["$scope", "$sce", "EditorData", "VideoPlayer", function($scope, $sce, EditorData, VideoPlayer) {

        // If a blank list of subs start, we automatically start editing
        if ($scope.workflow.subtitleList.length() == 0) {
            var newSub = $scope.workflow.subtitleList.insertSubtitleBefore(null);
            $scope.currentEdit.start(newSub);
        }

        function rewindPlayback() {
            VideoPlayer.pause();
            VideoPlayer.seek(0);
        }

        $scope.$watch('workflow.stage', function(newStage) {
            if(newStage == 'syncing' && !$scope.timelineShown) {
                $scope.toggleTimelineShown();
            }
            rewindPlayback();
        });

        // Hack to make task buttons work, we should replace this when #1667
        // is implemented
        $scope.taskButtons = Boolean(EditorData.task_needs_pane);
    }]);

    module.controller('ReviewWorkflowController', ["$scope", function($scope) {
        $scope.heading = $scope.workMode.heading;
    }]);

    module.controller('WorkflowController', ["$scope", "$controller", 'EditorData',
            function($scope, $controller, EditorData) {
        $scope.workMode = EditorData.work_mode;

        if($scope.workMode.type == 'normal') {
            $controller('NormalWorkflowController', {
                $scope: $scope
            });
        } else if($scope.workMode.type == 'review') {
            $controller('ReviewWorkflowController', {
                $scope: $scope
            });
        }
	$scope.onSubtitleLinkClicked = function($event) {
            var node = $event.target;
            if((node.dataset) && (node.dataset.target)) {
		var subtitle = $scope.workflow.subtitleList.getSubtitleById(node.dataset.target);
		if (subtitle) {
                    $scope.selectSubtitle(subtitle);
		}
            }
        }
        $scope.onEditTitleClicked = function($event) {
            $event.preventDefault();
            $event.stopPropagation();
            $scope.dialogManager.open('metadata');
        }

        $scope.stageLinkClass = function(stage) {
            if($scope.workflow.canChangeTo(stage)) {
                return 'workflowStageLink active';
            } else {
                return 'workflowStageLink';
            }
        }
        $scope.changeStage = function(stage) {
            if($scope.workflow.canChangeTo(stage)) {
                return $scope.workflow.changeTo(stage);
            }
        }
    }]);

})(this);
