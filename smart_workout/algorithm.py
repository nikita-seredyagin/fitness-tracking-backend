"""
Алгоритм двойной прогрессии и анализ объёма для smart-программ тренировок.

Принцип изоляции: внутри calculate_progression нет ORM-запросов Django.
Вызывающий код передаёт предзагруженные ORM-объекты; модуль выполняет только арифметику.

Научная основа:
- Модель двойной прогрессии (Schoenfeld et al., Israetel et al.)
- Пороги объёма MEV/MAV/MRV (Israetel, Renaissance Periodization)
- Деload-периодизация каждые 4 недели для восстановления
"""
from decimal import Decimal

VOLUME_THRESHOLDS = {
    'default':        (10, 16, 22),
    'грудь':          (10, 16, 22),
    'спина':          (10, 16, 22),
    'дельтовидные мышцы': (8,  14, 20),
    'дельты':         (8,  14, 20),
    'бицепс':         (8,  14, 20),
    'трицепс':        (6,  14, 18),
    'квадрицепс':     (8,  16, 22),
    'бицепс бедра':   (6,  12, 18),
    'ягодицы':        (8,  16, 24),
    'икры':           (8,  14, 20),
    'пресс':          (8,  16, 24),
    'предплечья':     (6,  10, 14),
    'трапеции':       (4,  10, 14),
}

LOWER_BODY_KEYWORDS = [
    'нога', 'ног', 'присед', 'жим ног', 'выпад', 'становая',
    'румынская', 'квадрицепс', 'бицепс бедра', 'икры', 'икроножн',
    'ягодиц', 'deadlift', 'squat', 'lunge',
]

DELOAD_WEEKS = 4
BREAK_DAYS = 10
MIN_PLATE = Decimal('2.5')
REPS_MAX = 12
REPS_RESET = 6


def _round_to_plate(weight: Decimal) -> Decimal:
    """Округляет вес до ближайшего кратного MIN_PLATE."""
    return (weight / MIN_PLATE).quantize(Decimal('1')) * MIN_PLATE


def _is_lower_body(exercise) -> bool:
    name_lower = exercise.name.lower()
    return any(keyword in name_lower for keyword in LOWER_BODY_KEYWORDS)


def _weight_increment(exercise) -> Decimal:
    return Decimal('5.0') if _is_lower_body(exercise) else Decimal('2.5')


def calculate_progression(day_exercise, session_exercise):
    """
    Вычисляет логику двойной прогрессии для одного упражнения в одной сессии.

    Параметры
    ---------
    day_exercise     : экземпляр SmartDayExercise (с prefetch .exercise)
    session_exercise : SessionExercise с prefetch session_sets

    Возвращает
    ----------
    (reason, delta, new_reps, sets_completed, avg_reps)
    reason         : 'increase' | 'maintain' | 'decrease'
    delta          : изменение веса (Decimal) для каждого SmartSet
    new_reps       : int | None — новые целевые повторы для всех SmartSet, None если без изменений
    sets_completed : int
    avg_reps       : Decimal (округлён до 1 знака)

    Логика двойной прогрессии:
    - Успех + target_reps < REPS_MAX  → +1 повтор, вес не меняется
    - Успех + target_reps == REPS_MAX → +вес, повторы сбрасываются до REPS_RESET
    - Успех + target_reps > REPS_MAX  → +вес, повторы не меняются (высокоповторные упражнения)
    - Все подходы сделаны, но повторов не хватило → maintain
    - Незавершённые подходы → decrease
    """
    all_sets = list(session_exercise.session_sets.all())
    done_sets = [session_set for session_set in all_sets if session_set.is_done]
    sets_completed = len(done_sets)

    target = len(all_sets)
    day_sets = list(day_exercise.sets.all())
    if day_sets:
        target_reps = Decimal(sum(smart_set.reps for smart_set in day_sets)) / Decimal(len(day_sets))
    else:
        target_reps = Decimal(str(REPS_MAX))

    if sets_completed == 0:
        avg_reps = Decimal('0.0')
    else:
        avg_reps = Decimal(sum(session_set.reps for session_set in done_sets)) / Decimal(sets_completed)

    increment = _weight_increment(day_exercise.exercise)
    target_reps_int = int(round(target_reps))

    if sets_completed >= target and avg_reps >= target_reps:
        reason = 'increase'
        if target_reps_int < REPS_MAX:
            delta = Decimal('0.0')
            new_reps = target_reps_int + 1
        elif target_reps_int == REPS_MAX:
            delta = increment
            new_reps = REPS_RESET
        else:
            delta = increment
            new_reps = None
    elif sets_completed >= target:
        reason = 'maintain'
        delta = Decimal('0.0')
        new_reps = None
    else:
        reason = 'decrease'
        delta = -increment
        new_reps = None

    return reason, delta, new_reps, sets_completed, round(avg_reps, 1)


