from rest_framework import serializers
from catalog.serializers import ExerciseSerializer
from .models import (
    SessionSet, SessionExercise, TrainingSession,
    DefaultProgramSet, DefaultProgramExercise, DefaultProgramDay, DefaultProgram,
)


class SessionSetSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionSet
        fields = ['id', 'weight', 'reps', 'is_done']


class SessionExerciseSerializer(serializers.ModelSerializer):
    exercise = ExerciseSerializer(read_only=True)
    sets = SessionSetSerializer(source='session_sets', many=True, read_only=True)

    class Meta:
        model = SessionExercise
        fields = ['id', 'exercise', 'sets']


class TrainingSessionSerializer(serializers.ModelSerializer):
    exercises = SessionExerciseSerializer(source='session_exercises', many=True, read_only=True)
    day_name = serializers.SerializerMethodField()

    class Meta:
        model = TrainingSession
        fields = ['id', 'date', 'is_active', 'duration_seconds', 'exercises', 'day_name']

    def get_day_name(self, training_session):
        if hasattr(training_session, 'smart_session'):
            return training_session.smart_session.day.name
        if hasattr(training_session, 'default_program_session'):
            return training_session.default_program_session.day.name
        return None


class TrainingSessionListSerializer(serializers.ModelSerializer):
    """Облегчённый сериализатор для списка тренировок — без вложенных упражнений."""
    day_name = serializers.SerializerMethodField()
    exercises_preview = serializers.SerializerMethodField()

    class Meta:
        model = TrainingSession
        fields = ['id', 'date', 'is_active', 'duration_seconds', 'day_name', 'exercises_preview']

    def get_day_name(self, training_session):
        if hasattr(training_session, 'smart_session'):
            return training_session.smart_session.day.name
        if hasattr(training_session, 'default_program_session'):
            return training_session.default_program_session.day.name
        return None

    def get_exercises_preview(self, training_session):
        session_exercises = training_session.session_exercises.select_related('exercise').all()
        return [
            {
                'name': session_exercise.exercise.name,
                'sets_count': session_exercise.session_sets.count(),
            }
            for session_exercise in session_exercises
        ]


class WorkoutProgramSetSerializer(serializers.ModelSerializer):
    class Meta:
        model = DefaultProgramSet
        fields = ['id', 'weight', 'reps']


class WorkoutProgramExerciseSerializer(serializers.ModelSerializer):
    exercise = ExerciseSerializer(read_only=True)
    sets = WorkoutProgramSetSerializer(source='default_program_sets', many=True, read_only=True)

    class Meta:
        model = DefaultProgramExercise
        fields = ['id', 'exercise', 'order', 'sets']


class WorkoutProgramDaySerializer(serializers.ModelSerializer):
    exercises = WorkoutProgramExerciseSerializer(many=True, read_only=True)

    class Meta:
        model = DefaultProgramDay
        fields = ['id', 'name', 'order', 'exercises']


class WorkoutProgramSerializer(serializers.ModelSerializer):
    days = WorkoutProgramDaySerializer(many=True, read_only=True)

    class Meta:
        model = DefaultProgram
        fields = ['id', 'name', 'created_at', 'days']


class WorkoutProgramListSerializer(serializers.ModelSerializer):
    days_count = serializers.IntegerField(source='days.count', read_only=True)

    class Meta:
        model = DefaultProgram
        fields = ['id', 'name', 'created_at', 'days_count']
