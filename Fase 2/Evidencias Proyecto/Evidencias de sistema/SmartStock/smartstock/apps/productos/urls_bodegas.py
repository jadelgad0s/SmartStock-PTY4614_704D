from rest_framework.routers import DefaultRouter
from .views_bodegas import BodegaViewSet

router = DefaultRouter()
router.register('bodegas', BodegaViewSet, basename='bodega')
urlpatterns = router.urls
