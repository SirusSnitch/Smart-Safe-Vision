from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from gismap.models import Camera

@login_required
def camera_list(request):
    # Récupérer le département de l'utilisateur connecté
    user_departement = request.user.lieu

    # Filtrer les caméras en fonction du département de l'utilisateur
    if user_departement:
        cameras = Camera.objects.filter(department=user_departement)  # Changé departement -> department
    else:
        # Si l'utilisateur n'a pas de département, on ne retourne aucune caméra
        cameras = Camera.objects.none()

    context = {
        'cameras': cameras,
    }

    return render(request, 'admin/interface_agent.html', context)