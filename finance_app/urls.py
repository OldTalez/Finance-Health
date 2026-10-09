"""
App-level URL routing for all Finance Platform endpoints
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create router for ViewSets
router = DefaultRouter()
router.register(r'accounts', views.AccountViewSet, basename='account')
router.register(r'transactions', views.TransactionViewSet, basename='transaction')
router.register(r'categories', views.CategoryViewSet, basename='category')
router.register(r'rules', views.RuleViewSet, basename='rule')

# Auth URLs
auth_patterns = [
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('refresh/', views.RefreshTokenView.as_view(), name='refresh'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('me/', views.UserProfileView.as_view(), name='profile'),
]

# Dashboard & Analytics URLs
analytics_patterns = [
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
]

# Import/Upload URLs
from .upload_views import UploadView

import_patterns = [
    path('upload/', UploadView.as_view(), name='upload'),
    path('status/<str:task_id>/', views.ImportStatusView.as_view(), name='import_status'),
    path('history/', views.ImportHistoryView.as_view(), name='import_history'),
]

# Combine all patterns
urlpatterns = [
    path('auth/', include(auth_patterns)),
    path('analytics/', include(analytics_patterns)),
    path('import/', include(import_patterns)),
    path('', include(router.urls)),  # Account, Transaction, Category, Rule routes
]
