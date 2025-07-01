from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from django import forms
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from authentification.models import *



class CinEmailControle:
    cin = forms.CharField(
        max_length=8,
        min_length=8,
        validators=[RegexValidator(regex='^[0-9]{8}$', message='Le CIN doit contenir exactement 8 chiffres.')],
        widget=forms.TextInput(attrs={'placeholder': 'Ex: 12345678'})
    )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if existing := User.objects.filter(email=email).first():
            raise forms.ValidationError(f"Email déjà utilisé par {existing.get_full_name()}")
        return email
    def clean_cin(self):
        cin = self.cleaned_data.get('cin')
        if hasattr(self, 'instance') and cin == getattr(self.instance, 'cin', None):
            return cin  # Ne pas valider si inchangé (pour les edits)
        if User.objects.filter(cin=cin).exists():
            raise forms.ValidationError("Ce CIN est déjà utilisé.")
        return cin


class LoginForm(AuthenticationForm):
    username = forms.EmailField(max_length=255, required=True, widget=forms.EmailInput(attrs={'placeholder' : "Enter your email", 'class': 'form-control'}))
    password = forms.CharField(max_length=50, required=True, widget=forms.PasswordInput(attrs={'placeholder': 'Password', 'class': 'form-control'}))

class AdminRegisterForm(forms.ModelForm,CinEmailControle):
    password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['cin','first_name', 'last_name', 'email', 'phone', 'password']



class CreateSuperviseurForm(forms.ModelForm,CinEmailControle):
    class Meta:
        model = User
        fields = ['cin','email', 'first_name', 'last_name', 'phone']

class EditSuperviseurForm(forms.ModelForm,CinEmailControle):

    class Meta:
        model = User
        fields = [ 'cin','email', 'first_name', 'last_name', 'phone']
        labels = {
            'email': 'Email',
        }


class CreateAgentForm(UserCreationForm,CinEmailControle):
    class Meta:
        model = User
        fields = ['cin','email', 'first_name', 'last_name', 'phone']

class PasswordResetRequestForm(forms.Form):
    email_or_cin = forms.CharField(
        label="Email ou CIN",
        max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'Entrez votre email ou CIN'}))

    def clean_email_or_cin(self):
        data = self.cleaned_data['email_or_cin']
        # Vérifie si c'est un CIN (8 chiffres)
        if data.isdigit() and len(data) == 8:
            return ('cin', data)
        # Sinon, vérifie si c'est un email valide
        try:
            validate_email(data)
            return ('email', data)
        except ValidationError:
            raise forms.ValidationError("Veuillez entrer un email valide ou un CIN à 8 chiffres")


