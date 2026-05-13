from django.urls import path
from .views import (
    ExerciseListView, ExerciseDetailView,
    ExerciseStatsView, MuscleGroupListView,
)

app_name = 'catalog'

urlpatterns = [
    path('exercises/', 
         ExerciseListView.as_view(),
         name='exercise_list'),
    path('exercises/<int:pk>/',
         ExerciseDetailView.as_view(),
         name='exercise_detail'),
    path('exercises/<int:pk>/stats/', 
         ExerciseStatsView.as_view(),
         name='exercise_stats'),
    path('muscle-groups/',
         MuscleGroupListView.as_view(),
         name='muscle_group_list'),
]
