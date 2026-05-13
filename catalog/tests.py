"""
Тесты приложения catalog: список упражнений, детальный просмотр, расчёт 1ПМ.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from catalog.models import Exercise, MuscleGroup
from diary.models import SessionSet, SessionExercise, TrainingSession

User = get_user_model()


def make_user(username='user', password='pass1234'):
    return User.objects.create_user(username=username, password=password)


def make_exercise(name='Жим штанги'):
    return Exercise.objects.create(name=name)


def make_finished_set(user, exercise, weight, reps):
    """Create a completed SessionSet in a finished session."""
    training_session = TrainingSession.objects.create(user=user, is_active=False)
    session_exercise = SessionExercise.objects.create(
        session=training_session, exercise=exercise
    )
    return SessionSet.objects.create(
        session_exercise=session_exercise,
        weight=Decimal(str(weight)),
        reps=reps,
        is_done=True,
    )


class ExerciseListTest(TestCase):
    def test_accessible_without_login(self):
        response = Client().get(reverse('catalog:exercise_list'))
        self.assertEqual(response.status_code, 200)

    def test_shows_all_exercises(self):
        Exercise.objects.create(name='Жим')
        Exercise.objects.create(name='Тяга')
        response = Client().get(reverse('catalog:exercise_list'))
        self.assertEqual(len(response.json()), 2)


class ExerciseStatsOneRMTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = Client()
        self.client.login(username='user', password='pass1234')
        self.exercise = make_exercise()

    def _get(self):
        return self.client.get(
            reverse(
                'catalog:exercise_stats',
                kwargs={'pk': self.exercise.pk},
            )
        )

    def test_one_rm_epley_formula(self):
        make_finished_set(self.user, self.exercise, weight=100, reps=5)
        response = self._get()
        self.assertEqual(response.json()['one_rm'], 116.7)

    def test_one_rm_picks_best_across_all_sets(self):
        make_finished_set(self.user, self.exercise, weight=90, reps=10)
        make_finished_set(self.user, self.exercise, weight=100, reps=5)
        response = self._get()
        self.assertEqual(response.json()['one_rm'], 120.0)

    def test_one_rm_uses_all_time_sets_not_just_recent(self):
        from django.utils import timezone
        from datetime import timedelta
        training_session = TrainingSession.objects.create(user=self.user, is_active=False)
        TrainingSession.objects.filter(pk=training_session.pk).update(
            date=timezone.now() - timedelta(days=120)
        )
        session_exercise = SessionExercise.objects.create(
            session=training_session, exercise=self.exercise
        )
        SessionSet.objects.create(
            session_exercise=session_exercise,
            weight=Decimal('150'),
            reps=1,
            is_done=True,
        )
        response = self._get()
        self.assertEqual(response.json()['one_rm'], 155.0)

    def test_one_rm_is_none_with_no_sets(self):
        response = self._get()
        self.assertIsNone(response.json()['one_rm'])

    def test_anonymous_user_cannot_get_stats(self):
        make_finished_set(self.user, self.exercise, weight=100, reps=5)
        response = Client().get(
            reverse(
                'catalog:exercise_stats',
                kwargs={'pk': self.exercise.pk},
            )
        )
        self.assertEqual(response.status_code, 401)

    def test_only_counts_done_sets(self):
        training_session = TrainingSession.objects.create(user=self.user, is_active=False)
        session_exercise = SessionExercise.objects.create(
            session=training_session, exercise=self.exercise
        )
        SessionSet.objects.create(
            session_exercise=session_exercise,
            weight=Decimal('200'),
            reps=5,
            is_done=False,
        )
        response = self._get()
        self.assertIsNone(response.json()['one_rm'])

    def test_only_counts_finished_sessions(self):
        training_session = TrainingSession.objects.create(user=self.user, is_active=True)
        session_exercise = SessionExercise.objects.create(
            session=training_session, exercise=self.exercise
        )
        SessionSet.objects.create(
            session_exercise=session_exercise,
            weight=Decimal('200'),
            reps=5,
            is_done=True,
        )
        response = self._get()
        self.assertIsNone(response.json()['one_rm'])


class ExerciseStatsBestSetTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = Client()
        self.client.login(username='user', password='pass1234')
        self.exercise = make_exercise()

    def _get(self):
        return self.client.get(
            reverse(
                'catalog:exercise_stats',
                kwargs={'pk': self.exercise.pk},
            )
        )

    def test_best_set_is_heaviest(self):
        make_finished_set(self.user, self.exercise, weight=80, reps=5)
        best = make_finished_set(
            self.user, self.exercise, weight=100, reps=5
        )
        data = self._get().json()
        self.assertEqual(
            Decimal(data['best_set']['weight']), best.weight
        )

    def test_no_best_set_when_no_history(self):
        data = self._get().json()
        self.assertIsNone(data['best_set'])

    def test_does_not_include_other_users_sets(self):
        other = make_user('other', 'pass1234')
        make_finished_set(other, self.exercise, weight=200, reps=5)
        data = self._get().json()
        self.assertIsNone(data['best_set'])


class ExerciseStatsChartTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = Client()
        self.client.login(username='user', password='pass1234')
        self.exercise = make_exercise()

    def _get(self):
        return self.client.get(
            reverse(
                'catalog:exercise_stats',
                kwargs={'pk': self.exercise.pk},
            )
        )

    def test_chart_includes_recent_sessions(self):
        make_finished_set(self.user, self.exercise, weight=100, reps=5)
        data = self._get().json()
        self.assertEqual(len(data['chart_weights']), 1)
        self.assertEqual(data['chart_weights'][0], 100.0)

    def test_chart_excludes_sessions_older_than_3_months(self):
        from django.utils import timezone
        from datetime import timedelta
        training_session = TrainingSession.objects.create(user=self.user, is_active=False)
        TrainingSession.objects.filter(pk=training_session.pk).update(
            date=timezone.now() - timedelta(days=95)
        )
        session_exercise = SessionExercise.objects.create(
            session=training_session, exercise=self.exercise
        )
        SessionSet.objects.create(
            session_exercise=session_exercise,
            weight=Decimal('120'),
            reps=5,
            is_done=True,
        )
        data = self._get().json()
        self.assertEqual(len(data['chart_weights']), 0)

    def test_chart_shows_max_weight_per_session(self):
        training_session = TrainingSession.objects.create(user=self.user, is_active=False)
        session_exercise = SessionExercise.objects.create(
            session=training_session, exercise=self.exercise
        )
        SessionSet.objects.create(
            session_exercise=session_exercise,
            weight=Decimal('80'),
            reps=5,
            is_done=True,
        )
        SessionSet.objects.create(
            session_exercise=session_exercise,
            weight=Decimal('100'),
            reps=5,
            is_done=True,
        )
        data = self._get().json()
        self.assertEqual(data['chart_weights'], [100.0])

    def test_chart_requires_login(self):
        make_finished_set(self.user, self.exercise, weight=100, reps=5)
        response = Client().get(
            reverse(
                'catalog:exercise_stats',
                kwargs={'pk': self.exercise.pk},
            )
        )
        self.assertEqual(response.status_code, 401)

    def test_chart_excludes_undone_sets(self):
        training_session = TrainingSession.objects.create(user=self.user, is_active=False)
        session_exercise = SessionExercise.objects.create(
            session=training_session, exercise=self.exercise
        )
        SessionSet.objects.create(
            session_exercise=session_exercise,
            weight=Decimal('150'),
            reps=5,
            is_done=False,
        )
        data = self._get().json()
        self.assertEqual(len(data['chart_weights']), 0)


class MuscleGroupTest(TestCase):
    def test_muscle_groups_returned(self):
        MuscleGroup.objects.create(name='Грудь')
        MuscleGroup.objects.create(name='Спина')
        response = Client().get(reverse('catalog:muscle_group_list'))
        self.assertEqual(len(response.json()), 2)
