from django.db import models
from django.contrib.auth.models import User
import os.path
import hashlib


def _upload_to(instance, filename):
    basename, ext = os.path.splitext(filename)
    return "flac/%s" % hashlib.md5(filename.encode("utf-8")).hexdigest() + ext

class Track(models.Model):
    flac = models.FileField(null=True, upload_to=_upload_to)
    mp3 = models.FileField(null=True, upload_to='mp3')
    user = models.ForeignKey(User)
    uploaded = models.BooleanField(default=False)
    vk_path = models.CharField(max_length=300, null=True)
    vk_hash = models.CharField(max_length=300, null=True)

    def flac_name(self):
        return os.path.basename(self.flac.name)

    def has_mp3(self):
        return bool(self.mp3)