from rest_framework import serializers
from .models import Exercise, MuscleGroup


class MuscleGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = MuscleGroup
        fields = ['id', 'name', 'description']


class ExerciseSerializer(serializers.ModelSerializer):
    muscle_groups = MuscleGroupSerializer(many=True, read_only=True)

    class Meta:
        model = Exercise
        fields = ['id', 'name', 'description', 'image', 'muscle_groups']
