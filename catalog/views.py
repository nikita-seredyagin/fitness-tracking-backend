from datetime import timedelta

from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView

from diary.models import SessionSet
from .models import Exercise, MuscleGroup
from .serializers import ExerciseSerializer, MuscleGroupSerializer


class ExerciseListView(ListAPIView):
    serializer_class = ExerciseSerializer
    queryset = Exercise.objects.prefetch_related('muscle_groups').all()
    permission_classes = [AllowAny]


class ExerciseDetailView(RetrieveAPIView):
    serializer_class = ExerciseSerializer
    queryset = Exercise.objects.prefetch_related('muscle_groups').all()
    permission_classes = [AllowAny]


class ExerciseStatsView(APIView):
    def get(self, request, pk):
        from django.shortcuts import get_object_or_404
        exercise = get_object_or_404(Exercise, pk=pk)

        three_months_ago = timezone.now() - timedelta(days=90)
        sets = (
            SessionSet.objects
            .filter(
                session_exercise__exercise=exercise,
                session_exercise__session__user=request.user,
                session_exercise__session__is_active=False,
                session_exercise__session__date__gte=three_months_ago,
                is_done=True,
            )
            .select_related('session_exercise__session')
            .order_by('session_exercise__session__date')
        )

        session_max = {}
        for session_set in sets:
            d = session_set.session_exercise.session.date.strftime('%d.%m.%Y')
            w = float(session_set.weight)
            if d not in session_max or w > session_max[d]:
                session_max[d] = w

        best_set = (
            SessionSet.objects
            .filter(
                session_exercise__exercise=exercise,
                session_exercise__session__user=request.user,
                session_exercise__session__is_active=False,
                is_done=True,
            )
            .order_by('-weight', '-reps')
            .first()
        )

        one_rm = None
        if best_set:
            all_sets = (
                SessionSet.objects
                .filter(
                    session_exercise__exercise=exercise,
                    session_exercise__session__user=request.user,
                    session_exercise__session__is_active=False,
                    is_done=True,
                    reps__gte=1,
                )
                .values_list('weight', 'reps')
            )
            one_rm = round(
                max(float(w) * (1 + r / 30) for w, r in all_sets), 1
            )

        return Response({
            'chart_dates': list(session_max.keys()),
            'chart_weights': list(session_max.values()),
            'best_set': {
                'weight': str(best_set.weight),
                'reps': best_set.reps,
            } if best_set else None,
            'one_rm': one_rm,
        })


class MuscleGroupListView(ListAPIView):
    serializer_class = MuscleGroupSerializer
    queryset = MuscleGroup.objects.all()
    permission_classes = [AllowAny]
