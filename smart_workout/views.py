from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import F, Max, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Exercise
from diary.models import SessionExercise, SessionSet, TrainingSession

from .algorithm import (
    _round_to_plate,
    analyze_program_volume,
    apply_deload,
    calculate_progression,
    should_deload,
)
from .models import (
    SmartDay,
    SmartDayExercise,
    SmartProgram,
    SmartProgressionLog,
    SmartSession,
    SmartSet,
)
from .presets import PRESET_PROGRAMS
from .serializers import (
    SmartProgressionLogSerializer,
    SmartSetSerializer,
    SmartWorkoutProgramDayExerciseSerializer,
    SmartWorkoutProgramDayListSerializer,
    SmartWorkoutProgramDaySerializer,
    SmartWorkoutProgramListSerializer,
    SmartWorkoutProgramSerializer,
    SmartWorkoutSessionSerializer,
)

_VOLUME_FILTER = Q(session__session_exercises__session_sets__is_done=True)
_VOLUME_EXPR = (
    F('session__session_exercises__session_sets__weight')
    * F('session__session_exercises__session_sets__reps')
)


def _next_order(queryset):
    current_max = queryset.aggregate(value=Max('order'))['value']
    return 0 if current_max is None else current_max + 1


class SmartWorkoutProgramListView(APIView):
    def get(self, request):
        queryset = SmartProgram.objects.filter(user=request.user)
        return Response(SmartWorkoutProgramListSerializer(queryset, many=True).data)

    def post(self, request):
        name = request.data.get('name', '').strip()
        if not name:
            return Response({'detail': 'Укажите название.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(name) > 200:
            return Response({'detail': 'Название не должно превышать 200 символов.'}, status=status.HTTP_400_BAD_REQUEST)
        smart_program = SmartProgram.objects.create(user=request.user, name=name)
        return Response(SmartWorkoutProgramListSerializer(smart_program).data, status=status.HTTP_201_CREATED)


class SmartWorkoutProgramDetailView(APIView):
    def _get_program(self, request, pk):
        return get_object_or_404(SmartProgram, pk=pk, user=request.user)

    def get(self, request, pk):
        smart_program = self._get_program(request, pk)

        chart_rows = (
            smart_program.sessions
            .select_related('session', 'day')
            .annotate(volume=Sum(_VOLUME_EXPR, filter=_VOLUME_FILTER))
            .order_by('session__date')[:12]
        )
        chart_labels = [row.session.date.strftime('%d.%m') for row in chart_rows]
        chart_volumes = [float(row.volume or 0) for row in chart_rows]

        volume_data, volume_is_actual = analyze_program_volume(smart_program)
        volume_list = [
            {
                'muscle_group': entry['muscle_group'].name,
                'weekly_sets': entry['weekly_sets'],
                'mev': entry['mev'], 'mav': entry['mav'], 'mrv': entry['mrv'],
                'status': entry['status'],
                'sets_to_optimal': entry['sets_to_optimal'],
            }
            for entry in volume_data
        ]

        data = SmartWorkoutProgramSerializer(smart_program).data
        data['chart_labels'] = chart_labels
        data['chart_volumes'] = chart_volumes
        data['volume_data'] = volume_list
        data['volume_is_actual'] = volume_is_actual
        return Response(data)

    def patch(self, request, pk):
        smart_program = self._get_program(request, pk)
        name = request.data.get('name', '').strip()
        if not name:
            return Response({'detail': 'Укажите название.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(name) > 200:
            return Response({'detail': 'Название не должно превышать 200 символов.'}, status=status.HTTP_400_BAD_REQUEST)
        smart_program.name = name
        smart_program.save(update_fields=['name'])
        return Response(SmartWorkoutProgramListSerializer(smart_program).data)

    def delete(self, request, pk):
        self._get_program(request, pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SmartWorkoutProgramDayListView(APIView):
    def post(self, request, pk):
        smart_program = get_object_or_404(SmartProgram, pk=pk, user=request.user)
        name = request.data.get('name', '').strip()
        if not name:
            return Response({'detail': 'Укажите название.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(name) > 200:
            return Response({'detail': 'Название не должно превышать 200 символов.'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            smart_day = SmartDay.objects.create(
                program=smart_program,
                name=name,
                order=_next_order(
                    SmartDay.objects
                    .select_for_update()
                    .filter(program=smart_program)
                ),
            )
        return Response(SmartWorkoutProgramDayListSerializer(smart_day).data, status=status.HTTP_201_CREATED)


class SmartWorkoutProgramDayDetailView(APIView):
    def _get_day(self, request, pk, bpk):
        smart_program = get_object_or_404(SmartProgram, pk=pk, user=request.user)
        return get_object_or_404(SmartDay, pk=bpk, program=smart_program)

    def get(self, request, pk, bpk):
        smart_day = self._get_day(request, pk, bpk)
        return Response(SmartWorkoutProgramDaySerializer(smart_day).data)

    def patch(self, request, pk, bpk):
        smart_day = self._get_day(request, pk, bpk)
        name = request.data.get('name', '').strip()
        if not name:
            return Response({'detail': 'Укажите название.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(name) > 200:
            return Response({'detail': 'Название не должно превышать 200 символов.'}, status=status.HTTP_400_BAD_REQUEST)
        smart_day.name = name
        smart_day.save(update_fields=['name'])
        return Response(SmartWorkoutProgramDayListSerializer(smart_day).data)

    def delete(self, request, pk, bpk):
        self._get_day(request, pk, bpk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SmartWorkoutProgramDayAddExerciseView(APIView):
    def post(self, request, pk, bpk):
        smart_program = get_object_or_404(SmartProgram, pk=pk, user=request.user)
        smart_day = get_object_or_404(SmartDay, pk=bpk, program=smart_program)
        exercise_id = request.data.get('exercise_id')
        exercise = get_object_or_404(Exercise, pk=exercise_id)
        try:
            with transaction.atomic():
                day_exercise = SmartDayExercise.objects.create(
                    day=smart_day,
                    exercise=exercise,
                    order=_next_order(
                        SmartDayExercise.objects
                        .select_for_update()
                        .filter(day=smart_day)
                    ),
                )
        except IntegrityError:
            return Response({'detail': 'Упражнение уже есть в этом дне.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SmartWorkoutProgramDayExerciseSerializer(day_exercise).data, status=status.HTTP_201_CREATED)


class SmartWorkoutProgramDayStartView(APIView):
    @transaction.atomic
    def post(self, request, pk, bpk):
        smart_program = get_object_or_404(SmartProgram, pk=pk, user=request.user)
        smart_day = get_object_or_404(
            SmartDay.objects.prefetch_related('exercises__sets', 'exercises__exercise'),
            pk=bpk, program=smart_program,
        )

        active_smart_session = SmartSession.objects.filter(
            program=smart_program, day=smart_day, session__is_active=True
        ).first()
        if active_smart_session:
            return Response(
                {'detail': 'Тренировка этого дня уже активна.', 'program_session_id': active_smart_session.pk},
                status=status.HTTP_400_BAD_REQUEST,
            )

        TrainingSession.objects.filter(user=request.user, is_active=True).update(is_active=False)

        training_session = TrainingSession.objects.create(user=request.user)
        week_number = SmartSession.objects.filter(program=smart_program, day=smart_day).count() + 1
        smart_session = SmartSession.objects.create(
            program=smart_program, day=smart_day,
            session=training_session, week_number=week_number,
        )

        is_deload = should_deload(smart_session)

        for day_exercise in smart_day.exercises.all():
            day_sets = list(day_exercise.sets.all())
            if not day_sets:
                continue
            session_exercise = SessionExercise.objects.create(
                session=training_session, exercise=day_exercise.exercise
            )
            sets_to_create = day_sets[:max(1, len(day_sets) // 2)] if is_deload else day_sets
            new_sets = [
                SessionSet(
                    session_exercise=session_exercise,
                    weight=apply_deload(smart_set.weight) if is_deload else _round_to_plate(smart_set.weight),
                    reps=smart_set.reps,
                    is_done=False,
                )
                for smart_set in sets_to_create
            ]
            if new_sets:
                SessionSet.objects.bulk_create(new_sets)

        return Response({'program_session_id': smart_session.pk}, status=status.HTTP_201_CREATED)


class SmartWorkoutProgramDayExerciseDeleteView(APIView):
    def delete(self, request, be_pk):
        day_exercise = get_object_or_404(
            SmartDayExercise, pk=be_pk, day__program__user=request.user
        )
        day_exercise.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SmartWorkoutProgramDayExerciseAddSetView(APIView):
    def post(self, request, be_pk):
        day_exercise = get_object_or_404(
            SmartDayExercise, pk=be_pk, day__program__user=request.user
        )
        try:
            weight = Decimal(str(request.data.get('weight', '')).replace(',', '.'))
            reps = int(request.data.get('reps', 10))
            if weight < 0 or reps < 1:
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            return Response({'detail': 'Некорректные данные.'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            smart_set = SmartSet.objects.create(
                day_exercise=day_exercise,
                weight=weight,
                reps=reps,
                order=_next_order(
                    SmartSet.objects
                    .select_for_update()
                    .filter(day_exercise=day_exercise)
                ),
            )
        return Response(SmartSetSerializer(smart_set).data, status=status.HTTP_201_CREATED)


class SmartWorkoutProgramSetDetailView(APIView):
    def _get_set(self, request, bs_pk):
        return get_object_or_404(
            SmartSet, pk=bs_pk, day_exercise__day__program__user=request.user
        )

    def patch(self, request, bs_pk):
        smart_set = self._get_set(request, bs_pk)
        try:
            weight = Decimal(str(request.data.get('weight', smart_set.weight)).replace(',', '.'))
            reps = int(request.data.get('reps', smart_set.reps))
            if weight < 0 or reps < 1:
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            return Response({'detail': 'Некорректные данные.'}, status=status.HTTP_400_BAD_REQUEST)
        smart_set.weight = weight
        smart_set.reps = reps
        smart_set.save(update_fields=['weight', 'reps'])
        return Response(SmartSetSerializer(smart_set).data)

    def delete(self, request, bs_pk):
        self._get_set(request, bs_pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _session_set_to_dict(session_set):
    return {
        'id': session_set.pk,
        'weight': str(session_set.weight),
        'reps': session_set.reps,
        'is_done': session_set.is_done,
    }


def _index_day_exercises_by_exercise(smart_day):
    """Возвращает {exercise_id: day_exercise с prefetch sets}. Один запрос к БД."""
    queryset = smart_day.exercises.select_related('exercise').prefetch_related('sets')
    return {day_exercise.exercise_id: day_exercise for day_exercise in queryset}


class SmartWorkoutSessionDetailView(APIView):
    def get(self, request, spk):
        smart_session = get_object_or_404(
            SmartSession.objects.select_related('session', 'day'),
            pk=spk, session__user=request.user,
        )
        training_session = smart_session.session
        smart_day = smart_session.day

        session_exercises = training_session.session_exercises.select_related(
            'exercise'
        ).prefetch_related('session_sets').all()

        day_exercises_by_id = _index_day_exercises_by_exercise(smart_day)

        exercises_with_targets = []
        for session_exercise in session_exercises:
            day_exercise = day_exercises_by_id.get(session_exercise.exercise_id)
            exercise_sets = list(session_exercise.session_sets.all())
            day_sets = list(day_exercise.sets.all()) if day_exercise else []
            paired = [
                {
                    'set': _session_set_to_dict(exercise_set),
                    'target': {'weight': str(day_sets[i].weight), 'reps': day_sets[i].reps}
                    if i < len(day_sets) else None,
                }
                for i, exercise_set in enumerate(exercise_sets)
            ]
            exercises_with_targets.append({
                'session_exercise_id': session_exercise.pk,
                'exercise': {'id': session_exercise.exercise.pk, 'name': session_exercise.exercise.name},
                'paired_sets': paired,
            })

        is_deload = should_deload(smart_session)
        if is_deload:
            for exercise_entry in exercises_with_targets:
                for pair in exercise_entry['paired_sets']:
                    if pair['target']:
                        pair['target']['weight'] = str(
                            apply_deload(Decimal(pair['target']['weight']))
                        )

        return Response({
            'program_session': SmartWorkoutSessionSerializer(smart_session).data,
            'exercises': exercises_with_targets,
            'is_deload': is_deload,
        })


class SmartWorkoutSessionFinishView(APIView):
    @transaction.atomic
    def post(self, request, spk):
        smart_session = get_object_or_404(
            SmartSession.objects.select_related('session', 'day'),
            pk=spk, session__user=request.user,
        )
        training_session = smart_session.session

        if not training_session.is_active:
            return Response({'detail': 'Тренировка уже завершена.'}, status=status.HTTP_400_BAD_REQUEST)

        elapsed = timezone.now() - training_session.date
        training_session.duration_seconds = int(elapsed.total_seconds())
        training_session.is_active = False
        training_session.save(update_fields=['duration_seconds', 'is_active'])

        smart_day = smart_session.day
        is_deload_week = should_deload(smart_session)

        day_exercises_by_id = _index_day_exercises_by_exercise(smart_day)
        session_exercises = (
            training_session.session_exercises
            .prefetch_related('session_sets')
            .all()
        )

        progression_logs = []
        sets_to_update = []

        for session_exercise in session_exercises:
            day_exercise = day_exercises_by_id.get(session_exercise.exercise_id)
            if not day_exercise:
                continue

            day_sets = list(day_exercise.sets.all())
            old_avg = (
                sum(smart_set.weight for smart_set in day_sets) / len(day_sets)
                if day_sets else Decimal('0.0')
            )

            if is_deload_week:
                reason = 'deload'
                delta = Decimal('0.0')
                new_reps = None
                done_sets = [s for s in session_exercise.session_sets.all() if s.is_done]
                sets_completed = len(done_sets)
                avg_reps = (
                    round(Decimal(sum(session_set.reps for session_set in done_sets)) / Decimal(sets_completed), 1)
                    if sets_completed else Decimal('0.0')
                )
            else:
                reason, delta, new_reps, sets_completed, avg_reps = calculate_progression(
                    day_exercise, session_exercise
                )

            exercise_sets = list(session_exercise.session_sets.all())
            new_weights = []
            for i, smart_set in enumerate(day_sets):
                if not is_deload_week and i < len(exercise_sets) and exercise_sets[i].is_done:
                    base = exercise_sets[i].weight
                else:
                    base = smart_set.weight
                new_weights.append(_round_to_plate(max(Decimal('0.0'), base + delta)))

            new_avg = sum(new_weights) / len(new_weights) if new_weights else old_avg

            if not is_deload_week:
                if new_avg < old_avg:
                    reason = 'decrease'
                elif new_avg > old_avg:
                    reason = 'increase'
                elif new_reps is not None:
                    reason = 'increase'
                else:
                    reason = 'maintain'

            progression_logs.append(SmartProgressionLog(
                day_exercise=day_exercise, session=training_session,
                old_weight=old_avg, new_weight=new_avg,
                reason=reason, sets_completed=sets_completed, avg_reps=avg_reps,
            ))

            for i, smart_set in enumerate(day_sets):
                changed_fields = []
                new_weight = new_weights[i]
                if new_weight != smart_set.weight:
                    smart_set.weight = new_weight
                    changed_fields.append('weight')
                if new_reps is not None and smart_set.reps != new_reps:
                    smart_set.reps = new_reps
                    changed_fields.append('reps')
                if changed_fields:
                    sets_to_update.append((smart_set, changed_fields))

        if progression_logs:
            SmartProgressionLog.objects.bulk_create(progression_logs)

        if sets_to_update:
            update_fields = sorted({f for _, fields in sets_to_update for f in fields})
            SmartSet.objects.bulk_update(
                [smart_set for smart_set, _ in sets_to_update],
                update_fields,
            )

        return Response({'program_session_id': smart_session.pk})


class SmartWorkoutSessionResultsView(APIView):
    def get(self, request, spk):
        smart_session = get_object_or_404(
            SmartSession.objects.select_related('session', 'day'),
            pk=spk, session__user=request.user,
        )
        logs = SmartProgressionLog.objects.filter(
            session=smart_session.session
        ).select_related('day_exercise__exercise')
        return Response({
            'program_session': SmartWorkoutSessionSerializer(smart_session).data,
            'logs': SmartProgressionLogSerializer(logs, many=True).data,
            'is_deload': should_deload(smart_session),
        })


class CreatePresetSmartWorkoutProgramView(APIView):
    @transaction.atomic
    def post(self, request):
        preset_type = request.data.get('type', '')
        preset = PRESET_PROGRAMS.get(preset_type)
        if not preset:
            return Response({'detail': 'Неизвестный тип программы.'}, status=status.HTTP_400_BAD_REQUEST)

        exercise_names = {
            exercise_name
            for day in preset['days']
            for exercise_name, _ in day['exercises']
        }
        exercises_by_name = {
            exercise.name: exercise
            for exercise in Exercise.objects.filter(name__in=exercise_names)
        }

        smart_program = SmartProgram.objects.create(user=request.user, name=preset['name'])

        smart_sets_to_create = []
        for day_order, day_data in enumerate(preset['days'], start=1):
            smart_day = SmartDay.objects.create(
                program=smart_program, name=day_data['name'], order=day_order,
            )
            for exercise_order, (exercise_name, sets) in enumerate(day_data['exercises'], start=1):
                exercise = exercises_by_name.get(exercise_name)
                if exercise is None:
                    continue
                day_exercise = SmartDayExercise.objects.create(
                    day=smart_day, exercise=exercise, order=exercise_order
                )
                for set_order, (weight, reps) in enumerate(sets, start=1):
                    smart_sets_to_create.append(SmartSet(
                        day_exercise=day_exercise,
                        weight=Decimal(weight),
                        reps=reps,
                        order=set_order,
                    ))

        if smart_sets_to_create:
            SmartSet.objects.bulk_create(smart_sets_to_create)

        return Response(SmartWorkoutProgramSerializer(smart_program).data, status=status.HTTP_201_CREATED)


class SmartWorkoutSetUpdateView(APIView):
    """Переключает is_done или обновляет вес/повторы для SessionSet в активной smart-тренировке."""
    def patch(self, request, set_pk):
        session_set = get_object_or_404(
            SessionSet, pk=set_pk,
            session_exercise__session__user=request.user,
            session_exercise__session__is_active=True,
        )

        if session_set.is_done:
            session_set.is_done = False
            session_set.save(update_fields=['is_done'])
        else:
            try:
                weight = Decimal(
                    str(request.data.get('weight', session_set.weight)).replace(',', '.')
                )
                reps = int(request.data.get('reps', session_set.reps))
                if weight < 0 or reps < 1:
                    raise ValueError
            except (InvalidOperation, ValueError, TypeError):
                return Response(
                    {'detail': 'Некорректные данные: вес должен быть >= 0, повторения >= 1.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            session_set.weight = weight
            session_set.reps = reps
            session_set.is_done = True
            session_set.save(update_fields=['weight', 'reps', 'is_done'])

        return Response({
            'id': session_set.pk,
            'weight': str(session_set.weight),
            'reps': session_set.reps,
            'is_done': session_set.is_done,
        })
