from rest_framework import serializers
from catalog.serializers import ExerciseSerializer
from .models import (
    SmartSet, SmartDayExercise, SmartDay,
    SmartProgram, SmartSession, SmartProgressionLog,
)


class SmartSetSerializer(serializers.ModelSerializer):
    class Meta:
        model = SmartSet
        fields = ['id', 'weight', 'reps', 'order']


class SmartWorkoutProgramDayExerciseSerializer(serializers.ModelSerializer):
    exercise = ExerciseSerializer(read_only=True)
    sets = SmartSetSerializer(many=True, read_only=True)

    class Meta:
        model = SmartDayExercise
        fields = ['id', 'exercise', 'order', 'sets']


class SmartWorkoutProgramDaySerializer(serializers.ModelSerializer):
    exercises = SmartWorkoutProgramDayExerciseSerializer(many=True, read_only=True)
    last_session_date = serializers.SerializerMethodField()

    class Meta:
        model = SmartDay
        fields = ['id', 'name', 'order', 'exercises', 'last_session_date']

    def get_last_session_date(self, smart_day):
        last_smart_session = (
            SmartSession.objects
            .filter(day=smart_day, session__is_active=False)
            .order_by('-session__date')
            .select_related('session')
            .first()
        )
        if last_smart_session:
            return last_smart_session.session.date.date().isoformat()
        return None


class SmartWorkoutProgramDayListSerializer(serializers.ModelSerializer):
    exercises_count = serializers.IntegerField(source='exercises.count', read_only=True)

    class Meta:
        model = SmartDay
        fields = ['id', 'name', 'order', 'exercises_count']


class SmartWorkoutProgramSerializer(serializers.ModelSerializer):
    days = SmartWorkoutProgramDaySerializer(many=True, read_only=True)

    class Meta:
        model = SmartProgram
        fields = ['id', 'name', 'is_active', 'created_at', 'days']


class SmartWorkoutProgramListSerializer(serializers.ModelSerializer):
    days_count = serializers.IntegerField(source='days.count', read_only=True)

    class Meta:
        model = SmartProgram
        fields = ['id', 'name', 'is_active', 'created_at', 'days_count']


class SmartProgressionLogSerializer(serializers.ModelSerializer):
    exercise_name = serializers.CharField(source='day_exercise.exercise.name', read_only=True)

    class Meta:
        model = SmartProgressionLog
        fields = ['id', 'exercise_name', 'old_weight', 'new_weight', 'reason', 'sets_completed', 'avg_reps']


class SmartWorkoutSessionSerializer(serializers.ModelSerializer):
    day_name = serializers.CharField(source='day.name', read_only=True)
    training_session_id = serializers.IntegerField(source='session.id', read_only=True)
    is_deload = serializers.SerializerMethodField()

    class Meta:
        model = SmartSession
        fields = ['id', 'week_number', 'day_name', 'training_session_id', 'is_deload']

    def get_is_deload(self, smart_session):
        from .algorithm import should_deload
        return should_deload(smart_session)
