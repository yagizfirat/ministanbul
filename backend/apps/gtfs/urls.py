"""API + preview routes for the gtfs app (spec §6.3, §7.1)."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.gtfs import views

router = DefaultRouter()
router.register(r"agencies", views.AgencyViewSet, basename="agency")
router.register(r"routes", views.RouteViewSet, basename="route")
router.register(r"stops", views.StopViewSet, basename="stop")

urlpatterns = [
    path("api/trips/active/", views.trips_active, name="trips-active"),
    path("api/", include(router.urls)),
    path("preview/", views.preview, name="preview"),
]
