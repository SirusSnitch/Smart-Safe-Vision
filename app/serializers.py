from rest_framework_gis.serializers import GeoFeatureModelSerializer
from .models import Lieu

class LieuSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = Lieu
        geo_field = 'position'
        fields = ('id', 'nom')
