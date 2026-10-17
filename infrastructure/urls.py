from django.urls import include, path
from . import views
from .views import mobile_infrastructure_list

urlpatterns = [
    path("", views.infrastructure_list, name="infrastructure_list"),
    path("add/", views.add_infrastructure, name="infrastructure-add"),
    path("edit/<int:infrastructure_id>/",views.edit_infrastructure,name="infrastructure-edit"),
    path("view/<int:infrastructure_id>/",views.view_infrastructure,name="infrastructure_view"),
    path("delete/<int:infrastructure_id>/",views.delete_infrastructure,name="infrastructure_delete"),
    path("map/", views.map, name="map"),
    path("api/", mobile_infrastructure_list, name="mobile-infrastructure-list"),
    
]