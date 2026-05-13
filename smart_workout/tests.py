"""
Тесты приложения smart_workout: алгоритм, представления, контроль доступа.
Каждый тест проверяет реальное бизнес-поведение, а не просто HTTP 200.
"""
from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Exercise, MuscleGroup
from diary.models import SessionSet, SessionExercise, TrainingSession
from smart_workout.algorithm import (
    BREAK_DAYS,
    REPS_MAX,
    REPS_RESET,
    apply_deload,
    analyze_program_volume,
    calculate_progression,
    should_deload,
)
from smart_workout.models import (
    SmartDayExercise,
    SmartSet,
    SmartDay,
    SmartSession,
    SmartProgressionLog,
    SmartProgram,
)

User = get_user_model()


def make_user(username='user', password='pass1234'):
    return User.objects.create_user(username=username, password=password)


def make_smart_program(user, name='Программа'):
    return SmartProgram.objects.create(user=user, name=name)


def make_smart_day(smart_program, name='День А'):
    return SmartDay.objects.create(
        program=smart_program, name=name, order=0
    )


def make_day_exercise(smart_day, exercise, sets_data):
    """sets_data: список кортежей (вес, повторы)"""
    day_exercise = SmartDayExercise.objects.create(
        day=smart_day, exercise=exercise, order=0
    )
    for i, (weight, reps) in enumerate(sets_data):
        SmartSet.objects.create(
            day_exercise=day_exercise,
            weight=Decimal(str(weight)),
            reps=reps,
            order=i,
        )
    return day_exercise


def make_session_exercise(training_session, exercise, sets_data):
    """sets_data: список кортежей (вес, повторы, выполнен)"""
    session_exercise = SessionExercise.objects.create(
        session=training_session, exercise=exercise
    )
    for weight, reps, done in sets_data:
        SessionSet.objects.create(
            session_exercise=session_exercise,
            weight=Decimal(str(weight)),
            reps=reps,
            is_done=done,
        )
    return session_exercise


class CalculateProgressionTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.exercise = Exercise.objects.create(name='Жим штанги лёжа')
        smart_program = make_smart_program(self.user)
        smart_day = make_smart_day(smart_program)
        self.smart_day = smart_day
        self.training_session = TrainingSession.objects.create(user=self.user)

    def _day_exercise(self, sets_data, exercise=None):
        exercise = exercise or self.exercise
        return make_day_exercise(self.smart_day, exercise, sets_data)

    def _session_exercise(self, sets_data, exercise=None):
        exercise = exercise or self.exercise
        return make_session_exercise(self.training_session, exercise, sets_data)


    def test_all_sets_done_and_reps_met_returns_increase(self):
        day_exercise = self._day_exercise([(100, 5), (100, 5), (100, 5)])
        session_exercise = self._session_exercise([(100, 5, True), (100, 5, True), (100, 5, True)])
        reason, delta, new_reps, sets_completed, avg_reps = calculate_progression(
            day_exercise, session_exercise
        )
        self.assertEqual(reason, 'increase')
        self.assertEqual(sets_completed, 3)

    def test_upper_body_increment_is_2_point_5_kg(self):
        day_exercise = self._day_exercise([(100, REPS_MAX)])
        session_exercise = self._session_exercise([(100, REPS_MAX, True)])
        _, delta, _, _, _ = calculate_progression(day_exercise, session_exercise)
        self.assertEqual(delta, Decimal('2.5'))

    def test_lower_body_increment_is_5_kg(self):
        exercise = Exercise.objects.create(name='Присед со штангой')
        day_exercise = self._day_exercise([(100, REPS_MAX)], exercise=exercise)
        session_exercise = self._session_exercise([(100, REPS_MAX, True)], exercise=exercise)
        _, delta, _, _, _ = calculate_progression(day_exercise, session_exercise)
        self.assertEqual(delta, Decimal('5.0'))

    def test_squat_keyword_triggers_lower_body(self):
        exercise = Exercise.objects.create(name='squat')
        day_exercise = self._day_exercise([(80, REPS_MAX)], exercise=exercise)
        session_exercise = self._session_exercise([(80, REPS_MAX, True)], exercise=exercise)
        _, delta, _, _, _ = calculate_progression(day_exercise, session_exercise)
        self.assertEqual(delta, Decimal('5.0'))


    def test_all_sets_done_but_reps_short_returns_maintain(self):
        day_exercise = self._day_exercise([(100, 10), (100, 10), (100, 10)])
        session_exercise = self._session_exercise([(100, 7, True), (100, 7, True), (100, 7, True)])
        reason, delta, _, _, _ = calculate_progression(day_exercise, session_exercise)
        self.assertEqual(reason, 'maintain')
        self.assertEqual(delta, Decimal('0.0'))

    def test_exactly_matching_reps_on_boundary_is_increase(self):
        day_exercise = self._day_exercise([(100, 8)])
        session_exercise = self._session_exercise([(100, 8, True)])
        reason, _, _, _, _ = calculate_progression(day_exercise, session_exercise)
        self.assertEqual(reason, 'increase')


    def test_incomplete_sets_returns_decrease(self):
        day_exercise = self._day_exercise([(100, 5), (100, 5), (100, 5)])
        session_exercise = self._session_exercise(
            [(100, 5, True), (100, 5, True), (100, 5, False)]
        )
        reason, delta, _, sets_completed, _ = calculate_progression(day_exercise, session_exercise)
        self.assertEqual(reason, 'decrease')
        self.assertEqual(delta, Decimal('-2.5'))
        self.assertEqual(sets_completed, 2)

    def test_zero_done_sets_returns_decrease_and_zero_avg_reps(self):
        day_exercise = self._day_exercise([(100, 5), (100, 5)])
        session_exercise = self._session_exercise([(100, 5, False), (100, 5, False)])
        reason, delta, _, sets_completed, avg_reps = calculate_progression(
            day_exercise, session_exercise
        )
        self.assertEqual(reason, 'decrease')
        self.assertEqual(sets_completed, 0)
        self.assertEqual(avg_reps, Decimal('0.0'))


    def test_avg_reps_is_mean_of_done_sets(self):
        day_exercise = self._day_exercise([(100, 5), (100, 5), (100, 5)])
        session_exercise = self._session_exercise([(100, 6, True), (100, 5, True), (100, 4, True)])
        _, _, _, _, avg_reps = calculate_progression(day_exercise, session_exercise)
        self.assertEqual(avg_reps, Decimal('5.0'))

    def test_avg_reps_ignores_undone_sets(self):
        day_exercise = self._day_exercise([(100, 10), (100, 10)])
        session_exercise = self._session_exercise([(100, 10, True), (100, 1, False)])
        _, _, _, _, avg_reps = calculate_progression(day_exercise, session_exercise)
        self.assertEqual(avg_reps, Decimal('10.0'))

    def test_no_day_sets_defaults_target_reps_to_reps_max(self):
        day_exercise = SmartDayExercise.objects.create(
            day=self.smart_day, exercise=self.exercise, order=1
        )
        session_exercise = self._session_exercise([(100, REPS_MAX, True)])
        reason, _, _, _, _ = calculate_progression(day_exercise, session_exercise)
        self.assertEqual(reason, 'increase')

    def test_target_reps_is_average_of_day_sets(self):
        day_exercise = self._day_exercise([(100, 5), (100, 5), (100, 10)])
        session_exercise = self._session_exercise([(100, 7, True), (100, 7, True), (100, 7, True)])
        reason, _, _, _, _ = calculate_progression(day_exercise, session_exercise)
        self.assertEqual(reason, 'increase')


    def test_reps_increase_when_below_ceiling(self):
        day_exercise = self._day_exercise([(100, 8)])
        session_exercise = self._session_exercise([(100, 8, True)])
        reason, delta, new_reps, _, _ = calculate_progression(day_exercise, session_exercise)
        self.assertEqual(reason, 'increase')
        self.assertEqual(delta, Decimal('0.0'))
        self.assertEqual(new_reps, 9)

    def test_weight_increase_when_reps_hit_ceiling(self):
        day_exercise = self._day_exercise([(100, REPS_MAX)])
        session_exercise = self._session_exercise([(100, REPS_MAX, True)])
        reason, delta, new_reps, _, _ = calculate_progression(day_exercise, session_exercise)
        self.assertEqual(reason, 'increase')
        self.assertGreater(delta, Decimal('0.0'))
        self.assertEqual(new_reps, REPS_RESET)

    def test_high_rep_exercise_increases_weight_without_touching_reps(self):
        day_exercise = self._day_exercise([(40, 15)])
        session_exercise = self._session_exercise([(40, 15, True)])
        _, delta, new_reps, _, _ = calculate_progression(day_exercise, session_exercise)
        self.assertGreater(delta, Decimal('0.0'))
        self.assertIsNone(new_reps)

    def test_no_reps_change_when_maintain(self):
        day_exercise = self._day_exercise([(100, 10)])
        session_exercise = self._session_exercise([(100, 7, True)])
        _, _, new_reps, _, _ = calculate_progression(day_exercise, session_exercise)
        self.assertIsNone(new_reps)

    def test_no_reps_change_when_decrease(self):
        day_exercise = self._day_exercise([(100, 8), (100, 8)])
        session_exercise = self._session_exercise([(100, 8, True), (100, 8, False)])
        _, _, new_reps, _, _ = calculate_progression(day_exercise, session_exercise)
        self.assertIsNone(new_reps)


