"""
Copyright (c) 2012-2013 RockStor, Inc. <http://rockstor.com>
This file is part of RockStor.

RockStor is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published
by the Free Software Foundation; either version 2 of the License,
or (at your option) any later version.

RockStor is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import requests
import json
import uuid
from rest_framework.response import Response
from django.db import transaction
from storageadmin.models import Appliance
from storageadmin.util import handle_exception
from storageadmin.serializers import ApplianceSerializer
from system.osi import (hostid, sethostname)
import rest_framework_custom as rfc
from cli.rest_util import (api_call, set_token)

import logging
logger = logging.getLogger(__name__)


class AppliancesView(rfc.GenericView):
    serializer_class = ApplianceSerializer

    def get_queryset(self, *args, **kwargs):
        if ('ip' in kwargs or 'id' in kwargs):
            self.paginate_by = 0
            try:
                if ('ip' in kwargs):
                    return Appliance.objects.get(ip=kwargs['ip'])
                return Appliance.objects.get(id=kwargs['id'])
            except:
                return []
        return Appliance.objects.all()

    def _get_remote_appliance(self, request, ip, port, client_id,
                              client_secret):
        with self._handle_exception(request):
            base_url = ('https://%s:%s' % (ip, port))
            set_token(client_id=client_id, client_secret=client_secret,
                      url=base_url)
            ad = api_call('%s/api/appliances/1' % base_url)
            logger.debug('remote appliance: %s' % ad)
            return ad['uuid']

    def _connect_to_appliance(self, request, url, ip, username, password):
        try:
            r = requests.post(
                url,
                headers={'content-type': 'application/json'},
                verify=False,
                data=json.dumps({'username': username,
                                 'password': password}),
                timeout=30.0)
            if (r.status_code == 401):
                #login incorrect
                logger.error(r.text)
                e_msg = ('Authentication to the remote Rockstor '
                         'appliance(%s) failed due to wrong username or '
                         'password. Try again.' % ip)
                handle_exception(Exception(e_msg), request)
            if (r.status_code != 200):
                logger.error(r.text)
                e_msg = ('Could not establish connection with the remote '
                         'Rockstor appliance(%s)')
                handle_exception(e_msg, request)
        except requests.exceptions.ConnectionError, e:
            logger.exception(e)
            e_msg = ('Could not reach the remote Rockstor appliance(%s). '
                     'Verify the IP or hostname provided and try again' % ip)
            handle_exception(Exception(e_msg), request)
        except requests.exceptions.Timeout, e:
            logger.exception(e)
            e_msg = ('Timeout occured while connecting to the remote '
                     'Rockstor appliance(%s). Try again later.' % ip)
            handle_exception(Exception(e_msg), request)

    @transaction.commit_on_success
    def post(self, request):
        with self._handle_exception(request):
            ip = request.DATA['ip']
            current_appliance = request.DATA['current_appliance']
            # authenticate if not adding current appliance
            if (Appliance.objects.filter(ip=ip).exists()):
                e_msg = ('The appliance with ip = %s already exists and '
                         'cannot be added again' % ip)
                handle_exception(Exception(e_msg), request)
            if (current_appliance is False):
                client_id = request.DATA['client_id']
                client_secret = request.DATA['client_secret']
                try:
                    mgmt_port = int(request.DATA['mgmt_port'])
                except Exception, e:
                    logger.exception(e)
                    e_msg = ('Invalid managemetn port(%s) supplied. Try '
                             'again' % request.DATA['mgmt_port'])
                    handle_exception(Exception(e_msg), request)
                url = ('https://%s' % ip)
                if (mgmt_port != 443):
                    url = ('%s:%s' % (url, mgmt_port))
                ra_uuid = self._get_remote_appliance(request, ip, mgmt_port,
                                                     client_id, client_secret)
                appliance = Appliance(uuid=ra_uuid, ip=ip, mgmt_port=mgmt_port,
                                      client_id=client_id,
                                      client_secret=client_secret)
                appliance.save()
            else:
                appliance_uuid = ('%s-%s' % (hostid()[0][0],
                                             str(uuid.uuid4())))
                appliance = Appliance(uuid=appliance_uuid, ip=ip,
                                      current_appliance=True)
                if ('hostname' in request.DATA):
                    appliance.hostname = request.DATA['hostname']
                appliance.save()
                sethostname(ip, appliance.hostname)
            return Response(ApplianceSerializer(appliance).data)

    def delete(self, request, id):
        try:
            appliance = Appliance.objects.get(pk=id)
        except Exception, e:
            logger.exception(e)
            e_msg = ('Appliance with id = %d does not exist' % id)
            handle_exception(Exception(e_msg), request)

        try:
            appliance.delete()
            return Response()
        except Exception, e:
            logger.exception(e)
            e_msg = ('Delete failed for appliance with id = %d' % id)
            handle_exception(e, request)
