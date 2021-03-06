import datetime, hashlib, json, os, pickle, urllib, urllib2

from Crypto.Cipher import AES

from django.core import serializers

from nudge.models import Batch, BatchItem, Setting, PushHistoryItem
from nudge.exceptions import *
from utils import related_objects

"""
client.py 

commands to send to nudge server
"""

SETTINGS = Setting.objects.get(pk=1)

def encrypt_batch(b_plaintext):
    """encrypts a pickled batch for sending to server"""
    key = SETTINGS.remote_key.decode('hex')
    m = hashlib.md5(os.urandom(16))
    iv = m.digest()
    encobj = AES.new(key, AES.MODE_CBC, iv)
    pad = lambda s: s + (16 - len(s) % 16) * ' '
    return { 'batch': encobj.encrypt(pad(b_plaintext)).encode('hex'), 'iv':iv.encode('hex') }

def serialize_batch(batch):
    """
    returns urlecncoded pickled serialization of a batch ready to be sent to 
    server.
    """
    items = BatchItem.objects.filter(batch=batch)
    versions = []
    # this is so we can inspect the objects, but get back the exact versions requested:
    version_lookup=dict([(item.version.object, item) for item in items])
    objects_exploded=[]
    # find related objects, and put them at the beginning of the exploded list
    for obj in version_lookup.keys():
    	related= related_objects(obj)
    	if related:
    		objects_exploded=related + objects_exploded
    #append the original list to the exploded list
    objects_exploded=[obj for obj in objects_exploded if obj in version_lookup]+version_lookup.keys()
    objects_imploded=[]
    #filter out duplicates and related items that aren't part of this push
    for obj in objects_exploded:
    	if obj not in objects_imploded and obj in version_lookup:
    		objects_imploded.append(obj)
    # put the batch back together. Now, related objects are pushed in a sensible order!
    for obj in objects_imploded:
        versions.append(version_lookup[obj].version)
    batch_items = serializers.serialize("json", versions)
    b_plaintext = pickle.dumps({ 'id':batch.id, 'title':batch.title, 'items':batch_items })
    return urllib.urlencode(encrypt_batch(b_plaintext))
    
def send_command(target, data):
    """
    sends a nudge api command
    """
    url = "%s/nudge-api/%s/" % (SETTINGS.remote_address, target)
    req = urllib2.Request(url, data)
    response = urllib2.urlopen(req)
    return response

def push_batch(batch):
    """
    pushes batch to server, logs push and timestamps on success
    """
    log=PushHistoryItem(batch=batch)
    log.save()
    try:
        response= send_command('batch', serialize_batch(batch))
        batch.pushed = datetime.datetime.now()
        batch.save()
        log.http_result=response.getcode()
        log.save()
        if log.http_result != 200:
            raise BatchPushFailure(http_status=response.getcode())
    except:
        raise BatchPushFailure