class ApplyDeloadTest(TestCase):
    def test_returns_60_percent(self):
        self.assertEqual(apply_deload(Decimal('100.0')), Decimal('60.0'))

    def test_rounds_to_nearest_plate(self):
        self.assertEqual(apply_deload(Decimal('83.0')), Decimal('50.0'))

    def test_zero_stays_zero(self):
        self.assertEqual(apply_deload(Decimal('0.0')), Decimal('0.0'))

    def test_large_weight(self):
        self.assertEqual(apply_deload(Decimal('200.0')), Decimal('120.0'))


class ShouldDeloadTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.smart_program = make_smart_program(self.user)
        self.smart_day = make_smart_day(self.smart_program)

    def _make_smart_session(self, week_number, days_ago=0):
        """Create a SmartSession whose TrainingSession is `days_ago` old."""
        training_session = TrainingSession.objects.create(user=self.user)
        if days_ago:
            TrainingSession.objects.filter(pk=training_session.pk).update(
                date=timezone.now() - timedelta(days=days_ago)
            )
            training_session.refresh_from_db()
        return SmartSession.objects.create(
            program=self.smart_program,
            day=self.smart_day,
            session=training_session,
            week_number=week_number,
        )

    def test_4th_session_is_deload(self):
        smart_session = self._make_smart_session(4)
        self.assertTrue(should_deload(smart_session))

    def test_8th_session_is_deload(self):
        smart_session = self._make_smart_session(8)
        self.assertTrue(should_deload(smart_session))

    def test_1st_session_is_not_deload(self):
        smart_session = self._make_smart_session(1)
        self.assertFalse(should_deload(smart_session))

    def test_2nd_session_is_not_deload(self):
        smart_session = self._make_smart_session(2)
        self.assertFalse(should_deload(smart_session))

    def test_3rd_session_is_not_deload(self):
        smart_session = self._make_smart_session(3)
        self.assertFalse(should_deload(smart_session))

    def test_no_deload_when_gap_exceeds_break_days(self):
        self._make_smart_session(week_number=3, days_ago=BREAK_DAYS + 5)
        current = self._make_smart_session(week_number=4, days_ago=0)
        self.assertFalse(should_deload(current))

    def test_deload_still_triggers_after_short_break(self):
        self._make_smart_session(week_number=3, days_ago=5)
        current = self._make_smart_session(week_number=4, days_ago=0)
        self.assertTrue(should_deload(current))

    def test_one_day_under_threshold_still_deloads(self):
        self._make_smart_session(week_number=3, days_ago=BREAK_DAYS - 1)
        current = self._make_smart_session(week_number=4, days_ago=0)
        self.assertTrue(should_deload(current))

    def test_first_session_no_previous_uses_week_number(self):
        smart_session = self._make_smart_session(week_number=4)
        self.assertTrue(should_deload(smart_session))

    def test_only_looks_at_same_day(self):
        other_day = SmartDay.objects.create(
            program=self.smart_program, name='День Б', order=1
        )
        training_session = TrainingSession.objects.create(user=self.user)
        TrainingSession.objects.filter(pk=training_session.pk).update(
            date=timezone.now() - timedelta(days=BREAK_DAYS + 5)
        )
        training_session.refresh_from_db()
        SmartSession.objects.create(
            program=self.smart_program,
            day=other_day,
            session=training_session,
            week_number=3,
        )
        current = self._make_smart_session(week_number=4, days_ago=0)
        self.assertTrue(should_deload(current))


class AnalyzeProgramVolumeTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.smart_program = make_smart_program(self.user)
        self.smart_day = make_smart_day(self.smart_program)
        self.mg_chest = MuscleGroup.objects.create(name='грудь')
        self.mg_shoulders = MuscleGroup.objects.create(name='Дельтовидные мышцы')
        self.exercise = Exercise.objects.create(name='Жим')
        self.exercise.muscle_groups.add(self.mg_chest)

    def _add_day_sets(self, count):
        day_exercise = SmartDayExercise.objects.create(
            day=self.smart_day, exercise=self.exercise, order=0
        )
        for i in range(count):
            SmartSet.objects.create(
                day_exercise=day_exercise,
                weight=Decimal('100'),
                reps=5,
                order=i,
            )
        return day_exercise

    def _make_actual_session(self, done_count, days_ago=0):
        """Create a SmartSession with `done_count` completed SessionSets."""
        training_session = TrainingSession.objects.create(user=self.user, is_active=False)
        if days_ago:
            TrainingSession.objects.filter(pk=training_session.pk).update(
                date=timezone.now() - timedelta(days=days_ago)
            )
        SmartSession.objects.create(
            program=self.smart_program,
            day=self.smart_day,
            session=training_session,
            week_number=1,
        )
        session_exercise = SessionExercise.objects.create(
            session=training_session, exercise=self.exercise
        )
        for _ in range(done_count):
            SessionSet.objects.create(
                session_exercise=session_exercise,
                weight=Decimal('100'),
                reps=5,
                is_done=True,
            )
        return training_session


    def test_no_sessions_uses_planned_dayset_count(self):
        self._add_day_sets(6)
        results, is_actual = analyze_program_volume(self.smart_program)
        self.assertFalse(is_actual)
        self.assertEqual(results[0]['weekly_sets'], 6)

    def test_recent_session_uses_actual_done_count(self):
        self._add_day_sets(10)
        self._make_actual_session(done_count=5, days_ago=0)
        results, is_actual = analyze_program_volume(self.smart_program)
        self.assertTrue(is_actual)
        self.assertEqual(results[0]['weekly_sets'], 5)

    def test_session_older_than_7_days_falls_back_to_planned(self):
        self._add_day_sets(10)
        self._make_actual_session(done_count=3, days_ago=8)
        results, is_actual = analyze_program_volume(self.smart_program)
        self.assertFalse(is_actual)
        self.assertEqual(results[0]['weekly_sets'], 10)

    def test_multiple_recent_sessions_accumulate_done_sets(self):
        self._add_day_sets(10)
        self._make_actual_session(done_count=3, days_ago=1)
        self._make_actual_session(done_count=4, days_ago=3)
        results, is_actual = analyze_program_volume(self.smart_program)
        self.assertTrue(is_actual)
        self.assertEqual(results[0]['weekly_sets'], 7)

    def test_undone_sets_not_counted_in_actual(self):
        self._add_day_sets(10)
        training_session = TrainingSession.objects.create(user=self.user, is_active=False)
        SmartSession.objects.create(
            program=self.smart_program,
            day=self.smart_day,
            session=training_session,
            week_number=1,
        )
        session_exercise = SessionExercise.objects.create(
            session=training_session, exercise=self.exercise
        )
        SessionSet.objects.create(
            session_exercise=session_exercise,
            weight=Decimal('100'),
            reps=5,
            is_done=True,
        )
        SessionSet.objects.create(
            session_exercise=session_exercise,
            weight=Decimal('100'),
            reps=5,
            is_done=False,
        )
        results, _ = analyze_program_volume(self.smart_program)
        self.assertEqual(results[0]['weekly_sets'], 1)


    def test_status_low_when_below_mev(self):
        self._add_day_sets(6)
        results, _ = analyze_program_volume(self.smart_program)
        self.assertEqual(results[0]['status'], 'low')

    def test_status_optimal_at_mev(self):
        self._add_day_sets(10)
        results, _ = analyze_program_volume(self.smart_program)
        self.assertEqual(results[0]['status'], 'optimal')

    def test_status_optimal_between_mev_and_mav(self):
        self._add_day_sets(13)
        results, _ = analyze_program_volume(self.smart_program)
        self.assertEqual(results[0]['status'], 'optimal')

    def test_status_high_between_mav_and_mrv(self):
        self._add_day_sets(20)
        results, _ = analyze_program_volume(self.smart_program)
        self.assertEqual(results[0]['status'], 'high')

    def test_status_danger_above_mrv(self):
        self._add_day_sets(25)
        results, _ = analyze_program_volume(self.smart_program)
        self.assertEqual(results[0]['status'], 'danger')


    def test_sets_to_optimal_equals_deficit_below_mev(self):
        self._add_day_sets(6)
        results, _ = analyze_program_volume(self.smart_program)
        self.assertEqual(results[0]['sets_to_optimal'], 4)

    def test_sets_to_optimal_is_zero_when_optimal(self):
        self._add_day_sets(12)
        results, _ = analyze_program_volume(self.smart_program)
        self.assertEqual(results[0]['sets_to_optimal'], 0)

    def test_sets_to_optimal_is_zero_when_over(self):
        self._add_day_sets(25)
        results, _ = analyze_program_volume(self.smart_program)
        self.assertEqual(results[0]['sets_to_optimal'], 0)


    def test_empty_program_returns_empty_list(self):
        results, is_actual = analyze_program_volume(self.smart_program)
        self.assertEqual(results, [])
        self.assertFalse(is_actual)

    def test_results_sorted_by_muscle_group_name(self):
        exercise2 = Exercise.objects.create(name='Жим гантелей')
        exercise2.muscle_groups.add(self.mg_shoulders)
        day_exercise2 = SmartDayExercise.objects.create(
            day=self.smart_day, exercise=exercise2, order=1
        )
        SmartSet.objects.create(
            day_exercise=day_exercise2, weight=Decimal('30'), reps=12, order=0
        )
        self._add_day_sets(5)
        results, _ = analyze_program_volume(self.smart_program)
        names = [entry['muscle_group'].name for entry in results]
        self.assertEqual(names, sorted(names))


class StartSmartWorkoutTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = Client()
        self.client.login(username='user', password='pass1234')

        self.exercise = Exercise.objects.create(name='Жим штанги')
        self.smart_program = make_smart_program(self.user)
        self.smart_day = make_smart_day(self.smart_program)
        self.day_exercise = SmartDayExercise.objects.create(
            day=self.smart_day, exercise=self.exercise, order=0
        )
        for i, (weight, reps) in enumerate([(100, 5), (100, 5), (100, 5)]):
            SmartSet.objects.create(
                day_exercise=self.day_exercise,
                weight=Decimal(str(weight)),
                reps=reps,
                order=i,
            )

    def _start(self):
        url = reverse(
            'smart_workout:start_day_workout',
            kwargs={'pk': self.smart_program.pk, 'bpk': self.smart_day.pk},
        )
        return self.client.post(url)

    def test_creates_active_training_session(self):
        self._start()
        queryset = TrainingSession.objects.filter(user=self.user, is_active=True)
        self.assertEqual(queryset.count(), 1)

    def test_session_sets_match_day_sets_weight_and_reps(self):
        self._start()
        training_session = TrainingSession.objects.get(user=self.user, is_active=True)
        session_exercise = SessionExercise.objects.get(
            session=training_session, exercise=self.exercise
        )
        session_sets = list(session_exercise.session_sets.order_by('pk'))
        self.assertEqual(len(session_sets), 3)
        self.assertEqual(session_sets[0].weight, Decimal('100.0'))
        self.assertEqual(session_sets[0].reps, 5)
        self.assertFalse(session_sets[0].is_done)

    def test_all_session_sets_start_as_not_done(self):
        self._start()
        training_session = TrainingSession.objects.get(user=self.user, is_active=True)
        done_count = SessionSet.objects.filter(
            session_exercise__session=training_session, is_done=True
        ).count()
        self.assertEqual(done_count, 0)

    def test_closes_existing_active_session(self):
        existing = TrainingSession.objects.create(user=self.user, is_active=True)
        self._start()
        existing.refresh_from_db()
        self.assertFalse(existing.is_active)

    def test_returns_program_session_id(self):
        response = self._start()
        self.assertEqual(response.status_code, 201)
        smart_session = SmartSession.objects.get(
            program=self.smart_program, day=self.smart_day
        )
        self.assertEqual(response.json()['program_session_id'], smart_session.pk)

    def test_week_number_increments_per_day(self):
        self._start()
        smart_session_1 = SmartSession.objects.get(
            program=self.smart_program, day=self.smart_day
        )
        self.assertEqual(smart_session_1.week_number, 1)
        TrainingSession.objects.filter(is_active=True).update(is_active=False)
        self._start()
        smart_session_2 = SmartSession.objects.filter(
            program=self.smart_program, day=self.smart_day
        ).order_by('-pk').first()
        self.assertEqual(smart_session_2.week_number, 2)

    def test_deload_week_halves_sets(self):
        for i in range(3):
            training_session = TrainingSession.objects.create(
                user=self.user, is_active=False
            )
            SmartSession.objects.create(
                program=self.smart_program, day=self.smart_day,
                session=training_session, week_number=i + 1,
            )
        self._start()
        training_session = TrainingSession.objects.get(user=self.user, is_active=True)
        session_exercise = SessionExercise.objects.get(
            session=training_session, exercise=self.exercise
        )
        self.assertEqual(session_exercise.session_sets.count(), 1)

    def test_deload_week_applies_60_percent_weight(self):
        for i in range(3):
            training_session = TrainingSession.objects.create(
                user=self.user, is_active=False
            )
            SmartSession.objects.create(
                program=self.smart_program, day=self.smart_day,
                session=training_session, week_number=i + 1,
            )
        self._start()
        training_session = TrainingSession.objects.get(user=self.user, is_active=True)
        session_exercise = SessionExercise.objects.get(
            session=training_session, exercise=self.exercise
        )
        deload_set = session_exercise.session_sets.first()
        self.assertEqual(deload_set.weight, Decimal('60.0'))

    def test_requires_login(self):
        self.client.logout()
        url = reverse(
            'smart_workout:start_day_workout',
            kwargs={'pk': self.smart_program.pk, 'bpk': self.smart_day.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 401)


class FinishSmartSessionTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = Client()
        self.client.login(username='user', password='pass1234')

        self.exercise = Exercise.objects.create(name='Жим штанги лёжа')
        self.smart_program = make_smart_program(self.user)
        self.smart_day = make_smart_day(self.smart_program)
        self.day_exercise = SmartDayExercise.objects.create(
            day=self.smart_day, exercise=self.exercise, order=0
        )
        self.smart_set = SmartSet.objects.create(
            day_exercise=self.day_exercise,
            weight=Decimal('100.0'),
            reps=5,
            order=0,
        )
        self.training_session = TrainingSession.objects.create(user=self.user)
        self.smart_session = SmartSession.objects.create(
            program=self.smart_program, day=self.smart_day,
            session=self.training_session, week_number=1,
        )
        self.session_exercise = SessionExercise.objects.create(
            session=self.training_session, exercise=self.exercise
        )

    def _add_set(self, weight, reps=5, is_done=True):
        return SessionSet.objects.create(
            session_exercise=self.session_exercise,
            weight=Decimal(str(weight)),
            reps=reps,
            is_done=is_done,
        )

    def _finish(self):
        url = reverse(
            'smart_workout:finish_program_session',
            kwargs={'spk': self.smart_session.pk},
        )
        return self.client.post(url)

    def test_session_marked_inactive(self):
        self._add_set(100)
        self._finish()
        self.training_session.refresh_from_db()
        self.assertFalse(self.training_session.is_active)

    def test_duration_seconds_saved(self):
        self._add_set(100)
        self._finish()
        self.training_session.refresh_from_db()
        self.assertIsNotNone(self.training_session.duration_seconds)
        self.assertGreaterEqual(self.training_session.duration_seconds, 0)

    def test_returns_program_session_id(self):
        self._add_set(100)
        response = self._finish()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['program_session_id'], self.smart_session.pk
        )

    def test_delta_applied_to_actual_weight_not_plan(self):
        self.smart_set.reps = REPS_MAX
        self.smart_set.save()
        self._add_set(110, reps=REPS_MAX)
        self._finish()
        self.smart_set.refresh_from_db()
        self.assertEqual(self.smart_set.weight, Decimal('112.5'))

    def test_user_lifts_less_and_completes_all_sets_gives_decrease(self):
        self._add_set(80, reps=5)
        self._finish()
        log = SmartProgressionLog.objects.get(session=self.training_session)
        self.assertEqual(log.reason, 'decrease')
        self.smart_set.refresh_from_db()
        self.assertEqual(self.smart_set.weight, Decimal('80.0'))

    def test_user_lifts_more_than_plan_reason_is_increase(self):
        self._add_set(110, reps=5)
        self._finish()
        log = SmartProgressionLog.objects.get(session=self.training_session)
        self.assertEqual(log.reason, 'increase')

    def test_reason_is_maintain_when_reps_short(self):
        self._add_set(100, reps=3)
        self._finish()
        log = SmartProgressionLog.objects.get(session=self.training_session)
        self.assertEqual(log.reason, 'maintain')

    def test_undone_set_uses_smart_set_weight_as_base(self):
        self._add_set(110, reps=5, is_done=False)
        self._finish()
        self.smart_set.refresh_from_db()
        self.assertEqual(self.smart_set.weight, Decimal('97.5'))

    def test_progression_log_records_old_and_new_weight(self):
        self.smart_set.reps = REPS_MAX
        self.smart_set.save()
        self._add_set(100, reps=REPS_MAX)
        self._finish()
        log = SmartProgressionLog.objects.get(session=self.training_session)
        self.assertEqual(log.old_weight, Decimal('100.0'))
        self.assertEqual(log.new_weight, Decimal('102.5'))

    def test_progression_log_records_sets_completed(self):
        self._add_set(100)
        self._add_set(100, is_done=False)
        self._finish()
        log = SmartProgressionLog.objects.get(session=self.training_session)
        self.assertEqual(log.sets_completed, 1)

    def test_deload_week_smart_set_weight_unchanged(self):
        self.smart_session.week_number = 4
        self.smart_session.save()
        self._add_set(60, reps=5)
        self._finish()
        self.smart_set.refresh_from_db()
        self.assertEqual(self.smart_set.weight, Decimal('100.0'))

    def test_deload_week_reason_is_deload(self):
        self.smart_session.week_number = 4
        self.smart_session.save()
        self._add_set(60)
        self._finish()
        log = SmartProgressionLog.objects.get(session=self.training_session)
        self.assertEqual(log.reason, 'deload')

    def test_multiple_exercises_each_get_progression_log(self):
        exercise2 = Exercise.objects.create(name='Тяга')
        day_exercise2 = SmartDayExercise.objects.create(
            day=self.smart_day, exercise=exercise2, order=1
        )
        SmartSet.objects.create(
            day_exercise=day_exercise2, weight=Decimal('80'), reps=8, order=0
        )
        session_exercise2 = SessionExercise.objects.create(
            session=self.training_session, exercise=exercise2
        )
        SessionSet.objects.create(
            session_exercise=session_exercise2,
            weight=Decimal('80'),
            reps=8,
            is_done=True,
        )
        self._add_set(100)
        self._finish()
        self.assertEqual(
            SmartProgressionLog.objects.filter(
                session=self.training_session
            ).count(),
            2,
        )

    def test_smart_set_reps_increase_when_below_ceiling(self):
        self.smart_set.reps = 8
        self.smart_set.save()
        self._add_set(100, reps=8)
        self._finish()
        self.smart_set.refresh_from_db()
        self.assertEqual(self.smart_set.reps, 9)
        self.assertEqual(self.smart_set.weight, Decimal('100.0'))

    def test_smart_set_reps_reset_and_weight_up_at_ceiling(self):
        self.smart_set.reps = REPS_MAX
        self.smart_set.save()
        self._add_set(100, reps=REPS_MAX)
        self._finish()
        self.smart_set.refresh_from_db()
        self.assertEqual(self.smart_set.reps, REPS_RESET)
        self.assertEqual(self.smart_set.weight, Decimal('102.5'))

    def test_deload_week_does_not_change_reps(self):
        self.smart_set.reps = 8
        self.smart_set.save()
        self.smart_session.week_number = 4
        self.smart_session.save()
        self._add_set(60, reps=8)
        self._finish()
        self.smart_set.refresh_from_db()
        self.assertEqual(self.smart_set.reps, 8)

    def test_requires_login(self):
        self.client.logout()
        url = reverse(
            'smart_workout:finish_program_session',
            kwargs={'spk': self.smart_session.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 401)


class SmartProgramAccessControlTest(TestCase):
    def setUp(self):
        self.owner = make_user('owner', 'pass1234')
        self.other = make_user('other', 'pass1234')
        self.client = Client()
        self.client.login(username='other', password='pass1234')

        smart_program = make_smart_program(self.owner)
        smart_day = make_smart_day(smart_program)
        exercise = Exercise.objects.create(name='Жим')
        day_exercise = SmartDayExercise.objects.create(
            day=smart_day, exercise=exercise, order=0
        )
        SmartSet.objects.create(
            day_exercise=day_exercise, weight=Decimal('100'), reps=5, order=0
        )

        self.owner_training_session = TrainingSession.objects.create(user=self.owner)
        self.smart_session = SmartSession.objects.create(
            program=smart_program, day=smart_day,
            session=self.owner_training_session, week_number=1,
        )

    def test_other_user_cannot_view_smart_session(self):
        url = reverse(
            'smart_workout:program_workout_detail',
            kwargs={'spk': self.smart_session.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_other_user_cannot_finish_smart_session(self):
        url = reverse(
            'smart_workout:finish_program_session',
            kwargs={'spk': self.smart_session.pk},
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_other_user_cannot_view_program_detail(self):
        smart_program = SmartProgram.objects.filter(user=self.owner).first()
        url = reverse(
            'smart_workout:program_detail', kwargs={'pk': smart_program.pk}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
