from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import permission_required, login_required
from django.contrib import messages
from authentification.forms.superviseur.formsSuperviseur import *

from django.contrib import messages
from django.db import transaction


@login_required
@permission_required('app.add_groupeagent')
def creer_groupe(request):
    if request.method == 'POST':
        form = GroupeAgentForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    groupe = form.save(commit=False)
                    groupe.created_by = request.user
                    groupe.save()
                    form.save_m2m()  # Pour les relations ManyToMany

                    messages.success(request, f"Groupe {groupe.nom} créé avec succès")
                    return redirect('liste_groupes')
            except ValidationError as e:
                messages.error(request, str(e))
    else:
        form = GroupeAgentForm(user=request.user)

    return render(request, 'superviseur/creer_groupe.html', {'form': form})