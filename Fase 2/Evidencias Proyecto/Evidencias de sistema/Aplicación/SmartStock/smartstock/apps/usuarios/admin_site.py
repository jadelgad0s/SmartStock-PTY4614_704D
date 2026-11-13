from django.contrib.admin import AdminSite
from django.contrib.admin.forms import AdminAuthenticationForm

from .navegacion import puede_acceder_admin


class SmartStockAdminAuthenticationForm(AdminAuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not puede_acceder_admin(user):
            raise self.get_invalid_login_error()


class SmartStockAdminSite(AdminSite):
    login_form = SmartStockAdminAuthenticationForm

    def has_permission(self, request):
        return puede_acceder_admin(request.user)
