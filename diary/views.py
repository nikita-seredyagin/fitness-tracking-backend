from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import F, Max, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Exercise
from .models import (
    DefaultProgram,
    DefaultProgramDay,
    DefaultProgramExercise,
    DefaultProgramSession,
    DefaultProgramSet,
    SessionExercise,
    SessionSet,
    TrainingSession,
)
from .serializers import (
    SessionSetSerializer,
    TrainingSessionListSerializer,
    TrainingSessionSerializer,
    WorkoutProgramDaySerializer,
    WorkoutProgramExerciseSerializer,
    WorkoutProgramListSerializer,
    WorkoutProgramSerializer,
    WorkoutProgramSetSerializer,
)


def _next_order(queryset):
    """Устойчивый к гонкам порядок: max(order) + 1. Использовать внутри transaction.atomic."""
    current_max = queryset.aggregate(value=Max('order'))['value']
    return 0 if current_max is None else current_max + 1


_VOLUME_FILTER = Q(session__session_exercises__session_sets__is_done=True)
_VOLUME_EXPR = (
    F('session__session_exercises__session_sets__weight')
    * F('session__session_exercises__session_sets__reps')
)


class WorkoutListView(APIView):
    def get(self, request):
        queryset = (
            TrainingSession.objects
            .filter(user=request.user, is_active=False)
            .select_related(
                'default_program_session__day',
                'smart_session__day',
            )
            .prefetch_related(
                'session_exercises__exercise',
                'session_exercises__session_sets',
            )
            .order_by('-date')
        )
        return Response(
            TrainingSessionListSerializer(queryset, many=True).data
        )


class WorkoutDetailView(APIView):
    def get(self, request, pk):
        training_session = get_object_or_404(
            TrainingSession.objects.select_related(
                'default_program_session__day',
                'smart_session__day',
            ),
            pk=pk, user=request.user,
        )
        return Response(TrainingSessionSerializer(training_session).data)


