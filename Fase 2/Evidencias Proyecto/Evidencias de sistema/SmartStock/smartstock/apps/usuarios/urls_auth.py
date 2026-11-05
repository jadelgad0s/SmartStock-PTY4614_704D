"""
URLs de autenticación.
"""
from django.urls import path
from .views_auth import (
    LoginView,
    LoginWebView,
    CustomTokenRefreshView,
    logout_view,
    me_view,
    navegacion_view,
    cambiar_password_view,
)

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('login-web/', LoginWebView.as_view(), name='login_web'),
    path('logout/', logout_view, name='logout'),
    path('refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
    path('me/', me_view, name='me'),
    path('navegacion/', navegacion_view, name='navegacion'),
    path('cambiar-password/', cambiar_password_view, name='cambiar_password'),
]
