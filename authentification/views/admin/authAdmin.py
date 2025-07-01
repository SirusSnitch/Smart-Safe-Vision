from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth import login, get_user_model, logout
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.template.loader import render_to_string
from django.utils.crypto import get_random_string
from authentification.forms.admin.formsAdmin import PasswordResetRequestForm
from authentification.forms.admin.formsAdmin import *



def is_admin(user):
    return user.role == User.Role.ADMIN
def is_super(user):
    return user.role == User.Role.SUPERVISEUR
def admin_main(request):
    return render(request, 'admin/home.html')


def register_admin(request):
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
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            if user.role == 'ADMIN':
                return redirect('admin_main')
            elif user.role == 'SUPER':
                return redirect('liste_superviseurs')
            elif user.role == 'AGENT':
                return redirect('admin_mainn')
        else:
            form.add_error(None, "Email ou mot de passe invalide.")
    else:
        form = LoginForm()

    return render(request, 'admin/signin.html', {'form': form})



def logOut(request):
    logout(request)
    return redirect('login')




@user_passes_test(is_admin)
def creer_superviseur(request):
    if request.method == 'POST':
        form = CreateSuperviseurForm(request.POST)
        if form.is_valid():
            superviseur = form.save(commit=False)
            superviseur.role = User.Role.SUPERVISEUR
            password = get_random_string(length=12)  # Mot de passe plus sécurisé
            superviseur.set_password(password)
            superviseur.save()

            # Envoi de l'email
            subject = "Vos identifiants de superviseur"
            message = render_to_string('admin/admin_email_password.html', {
                'user': superviseur,
                'email': superviseur.email,
                'password': password,
                'login_url': f"{'https' if request.is_secure() else 'http'}://{get_current_site(request).domain}/login"
            })

            send_mail(
                subject,
                message,
                'dridi.nourchenee@gmail.com',
                [superviseur.email],
                fail_silently=False,
                html_message=message  # Pour un email HTML
            )

            return redirect('liste_superviseurs')
    else:
        form = CreateSuperviseurForm()
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
        form = EditSuperviseurForm(request.POST, instance=superviseur)
        if form.is_valid():
            form.save()
            messages.success(request, "Superviseur mis à jour avec succès")
            return redirect('liste_superviseurs')
    else:
        form = EditSuperviseurForm(instance=superviseur)

    return render(request, 'admin/modifier_superviseur.html', {
        'form': form,
        'superviseur': superviseur
    })


@user_passes_test(is_admin,is_super)
def creer_agent(request):
    if request.method == 'POST':
        form = CreateAgentForm(request.POST)
        if form.is_valid():
            agent = form.save(commit=False)
            agent.role = User.Role.AGENT
            password = get_random_string(length=12)  # Mot de passe plus sécurisé
            agent.set_password(password)
            agent.save()

            # Envoi de l'email
            subject = "Vos identifiants de agent"
            message = render_to_string('admin/admin_email_password.html', {
                'user': agent,
                'email': agent.email,
                'password': password,
                'login_url': f"{'https' if request.is_secure() else 'http'}://{get_current_site(request).domain}/login"
            })

            send_mail(
                subject,
                message,
                'dridi.nourchenee@gmail.com',
                [agent.email],
                fail_silently=False,
                html_message=message  # Pour un email HTML
            )

            return redirect('liste_agents')

        messages.success(request, "Agent créé avec succès")
        return redirect('liste_agents')
    else:
        form = CreateAgentForm()

    return render(request, 'admin/creer_agent.html', {'form': form})

@user_passes_test(is_admin,is_super)
def modifier_agent(request, agent_id):
    agent = get_object_or_404(User, id=agent_id, role=User.Role.AGENT)

    if request.method == 'POST':
        form = CreateAgentForm(request.POST, instance=agent)
        if form.is_valid():
            form.save()
            messages.success(request, "Agent modifié avec succès")
            return redirect('liste_agents')
    else:
        form = CreateAgentForm(instance=agent)

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




User = get_user_model()
def password_reset_request(request):
    if request.method == 'POST':
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            field_type, value = form.cleaned_data['email_or_cin']

            # Trouver l'utilisateur par email ou CIN
            if field_type == 'email':
                user = User.objects.filter(email=value).first()
            else:  # CIN
                user = User.objects.filter(cin=value).first()

            if user:
                # Générer un nouveau mot de passe temporaire
                temp_password = get_random_string(length=12)
                user.set_password(temp_password)
                user.save()

                # Envoyer l'email
                subject = "Réinitialisation de votre mot de passe"
                message = render_to_string('admin/password_reset_email.html', {
                    'user': user,
                    'temp_password': temp_password,
                })

                send_mail(
                    subject,
                    message,
                    'dridi.nourchenee@gmail.com',
                    [user.email],
                    fail_silently=False,
                    html_message=message
                )

            # Toujours retourner le même message pour éviter le fishing
            return render(request, 'admin/password_reset_sent.html')
    else:
        form = PasswordResetRequestForm()

    return render(request, 'admin/password_reset_form.html', {'form': form})