class WorkoutFinishView(APIView):
    def post(self, request, pk):
        training_session = get_object_or_404(
            TrainingSession, pk=pk, user=request.user
        )
        if not training_session.is_active:
            return Response(
                {'detail': 'Тренировка уже завершена.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        elapsed = timezone.now() - training_session.date
        training_session.duration_seconds = int(elapsed.total_seconds())
        training_session.is_active = False
        training_session.save(update_fields=['duration_seconds', 'is_active'])
        return Response(TrainingSessionSerializer(training_session).data)


class AddSetToExerciseView(APIView):
    def post(self, request, pk):
        session_exercise = get_object_or_404(
            SessionExercise, pk=pk,
            session__user=request.user,
            session__is_active=True,
        )
        try:
            raw = str(request.data.get('weight', '')).replace(',', '.')
            weight = Decimal(raw)
            reps = int(request.data.get('reps', 10))
            if weight < 0 or reps < 1:
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            return Response(
                {'detail': 'Некорректные данные.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        session_set = SessionSet.objects.create(
            session_exercise=session_exercise, weight=weight, reps=reps
        )
        return Response(
            SessionSetSerializer(session_set).data,
            status=status.HTTP_201_CREATED,
        )


class SetDetailView(APIView):
    def _get_set(self, request, pk):
        return get_object_or_404(
            SessionSet, pk=pk,
            session_exercise__session__user=request.user,
            session_exercise__session__is_active=True,
        )

    def patch(self, request, pk):
        return self._update(request, pk)

    def post(self, request, pk):
        return self._update(request, pk)

    def _update(self, request, pk):
        session_set = self._get_set(request, pk)
        try:
            raw = str(request.data.get('weight', session_set.weight)).replace(',', '.')
            weight = Decimal(raw)
            reps = int(request.data.get('reps', session_set.reps))
            if weight < 0 or reps < 1:
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            return Response(
                {'detail': 'Некорректные данные.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        session_set.weight = weight
        session_set.reps = reps
        session_set.save(update_fields=['weight', 'reps'])
        return Response(SessionSetSerializer(session_set).data)

    def delete(self, request, pk):
        self._get_set(request, pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ToggleSetDoneView(APIView):
    def post(self, request, pk):
        session_set = get_object_or_404(
            SessionSet, pk=pk,
            session_exercise__session__user=request.user,
            session_exercise__session__is_active=True,
        )
        session_set.is_done = not session_set.is_done
        session_set.save(update_fields=['is_done'])
        return Response(SessionSetSerializer(session_set).data)


class WorkoutProgramListView(APIView):
    def get(self, request):
        queryset = DefaultProgram.objects.filter(
            user=request.user
        ).order_by('-created_at')
        return Response(
            WorkoutProgramListSerializer(queryset, many=True).data
        )

    def post(self, request):
        name = request.data.get('name', '').strip()
        if not name:
            return Response(
                {'detail': 'Укажите название.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        default_program = DefaultProgram.objects.create(
            user=request.user, name=name
        )
        return Response(
            WorkoutProgramSerializer(default_program).data,
            status=status.HTTP_201_CREATED,
        )


class WorkoutProgramDetailView(APIView):
    def _get(self, request, pk):
        return get_object_or_404(
            DefaultProgram, pk=pk, user=request.user
        )

    def get(self, request, pk):
        default_program = self._get(request, pk)
        chart_rows = (
            DefaultProgramSession.objects
            .filter(day__program=default_program)
            .select_related('session')
            .annotate(volume=Sum(_VOLUME_EXPR, filter=_VOLUME_FILTER))
            .order_by('session__date')[:12]
        )
        chart_labels = [row.session.date.strftime('%d.%m') for row in chart_rows]
        chart_volumes = [float(row.volume or 0) for row in chart_rows]

        data = WorkoutProgramSerializer(default_program).data
        data['chart_labels'] = chart_labels
        data['chart_volumes'] = chart_volumes
        return Response(data)

    def patch(self, request, pk):
        default_program = self._get(request, pk)
        name = request.data.get('name', '').strip()
        if not name:
            return Response({'detail': 'Укажите название.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(name) > 200:
            return Response({'detail': 'Название не должно превышать 200 символов.'}, status=status.HTTP_400_BAD_REQUEST)
        default_program.name = name
        default_program.save(update_fields=['name'])
        return Response(WorkoutProgramListSerializer(default_program).data)

    def delete(self, request, pk):
        self._get(request, pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkoutProgramDayListView(APIView):
    def post(self, request, pk):
        default_program = get_object_or_404(
            DefaultProgram, pk=pk, user=request.user
        )
        name = request.data.get('name', '').strip()
        if not name:
            return Response(
                {'detail': 'Укажите название.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            day = DefaultProgramDay.objects.create(
                program=default_program,
                name=name,
                order=_next_order(
                    DefaultProgramDay.objects
                    .select_for_update()
                    .filter(program=default_program)
                ),
            )
        return Response(
            WorkoutProgramDaySerializer(day).data,
            status=status.HTTP_201_CREATED,
        )


class WorkoutProgramDayDetailView(APIView):
    def _get(self, request, pk, dpk):
        default_program = get_object_or_404(
            DefaultProgram, pk=pk, user=request.user
        )
        return get_object_or_404(
            DefaultProgramDay, pk=dpk, program=default_program
        )

    def get(self, request, pk, dpk):
        day = self._get(request, pk, dpk)
        return Response(WorkoutProgramDaySerializer(day).data)

    def patch(self, request, pk, dpk):
        day = self._get(request, pk, dpk)
        name = request.data.get('name', '').strip()
        if not name:
            return Response({'detail': 'Укажите название.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(name) > 200:
            return Response({'detail': 'Название не должно превышать 200 символов.'}, status=status.HTTP_400_BAD_REQUEST)
        day.name = name
        day.save(update_fields=['name'])
        return Response(WorkoutProgramDaySerializer(day).data)

    def delete(self, request, pk, dpk):
        self._get(request, pk, dpk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkoutProgramDayAddExerciseView(APIView):
    def post(self, request, pk, dpk):
        default_program = get_object_or_404(
            DefaultProgram, pk=pk, user=request.user
        )
        day = get_object_or_404(
            DefaultProgramDay, pk=dpk, program=default_program
        )
        exercise_id = request.data.get('exercise_id')
        exercise = get_object_or_404(Exercise, pk=exercise_id)
        with transaction.atomic():
            program_exercise = DefaultProgramExercise.objects.create(
                day=day,
                exercise=exercise,
                order=_next_order(
                    DefaultProgramExercise.objects
                    .select_for_update()
                    .filter(day=day)
                ),
            )
        return Response(
            WorkoutProgramExerciseSerializer(program_exercise).data,
            status=status.HTTP_201_CREATED,
        )


class WorkoutProgramDayStartView(APIView):
    @transaction.atomic
    def post(self, request, pk, dpk):
        default_program = get_object_or_404(
            DefaultProgram, pk=pk, user=request.user
        )
        day = get_object_or_404(
            DefaultProgramDay.objects.prefetch_related(
                'exercises__exercise',
                'exercises__default_program_sets',
            ),
            pk=dpk, program=default_program,
        )
        TrainingSession.objects.filter(
            user=request.user, is_active=True
        ).update(is_active=False)

        training_session = TrainingSession.objects.create(user=request.user)
        DefaultProgramSession.objects.create(day=day, session=training_session)

        for program_exercise in day.exercises.all():
            session_exercise = SessionExercise.objects.create(
                session=training_session, exercise=program_exercise.exercise
            )
            session_sets = [
                SessionSet(
                    session_exercise=session_exercise,
                    weight=program_set.weight,
                    reps=program_set.reps,
                    is_done=False,
                )
                for program_set in program_exercise.default_program_sets.all()
            ]
            if session_sets:
                SessionSet.objects.bulk_create(session_sets)
        return Response(
            {'workout_session_id': training_session.pk},
            status=status.HTTP_201_CREATED,
        )


class WorkoutProgramExerciseDeleteView(APIView):
    def delete(self, request, pk):
        program_exercise = get_object_or_404(
            DefaultProgramExercise, pk=pk,
            day__program__user=request.user,
        )
        program_exercise.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkoutProgramExerciseAddSetView(APIView):
    def post(self, request, pk):
        program_exercise = get_object_or_404(
            DefaultProgramExercise, pk=pk,
            day__program__user=request.user,
        )
        try:
            raw = str(request.data.get('weight', '')).replace(',', '.')
            weight = Decimal(raw)
            reps = int(request.data.get('reps', 10))
            if weight < 0 or reps < 1:
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            return Response(
                {'detail': 'Некорректные данные.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        program_set = DefaultProgramSet.objects.create(
            program_exercise=program_exercise, weight=weight, reps=reps
        )
        return Response(
            WorkoutProgramSetSerializer(program_set).data,
            status=status.HTTP_201_CREATED,
        )


class WorkoutProgramSetDetailView(APIView):
    def _get(self, request, pk):
        return get_object_or_404(
            DefaultProgramSet, pk=pk,
            program_exercise__day__program__user=request.user,
        )

    def patch(self, request, pk):
        return self._update(request, pk)

    def post(self, request, pk):
        return self._update(request, pk)

    def _update(self, request, pk):
        program_set = self._get(request, pk)
        try:
            raw = str(request.data.get('weight', program_set.weight)).replace(',', '.')
            weight = Decimal(raw)
            reps = int(request.data.get('reps', program_set.reps))
            if weight < 0 or reps < 1:
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            return Response(
                {'detail': 'Некорректные данные.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        program_set.weight = weight
        program_set.reps = reps
        program_set.save(update_fields=['weight', 'reps'])
        return Response(WorkoutProgramSetSerializer(program_set).data)

    def delete(self, request, pk):
        self._get(request, pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
