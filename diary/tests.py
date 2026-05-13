"""
Tests for diary app: training sessions, default programs, set management.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from catalog.models import Exercise
from diary.models import (
    SessionSet,
    DefaultProgramDay,
    DefaultProgramExercise,
    DefaultProgramSession,
    DefaultProgramSet,
    SessionExercise,
    TrainingSession,
    DefaultProgram,
)

User = get_user_model()


def make_user(username='user', password='pass1234'):
    return User.objects.create_user(username=username, password=password)


def make_exercise(name='Жим штанги'):
    return Exercise.objects.create(name=name)


def make_training_session(user, is_active=True):
    return TrainingSession.objects.create(user=user, is_active=is_active)


def make_session_exercise(training_session, exercise):
    return SessionExercise.objects.create(session=training_session, exercise=exercise)


def make_session_set(session_exercise, weight=100, reps=5, is_done=False):
    return SessionSet.objects.create(
        session_exercise=session_exercise,
        weight=Decimal(str(weight)),
        reps=reps,
        is_done=is_done,
    )


def make_default_program(user, name='Шаблон'):
    return DefaultProgram.objects.create(user=user, name=name)


def make_default_program_day(default_program, name='День А', order=0):
    return DefaultProgramDay.objects.create(
        program=default_program, name=name, order=order
    )


class WorkoutListTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = Client()
        self.client.login(username='user', password='pass1234')

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('diary:workout_list'))
        self.assertEqual(response.status_code, 401)

    def test_shows_only_finished_sessions(self):
        finished = make_training_session(self.user, is_active=False)
        make_training_session(self.user, is_active=True)
        response = self.client.get(reverse('diary:workout_list'))
        data = response.json()
        ids = [session['id'] for session in data]
        self.assertIn(finished.pk, ids)
        self.assertEqual(len(data), 1)

    def test_does_not_show_other_users_sessions(self):
        other = make_user('other', 'pass1234')
        make_training_session(other, is_active=False)
        response = self.client.get(reverse('diary:workout_list'))
        self.assertEqual(len(response.json()), 0)


class FinishWorkoutTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = Client()
        self.client.login(username='user', password='pass1234')
        self.training_session = make_training_session(self.user, is_active=True)

    def test_sets_session_inactive(self):
        url = reverse('diary:finish_workout', kwargs={'pk': self.training_session.pk})
        self.client.post(url)
        self.training_session.refresh_from_db()
        self.assertFalse(self.training_session.is_active)

    def test_saves_duration_seconds(self):
        url = reverse('diary:finish_workout', kwargs={'pk': self.training_session.pk})
        self.client.post(url)
        self.training_session.refresh_from_db()
        self.assertIsNotNone(self.training_session.duration_seconds)
        self.assertGreaterEqual(self.training_session.duration_seconds, 0)

    def test_finishes_session_without_program(self):
        url = reverse('diary:finish_workout', kwargs={'pk': self.training_session.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)

    def test_finishes_session_started_from_default_program(self):
        default_program = make_default_program(self.user)
        day = make_default_program_day(default_program)
        DefaultProgramSession.objects.create(day=day, session=self.training_session)
        url = reverse('diary:finish_workout', kwargs={'pk': self.training_session.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)

    def test_other_user_cannot_finish_session(self):
        other = make_user('other', 'pass1234')
        other_session = make_training_session(other)
        url = reverse('diary:finish_workout', kwargs={'pk': other_session.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)


class AddSetTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = Client()
        self.client.login(username='user', password='pass1234')
        self.training_session = make_training_session(self.user)
        self.exercise = make_exercise()
        self.session_exercise = make_session_exercise(self.training_session, self.exercise)

    def test_creates_session_set_with_correct_values(self):
        url = reverse('diary:add_set', kwargs={'pk': self.session_exercise.pk})
        self.client.post(url, {'weight': '80.0', 'reps': 8})
        session_set = SessionSet.objects.get(session_exercise=self.session_exercise)
        self.assertEqual(session_set.weight, Decimal('80.0'))
        self.assertEqual(session_set.reps, 8)
        self.assertFalse(session_set.is_done)

    def test_cannot_add_set_to_finished_session(self):
        finished = make_training_session(self.user, is_active=False)
        session_exercise = make_session_exercise(finished, self.exercise)
        url = reverse('diary:add_set', kwargs={'pk': session_exercise.pk})
        response = self.client.post(url, {'weight': '80.0', 'reps': 8})
        self.assertEqual(response.status_code, 404)


class ToggleSetDoneTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = Client()
        self.client.login(username='user', password='pass1234')
        self.training_session = make_training_session(self.user)
        self.exercise = make_exercise()
        self.session_exercise = make_session_exercise(self.training_session, self.exercise)

    def test_toggles_false_to_true(self):
        session_set = make_session_set(self.session_exercise, is_done=False)
        self.client.post(reverse('diary:toggle_set_done', kwargs={'pk': session_set.pk}))
        session_set.refresh_from_db()
        self.assertTrue(session_set.is_done)

    def test_toggles_true_to_false(self):
        session_set = make_session_set(self.session_exercise, is_done=True)
        self.client.post(reverse('diary:toggle_set_done', kwargs={'pk': session_set.pk}))
        session_set.refresh_from_db()
        self.assertFalse(session_set.is_done)

    def test_toggle_not_allowed_on_finished_session(self):
        finished = make_training_session(self.user, is_active=False)
        session_exercise = make_session_exercise(finished, self.exercise)
        session_set = make_session_set(session_exercise, is_done=False)
        response = self.client.post(
            reverse('diary:toggle_set_done', kwargs={'pk': session_set.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_other_user_cannot_toggle_set(self):
        other = make_user('other', 'pass1234')
        other_session = make_training_session(other)
        other_session_exercise = make_session_exercise(other_session, self.exercise)
        other_set = make_session_set(other_session_exercise, is_done=False)
        response = self.client.post(
            reverse('diary:toggle_set_done', kwargs={'pk': other_set.pk})
        )
        self.assertEqual(response.status_code, 404)


class UpdateSetTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = Client()
        self.client.login(username='user', password='pass1234')
        self.training_session = make_training_session(self.user)
        self.session_exercise = make_session_exercise(self.training_session, make_exercise())
        self.session_set = make_session_set(self.session_exercise, weight=100, reps=5)

    def test_saves_new_weight_and_reps(self):
        self.client.post(
            reverse('diary:update_set', kwargs={'pk': self.session_set.pk}),
            {'weight': '120.0', 'reps': 8},
        )
        self.session_set.refresh_from_db()
        self.assertEqual(self.session_set.weight, Decimal('120.0'))
        self.assertEqual(self.session_set.reps, 8)

    def test_accepts_comma_as_decimal_separator(self):
        self.client.post(
            reverse('diary:update_set', kwargs={'pk': self.session_set.pk}),
            {'weight': '92,5', 'reps': 6},
        )
        self.session_set.refresh_from_db()
        self.assertEqual(self.session_set.weight, Decimal('92.5'))

    def test_cannot_update_set_in_finished_session(self):
        finished = make_training_session(self.user, is_active=False)
        session_exercise = make_session_exercise(finished, make_exercise('Тяга'))
        session_set = make_session_set(session_exercise)
        response = self.client.post(
            reverse('diary:update_set', kwargs={'pk': session_set.pk}),
            {'weight': '50.0', 'reps': 10},
        )
        self.assertEqual(response.status_code, 404)


class StartFromTemplateDayTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = Client()
        self.client.login(username='user', password='pass1234')

        self.exercise = make_exercise()
        self.default_program = make_default_program(self.user)
        self.day = make_default_program_day(self.default_program)

        program_exercise = DefaultProgramExercise.objects.create(
            day=self.day, exercise=self.exercise, order=0
        )
        DefaultProgramSet.objects.create(
            program_exercise=program_exercise, weight=Decimal('80.0'), reps=8
        )
        DefaultProgramSet.objects.create(
            program_exercise=program_exercise, weight=Decimal('80.0'), reps=8
        )

    def _start(self):
        return self.client.post(
            reverse(
                'diary:start_from_template_day',
                kwargs={'pk': self.default_program.pk, 'dpk': self.day.pk},
            )
        )

    def test_creates_new_active_training_session(self):
        self._start()
        queryset = TrainingSession.objects.filter(user=self.user, is_active=True)
        self.assertEqual(queryset.count(), 1)

    def test_creates_default_program_session_link(self):
        self._start()
        training_session = TrainingSession.objects.get(user=self.user, is_active=True)
        self.assertTrue(
            DefaultProgramSession.objects.filter(
                session=training_session, day=self.day
            ).exists()
        )

    def test_copies_exercise_from_default_program(self):
        self._start()
        training_session = TrainingSession.objects.get(user=self.user, is_active=True)
        self.assertTrue(
            SessionExercise.objects.filter(
                session=training_session, exercise=self.exercise
            ).exists()
        )

    def test_copies_correct_number_of_sets(self):
        self._start()
        training_session = TrainingSession.objects.get(user=self.user, is_active=True)
        session_exercise = SessionExercise.objects.get(
            session=training_session, exercise=self.exercise
        )
        self.assertEqual(session_exercise.session_sets.count(), 2)

    def test_copies_weight_and_reps_from_program_sets(self):
        self._start()
        training_session = TrainingSession.objects.get(user=self.user, is_active=True)
        session_exercise = SessionExercise.objects.get(
            session=training_session, exercise=self.exercise
        )
        session_set = session_exercise.session_sets.first()
        self.assertEqual(session_set.weight, Decimal('80.0'))
        self.assertEqual(session_set.reps, 8)

    def test_all_copied_sets_start_as_not_done(self):
        self._start()
        training_session = TrainingSession.objects.get(user=self.user, is_active=True)
        done_count = SessionSet.objects.filter(
            session_exercise__session=training_session, is_done=True
        ).count()
        self.assertEqual(done_count, 0)

    def test_closes_existing_active_session(self):
        existing = make_training_session(self.user, is_active=True)
        self._start()
        existing.refresh_from_db()
        self.assertFalse(existing.is_active)

    def test_returns_workout_session_id(self):
        response = self._start()
        self.assertEqual(response.status_code, 201)
        training_session = TrainingSession.objects.get(user=self.user, is_active=True)
        self.assertEqual(response.json()['workout_session_id'], training_session.pk)

    def test_requires_login(self):
        self.client.logout()
        response = self._start()
        self.assertEqual(response.status_code, 401)


class TemplateManagementTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = Client()
        self.client.login(username='user', password='pass1234')
        self.default_program = make_default_program(self.user)

    def test_create_default_program_sets_current_user(self):
        self.client.post(reverse('diary:create_template'), {'name': 'Новый'})
        default_program = DefaultProgram.objects.get(name='Новый')
        self.assertEqual(default_program.user, self.user)

    def test_delete_default_program_removes_it(self):
        url = reverse(
            'diary:template_detail', kwargs={'pk': self.default_program.pk}
        )
        self.client.delete(url)
        self.assertFalse(
            DefaultProgram.objects.filter(pk=self.default_program.pk).exists()
        )

    def test_cannot_delete_other_users_default_program(self):
        other = make_user('other', 'pass1234')
        other_program = make_default_program(other, 'Чужой')
        url = reverse(
            'diary:template_detail', kwargs={'pk': other_program.pk}
        )
        self.client.delete(url)
        self.assertTrue(
            DefaultProgram.objects.filter(pk=other_program.pk).exists()
        )

    def test_create_default_program_day(self):
        url = reverse(
            'diary:create_template_day', kwargs={'pk': self.default_program.pk}
        )
        self.client.post(url, {'name': 'День 1'})
        self.assertTrue(
            DefaultProgramDay.objects.filter(
                program=self.default_program, name='День 1'
            ).exists()
        )

    def test_delete_default_program_day(self):
        day = make_default_program_day(self.default_program, 'Удалить')
        url = reverse(
            'diary:template_day_detail',
            kwargs={'pk': self.default_program.pk, 'dpk': day.pk},
        )
        self.client.delete(url)
        self.assertFalse(DefaultProgramDay.objects.filter(pk=day.pk).exists())


class TemplateSetTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = Client()
        self.client.login(username='user', password='pass1234')

        exercise = make_exercise()
        self.default_program = make_default_program(self.user)
        self.day = make_default_program_day(self.default_program)
        self.program_exercise = DefaultProgramExercise.objects.create(
            day=self.day, exercise=exercise, order=0
        )

    def test_add_program_set_saves_weight_and_reps(self):
        self.client.post(
            reverse('diary:add_template_set', kwargs={'pk': self.program_exercise.pk}),
            {'weight': '75.0', 'reps': 10},
        )
        program_set = DefaultProgramSet.objects.get(program_exercise=self.program_exercise)
        self.assertEqual(program_set.weight, Decimal('75.0'))
        self.assertEqual(program_set.reps, 10)

    def test_update_program_set(self):
        program_set = DefaultProgramSet.objects.create(
            program_exercise=self.program_exercise, weight=Decimal('60.0'), reps=8
        )
        self.client.post(
            reverse('diary:update_template_set', kwargs={'pk': program_set.pk}),
            {'weight': '65.0', 'reps': 10},
        )
        program_set.refresh_from_db()
        self.assertEqual(program_set.weight, Decimal('65.0'))
        self.assertEqual(program_set.reps, 10)

    def test_delete_program_set(self):
        program_set = DefaultProgramSet.objects.create(
            program_exercise=self.program_exercise, weight=Decimal('60.0'), reps=8
        )
        self.client.delete(
            reverse('diary:update_template_set', kwargs={'pk': program_set.pk})
        )
        self.assertFalse(DefaultProgramSet.objects.filter(pk=program_set.pk).exists())

    def test_cannot_modify_other_users_program_set(self):
        other = make_user('other', 'pass1234')
        other_program = make_default_program(other)
        other_day = make_default_program_day(other_program)
        other_program_exercise = DefaultProgramExercise.objects.create(
            day=other_day, exercise=make_exercise('Тяга'), order=0
        )
        other_set = DefaultProgramSet.objects.create(
            program_exercise=other_program_exercise, weight=Decimal('50'), reps=5
        )
        response = self.client.post(
            reverse('diary:update_template_set', kwargs={'pk': other_set.pk}),
            {'weight': '999', 'reps': 1},
        )
        self.assertEqual(response.status_code, 404)
