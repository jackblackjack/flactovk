# Create your views here.
from django.views.generic import CreateView
from models import Track
import json
from django.http import HttpResponse
import os
from django.conf import settings
from django.core.urlresolvers import reverse
from django.views.decorators.http import require_POST
from jfu.http import upload_receive, UploadResponse, JFUResponse
import os
from django.core.files import File
import subprocess
from social.apps.django_app.default.models import UserSocialAuth
import vkontakte
import requests
import json


class JSONResponseMixin(object):
    """
    A mixin that can be used to render a JSON response.
    """
    def render_to_json_response(self, context, **response_kwargs):
        """
        Returns a JSON response, transforming 'context' to make the payload.
        """
        return HttpResponse(
            self.convert_context_to_json(context),
            content_type='application/json',
            **response_kwargs
        )

    def convert_context_to_json(self, context):
        "Convert the context dictionary into a JSON object"
        # Note: This is *EXTREMELY* naive; in reality, you'll need
        # to do much more complex handling to ensure that arbitrary
        # objects -- such as Django model instances or querysets
        # -- can be serialized as JSON.
        return json.dumps(context)


# class TrackCreateView(CreateView, JSONResponseMixin):
#     model = Track
#     fields = ['mp3']
#
#     def form_valid(self, form):
#         track = form.save(commit=False)
#         track.user = self.request.user
#         track.save()
#
#         context = self.get_context_data()
#         return super(TrackCreateView, self).render_to_response(context)
#
#     def render_to_response(self, context, **response_kwargs):
#         return JSONResponseMixin.render_to_json_response(context)

@require_POST
def upload(request):

    # The assumption here is that jQuery File Upload
    # has been configured to send files one at a time.
    # If multiple files can be uploaded simulatenously,
    # 'file' may be a list of files.

    file = upload_receive(request)

    instance = Track(flac=file, user=request.user)
    instance.save()

    basename = os.path.basename(instance.flac.file.name)
    filename = "%s%s%s" % (settings.MEDIA_ROOT, 'mp3/', basename)
    mp3_filename = "%s%s" % (filename, '.mp3')

    # os.chdir("%s%s" % (settings.MEDIA_ROOT, 'mp3/'))
    resp = os.system('track2track -V quiet -t mp3 -o "%s" "%s"' % (mp3_filename, instance.flac.path))
    # subprocess.call(['track2track -V quiet -t mp3 -o "%s" "%s"' % (mp3_filename, instance.flac.path)])
    instance.mp3 = "mp3/%s" % os.path.basename(mp3_filename)

    # f = open(filename, 'r')
    # djangofile = File(f)
    # instance.mp3.save('filename.txt', djangofile)
    # f.close()

    instance.save()

    us = UserSocialAuth.objects.get(user=request.user)
    token = us.extra_data.get("access_token")
    vk = vkontakte.API(token=token)
    server = vk.audio.getUploadServer()
    url = server.get("upload_url")
    files = {'file' : open(instance.mp3.path, 'rb')}
    r = requests.post(url, files=files)
    _json = json.loads(r.text)
    vk.audio.save(server=_json.get('server'), hash=_json.get('hash'), audio=_json.get('audio'))

    file_dict = {
        'name': basename,
        'size': instance.flac.file.size,

        # The assumption is that file_field is a FileField that saves to
        # the 'media' directory.
        'url': settings.MEDIA_URL + 'flac/' + basename,
        'thumbnail_url': settings.MEDIA_URL + 'flac/' + basename,
        'delete_url': reverse('jfu_delete', kwargs={'pk': instance.pk}),
        'delete_type': 'POST',
        'r' : r.text
    }

    return UploadResponse(request, file_dict)

@require_POST
def upload_delete( request, pk ):
    # An example implementation.
    success = True
    try:
        instance = Track.objects.get( pk = pk )
        os.unlink(instance.flac.file.name)
        instance.delete()
    except Track.DoesNotExist:
        success = False

    return JFUResponse( request, success )