from django.urls import path
from .views import map_isgb

urlpatterns = [
    path('map-isgb/', map_isgb, name='map_isgb'),
]
