from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth import login
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from authentification.forms.admin.formsAdmin import *



def admin_main(request):
    return render(request, 'admin/liste_superviseurs.html')


def register_admin(request):
    # Vérifier s’il existe déjà un administrateur
    if User.objects.filter(role='ADMIN').exists():
        messages.warning(request, "Un administrateur existe déjà.")
        return redirect('login')

    if request.method == 'POST':
        form = AdminRegisterForm(request.POST)
        if form.is_valid():
            admin = form.save(commit=False)
            admin.is_superuser = True
            admin.is_staff = True
            admin.role = 'ADMIN'
            admin.set_password(form.cleaned_data['password'])
            admin.save()
            messages.success(request, "Administrateur créé avec succès.")
            return redirect('login')
    else:
        form = AdminRegisterForm()

    return render(request, 'admin/register_admin.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = EmailLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            # Redirection selon le rôle
            if user.role == 'ADMIN':
                return redirect('admin_main')
            elif user.role == 'SUPER':
                return redirect('liste_superviseurs')
            elif user.role == 'AGENT':
                return redirect('admin_mainn')
        else:
            form.add_error(None, "Email ou mot de passe invalide.")
    else:
        form = EmailLoginForm()

    return render(request, 'admin/signin.html', {'form': form})


def is_admin(user):
    return user.role == User.Role.ADMIN
def is_super(user):
    return user.role == User.Role.SUPERVISEUR

@user_passes_test(is_admin)
def creer_superviseur(request):
    if request.method == 'POST':
        form = SuperviseurForm(request.POST)
        if form.is_valid():
            superviseur = form.save(commit=False)
            superviseur.role = User.Role.SUPERVISEUR
            superviseur.username = None
            superviseur.save()

            # Attribution des permissions de base
            permissions = Permission.objects.filter(
                codename__in=['creer_groupes', 'gerer_secteurs', 'lier_cameras', 'affecter_agents']
            )
            superviseur.user_permissions.set(permissions)

            return redirect('liste_superviseurs')
    else:
        form = SuperviseurForm()
    return render(request, 'admin/creer_superviseur.html', {'form': form})



@user_passes_test(lambda u: u.role == User.Role.ADMIN)
def liste_superviseurs(request):
    superviseurs = User.objects.filter(role=User.Role.SUPERVISEUR).order_by('-date_joined')
    return render(request, 'admin/liste_superviseurs.html', {'superviseurs': superviseurs})


@user_passes_test(is_admin)
def supprimer_superviseur(request, pk):
    superviseur = get_object_or_404(User, pk=pk, role=User.Role.SUPERVISEUR)

    if request.method == 'POST':
        try:
            superviseur.delete()
            messages.success(request, "Superviseur supprimé avec succès")
        except Exception as e:
            messages.error(request, f"Erreur lors de la suppression : {str(e)}")
        return redirect('liste_superviseurs')

    return render(request, 'admin/confirmer_suppression.html', {
        'superviseur': superviseur
    })


@user_passes_test(is_admin)
def modifier_superviseur(request, pk):
    superviseur = get_object_or_404(User, pk=pk, role=User.Role.SUPERVISEUR)

    if request.method == 'POST':
        form = SuperviseurEditForm(request.POST, instance=superviseur)
        if form.is_valid():
            # Sauvegarde des informations de base
            form.save()

            # Mise à jour des permissions
            superviseur.user_permissions.set(form.cleaned_data['permissions'])

            messages.success(request, "Superviseur mis à jour avec succès")
            return redirect('liste_superviseurs')
    else:
        form = SuperviseurEditForm(instance=superviseur)
        # Initialiser les permissions actuelles
        form.fields['permissions'].initial = superviseur.user_permissions.all()

    return render(request, 'admin/modifier_superviseur.html', {
        'form': form,
        'superviseur': superviseur
    })


@user_passes_test(is_admin,is_super)
def creer_agent(request):
    if request.method == 'POST':
        form = AgentCreationForm(request.POST)
        if form.is_valid():
            agent = form.save(commit=False)
            agent.role = User.Role.AGENT
            agent.save()
            messages.success(request, "Agent créé avec succès")
            return redirect('liste_agents')
    else:
        form = AgentCreationForm()

    return render(request, 'admin/creer_agent.html', {'form': form})

@user_passes_test(is_admin,is_super)
def modifier_agent(request, agent_id):
    agent = get_object_or_404(User, id=agent_id, role=User.Role.AGENT)

    if request.method == 'POST':
        form = AgentCreationForm(request.POST, instance=agent)
        if form.is_valid():
            form.save()
            messages.success(request, "Agent modifié avec succès")
            return redirect('liste_agents')
    else:
        form = AgentCreationForm(instance=agent)

    return render(request, 'admin/modifier_agent.html', {'form': form, 'agent': agent})

@user_passes_test(is_admin,is_super)
def supprimer_agent(request, agent_id):
    agent = get_object_or_404(User, id=agent_id, role=User.Role.AGENT)

    if request.method == 'POST':
        agent.delete()
        messages.success(request, "Agent supprimé avec succès")
        return redirect('liste_agents')

    return render(request, 'admin/supprimer_agent.html', {'agent': agent})

@user_passes_test(is_admin,is_super)
def liste_agents(request):
    agents = User.objects.filter(role=User.Role.AGENT).order_by('last_name')
    return render(request, 'admin/liste_agents.html', {'agents': agents})