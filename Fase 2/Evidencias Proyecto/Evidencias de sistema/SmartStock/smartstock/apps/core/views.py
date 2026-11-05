from functools import wraps

from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache

from apps.usuarios.navegacion import cuenta_habilitada, inicio_usuario, modulos_usuario


def requiere_modulo(vista):
    @never_cache
    @wraps(vista)
    def protegida(request, *args, **kwargs):
        if not cuenta_habilitada(request.user):
            return redirect('login_page')
        modulos = modulos_usuario(request.user)
        if request.path_info not in modulos:
            return redirect(inicio_usuario(request.user, modulos))
        return vista(request, *args, **kwargs)
    return protegida


@never_cache
def login_page(request):
    return render(request, 'login.html')

def dashboard_page(request):
    return render(request, 'dashboard.html')

def productos_page(request):
    return render(request, 'productos.html')


# Vista para la operación de bodega (Escáner)
def movimientos_page(request):
    return render(request, 'movimientos.html')


def auditoria_page(request):
    return render(request, 'auditoria.html')

def mermas_page(request):
    return render(request, 'mermas.html')


def bodegas_page(request):
    return render(request, 'bodegas.html')


def transferencias_page(request):
    return render(request, 'transferencias.html')

