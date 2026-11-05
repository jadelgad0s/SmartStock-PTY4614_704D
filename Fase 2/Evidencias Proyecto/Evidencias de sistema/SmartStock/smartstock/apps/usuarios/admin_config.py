from django.contrib.admin.apps import AdminConfig


class SmartStockAdminConfig(AdminConfig):
    default_site = 'apps.usuarios.admin_site.SmartStockAdminSite'
