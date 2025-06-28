from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from authentification.models import *


class EmailLoginForm(AuthenticationForm):
    username = forms.EmailField(max_length=255, required=True, widget=forms.EmailInput(attrs={'placeholder' : "Enter your email", 'class': 'form-control'}))
    password = forms.CharField(max_length=50, required=True, widget=forms.PasswordInput(attrs={'placeholder': 'Password', 'class': 'form-control'}))

class AdminRegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'username', 'phone', 'password']


# forms.py
class SuperviseurForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'phone', 'password1', 'password2']
        labels = {
            'email': 'Email (identifiant)',
            'password1': 'Mot de passe',
            'password2': 'Confirmation'
        }

class SuperviseurEditForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.filter(codename__in=[
            'creer_groupes',
            'gerer_secteurs',
            'lier_cameras',
            'affecter_agents'
        ]),
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'phone']
        labels = {
            'email': 'Email (identifiant)',
        }




class AgentCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'phone', 'password1', 'password2']
        labels = {
            'email': 'Email (identifiant)',
            'password1': 'Mot de passe',
            'password2': 'Confirmation du mot de passe'
        }