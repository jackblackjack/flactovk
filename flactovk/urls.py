from django.conf.urls import patterns, include, url
from django.views.generic import TemplateView
from flactovk.views import upload, upload_delete
from frontend.views import ProtectedView, my_logout

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    # Examples:
    # url(r'^$', 'flactovk.views.home', name='home'),
    url(r'^$', TemplateView.as_view(template_name='index.html'), name='home'),
    url(r'^accounts/profile/$', ProtectedView.as_view(template_name='profile.html'), name='profile'),
    url(r'^accounts/profile/tracks/$', ProtectedView.as_view(template_name='profile_tracks.html'), name='tracks'),
    url(r'^accounts/logout/$', my_logout, name='logout'),
    # url(r'^flactovk/', include('flactovk.foo.urls')),

    # Uncomment the admin/doc line below to enable admin documentation:
    # url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    url('', include('social.apps.django_app.urls', namespace='social')),
    url(r'^admin/', include(admin.site.urls)),
    url( r'upload/', upload, name='jfu_upload' ),
    # You may optionally define a delete url as well
    url( r'^delete/(?P<pk>\d+)$', upload_delete, name='jfu_delete' ),
)
