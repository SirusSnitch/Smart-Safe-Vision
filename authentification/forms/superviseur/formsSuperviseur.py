from django import forms
from authentification.models import GroupeAgent, Secteur, User

class GroupeAgentForm(forms.ModelForm):
    class Meta:
        model = GroupeAgent
        fields = ['nom', 'secteur', 'agents']
        widgets = {
            'agents': forms.SelectMultiple(attrs={'class': 'select2'}),
            'secteur': forms.Select(attrs={'class': 'form-control'})
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            # Filtre les secteurs que ce superviseur gère
            self.fields['secteur'].queryset = Secteur.objects.filter(superviseur=user)
            # Filtre uniquement les agents
            self.fields['agents'].queryset = User.objects.filter(role=User.Role.AGENT)