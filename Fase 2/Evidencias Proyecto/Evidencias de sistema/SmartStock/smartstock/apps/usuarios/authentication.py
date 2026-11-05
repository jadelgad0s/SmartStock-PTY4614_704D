from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication

from .navegacion import cuenta_habilitada


class JWTConRolActivo(JWTAuthentication):
    def get_user(self, validated_token):
        usuario = super().get_user(validated_token)
        if not cuenta_habilitada(usuario):
            raise PermissionDenied('Tu cuenta necesita estar activa y tener un rol activo.')
        return usuario
