from django.urls import path
from authentification.views.admin.authAdmin import *

urlpatterns = [

   # Urls Admin
   path('signin/', login_view, name='login'),
   path('admin_main/', admin_main, name='admin_main'),
   path('register-admin/', register_admin, name='register_admin'),
   path('superviseurs/', liste_superviseurs, name='liste_superviseurs'),
   path('superviseurs/creer/', creer_superviseur, name='creer_superviseur'),
   path('superviseurs/supprimer/<int:pk>/', supprimer_superviseur, name='supprimer_superviseur'),
   path('superviseurs/modifier/<int:pk>/', modifier_superviseur, name='modifier_superviseur'),
   path('agents/', liste_agents, name='liste_agents'),
   path('agents/creer/', creer_agent, name='creer_agent'),
   path('agents/modifier/<int:agent_id>/', modifier_agent, name='modifier_agent'),
   path('agents/supprimer/<int:agent_id>/', supprimer_agent, name='supprimer_agent'),



   # URLs Agent
   #path('agent/dashboard/', agent_dashboard, name='agent_dashboard'),
   #path('register/',register_view, name='register'),
]
