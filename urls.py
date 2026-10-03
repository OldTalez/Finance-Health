"""
API URL routing for Finance Platform Phase 1
RESTful endpoint structure
"""

from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from django.http import HttpResponse

# Main URL configuration
urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # API Documentation (Swagger/OpenAPI)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc-ui'),

    # API v1 - All Finance Platform endpoints
    path('api/v1/', include('app_urls')),

    # Health check endpoint (for monitoring/uptime checks)
    path('health/', lambda request: HttpResponse('OK'), name='health'),
]
