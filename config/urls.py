from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

admin.site.site_header = 'FitnesTracking Admin'
admin.site.site_title = 'FitnesTracking'
admin.site.index_title = 'Управление приложением'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('users.urls')),
    path('api/', include('catalog.urls')),
    path('api/', include('diary.urls')),
    path('api/', include('smart_workout.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