def apply_deload(weight: Decimal) -> Decimal:
    """Возвращает deload-вес (60%), округлённый до ближайшего кратного MIN_PLATE."""
    return _round_to_plate(weight * Decimal('0.60'))


def should_deload(smart_session) -> bool:
    from datetime import timedelta

    previous_session = (
        smart_session.__class__.objects
        .filter(
            program=smart_session.program,
            day=smart_session.day,
            pk__lt=smart_session.pk,
        )
        .select_related('session')
        .order_by('-pk')
        .first()
    )
    if previous_session is not None:
        gap = smart_session.session.date - previous_session.session.date
        if gap > timedelta(days=BREAK_DAYS):
            return False

    return smart_session.week_number % DELOAD_WEEKS == 0


def analyze_program_volume(smart_program):
    """
    Считает недельные подходы по группам мышц на основе РЕАЛЬНО выполненных подходов
    за последние 7 дней. Если сессий за этот период не было — использует плановые SmartSet.

    Возвращает (results, is_actual):
      results   — список словарей, отсортированных по muscle_group.name:
                  { 'muscle_group', 'weekly_sets', 'mev', 'mav', 'mrv',
                    'status', 'sets_to_optimal' }
      is_actual — True если данные из реальных сессий, False если из плана
    """
    from collections import defaultdict
    from datetime import timedelta

    from django.utils import timezone

    from catalog.models import MuscleGroup

    sets_per_group = defaultdict(int)
    cutoff = timezone.now() - timedelta(days=7)

    recent_sessions = smart_program.sessions.filter(
        session__date__gte=cutoff,
    ).prefetch_related(
        'session__session_exercises__exercise__muscle_groups',
        'session__session_exercises__session_sets',
    )

    is_actual = False
    for smart_session in recent_sessions:
        is_actual = True
        for session_exercise in smart_session.session.session_exercises.all():
            done_count = sum(
                1 for session_set in session_exercise.session_sets.all() if session_set.is_done
            )
            for link in session_exercise.exercise.muscle_group_links.all():
                weight = 1.0 if link.is_primary else 0.5
                sets_per_group[link.muscle_group_id] += done_count * weight

    if not is_actual:
        for smart_day in smart_program.days.prefetch_related(
            'exercises__sets',
            'exercises__exercise__muscle_group_links',
        ).all():
            for day_exercise in smart_day.exercises.all():
                set_count = day_exercise.sets.count()
                for link in day_exercise.exercise.muscle_group_links.all():
                    weight = 1.0 if link.is_primary else 0.5
                    sets_per_group[link.muscle_group_id] += set_count * weight

    if not sets_per_group:
        return [], is_actual

    muscle_groups = MuscleGroup.objects.filter(id__in=sets_per_group.keys())
    results = []
    for muscle_group in muscle_groups:
        weekly_sets = round(sets_per_group[muscle_group.id])
        mev, mav, mrv = VOLUME_THRESHOLDS.get(
            muscle_group.name.lower(), VOLUME_THRESHOLDS['default']
        )
        if weekly_sets < mev:
            volume_status = 'low'
        elif weekly_sets <= mav:
            volume_status = 'optimal'
        elif weekly_sets <= mrv:
            volume_status = 'high'
        else:
            volume_status = 'danger'

        sets_to_optimal = max(0, mev - weekly_sets)

        results.append({
            'muscle_group': muscle_group,
            'weekly_sets': weekly_sets,
            'mev': mev, 'mav': mav, 'mrv': mrv,
            'status': volume_status,
            'sets_to_optimal': sets_to_optimal,
        })

    results.sort(key=lambda entry: entry['muscle_group'].name)
    return results, is_actual
