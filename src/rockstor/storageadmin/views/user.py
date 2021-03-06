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

from rest_framework.response import Response
from django.db import transaction
from django.conf import settings
from storageadmin.util import handle_exception
from django.contrib.auth.models import User as DjangoUser
from storageadmin.serializers import SUserSerializer
from storageadmin.models import (User, Group)
import rest_framework_custom as rfc
from system.users import (useradd, usermod, userdel,
                          smbpasswd, add_ssh_key, update_shell)
from storageadmin.exceptions import RockStorAPIException
import pwd
from system.ssh import is_pub_key
from ug_helpers import (combined_users, combined_groups)
import logging
import re
logger = logging.getLogger(__name__)


class UserView(rfc.GenericView):
    serializer_class = SUserSerializer
    exclude_list = ('root', 'nobody', 'bin', 'daemon', 'adm', 'sync',
                    'shutdown', 'halt', 'mail', 'operator', 'dbus', 'rpc',
                    'avahi', 'avahi-autoipd', 'rpcuser', 'nfsnobody',
                    'postgres', 'ntp', 'nginx', 'postfix', 'sshd', )

    def get_queryset(self, *args, **kwargs):
        if ('username' in kwargs):
            self.paginate_by = 0
            try:
                return User.objects.get(username=kwargs['username'])
            except:
                return []
        return combined_users()

    def _validate_input(self, request):
        input_fields = {}
        username = request.DATA.get('username', None)
        if (username is None or
            re.match(settings.USERNAME_REGEX, username) is None):
            e_msg = ('Username is invalid. It must confirm to the regex: %s' %
                     (settings.USERNAME_REGEX))
            handle_exception(Exception(e_msg), request)
        if (len(username) > 30):
            e_msg = ('Username cannot be more than 30 characters long')
            handle_exception(Exception(e_msg), request)
        input_fields['username'] = username
        password = request.DATA.get('password', None)
        if (password is None or password == ''):
            e_msg = ('Password must be a valid string')
            handle_exception(Exception(e_msg), request)
        input_fields['password'] = password
        admin = request.DATA.get('admin', True)
        if (type(admin) != bool):
            e_msg = ('Admin(user type) must be a boolean')
            handle_exception(Exception(e_msg), request)
        input_fields['admin'] = admin
        shell = request.DATA.get('shell', '/bin/bash')
        if (shell not in settings.VALID_SHELLS):
            e_msg = ('shell(%s) is not valid. Valid shells are %s' %
                     (shell, settings.VALID_SHELLS))
            handle_exception(Exception(e_msg), request)
        input_fields['shell'] = shell
        email = request.DATA.get('email', None)
        if (email is not None and type(email) != unicode):
            e_msg = ('Email must be a valid string. not: %s' % type(email))
            handle_exception(Exception(e_msg), request)
        input_fields['email'] = email
        input_fields['homedir'] = request.DATA.get(
            'homedir', '/home/%s' % username)
        input_fields['uid'] = request.DATA.get('uid', None)
        input_fields['group'] = request.DATA.get('group', None)
        input_fields['public_key'] = self._validate_public_key(request)
        return input_fields

    def _validate_public_key(self, request):
        public_key = request.DATA.get('public_key', None)
        if (public_key is not None and not is_pub_key(public_key)):
            e_msg = ('Public key is invalid')
            handle_exception(Exception(e_msg), request)

    @transaction.commit_on_success
    def post(self, request):
        try:
            invar = self._validate_input(request)
            logger.debug('input = %s' % invar)

            # Check that a django user with the same name does not exist
            e_msg = ('user: %s already exists. Please choose a different'
                     ' username' % invar['username'])
            if (DjangoUser.objects.filter(
                    username=invar['username']).exists()):
                handle_exception(Exception(e_msg), request)
            users = combined_users()
            for u in users:
                if (u.username == invar['username']):
                    handle_exception(Exception(e_msg), request)
                if (u.uid == invar['uid']):
                    e_msg = ('uid: %d already exists.' % invar['uid'])
                    handle_exception(Exception(e_msg), request)

            groups = combined_groups()
            invar['gid'] = None
            admin_group = None
            if (invar['group'] is not None):
                for g in groups:
                    if (g.groupname == invar['group']):
                        invar['gid'] = g.gid
                        admin_group = g
                        break

            if (invar['admin']):
                # Create Django user
                auser = DjangoUser.objects.create_user(invar['username'],
                                                       None, invar['password'])
                auser.is_active = True
                auser.save()
                invar['user'] = auser

            useradd(invar['username'], invar['shell'], uid=invar['uid'],
                    gid=invar['gid'])
            pw_entries = pwd.getpwnam(invar['username'])
            invar['uid'] = pw_entries[2]
            invar['gid'] = pw_entries[3]
            usermod(invar['username'], invar['password'])
            smbpasswd(invar['username'], invar['password'])
            if (invar['public_key'] is not None):
                add_ssh_key(invar['username'], invar['public_key'])
            del(invar['password'])
            invar['group'] = None
            if (admin_group is None):
                admin_group = Group(gid=invar['gid'],
                                    groupname=invar['username'],
                                    admin=True)
                admin_group.save()
                invar['group'] = admin_group
            invar['admin'] = True
            suser = User(**invar)
            suser.save()
            return Response(SUserSerializer(suser).data)
        except RockStorAPIException:
            raise
        except Exception, e:
            handle_exception(e, request)

    @transaction.commit_on_success
    def put(self, request, username):
        if (username in self.exclude_list):
            if (username != 'root'):
                e_msg = ('Editing restricted user(%s) is not supported.' %
                         username)
                handle_exception(Exception(e_msg), request)
        email = request.DATA.get('email', None)
        new_pw = request.DATA.get('password', None)
        shell = request.DATA.get('shell', None)
        public_key = self._validate_public_key(request)
        admin = request.DATA.get('admin', False)
        if (User.objects.filter(username=username).exists()):
            u = User.objects.get(username=username)
            if (admin is True):
                if (u.user is None):
                    if (new_pw is None):
                        e_msg = ('password reset is required to enable admin '
                                 'access. please provide a new password')
                        handle_exception(Exception(e_msg), request)
                    auser = DjangoUser.objects.create_user(username,
                                                           None, new_pw)
                    auser.is_active = True
                    auser.save()
                    u.user = auser
                    u.save()
                elif (new_pw is not None):
                    u.user.set_password(new_pw)
                    u.user.save()
            elif (u.user is not None):
                auser = u.user
                u.user = None
                auser.delete()

            u.public_key = public_key
            if (email is not None and email != ''):
                u.email = email
            if (shell is not None and shell != u.shell):
                u.shell = shell
            u.save()

        sysusers = combined_users()
        suser = None
        for u in sysusers:
            if (u.username == username):
                suser = u
                if (new_pw is not None):
                    usermod(username, new_pw)
                    smbpasswd(username, new_pw)
                if (shell is not None):
                    update_shell(username, shell)
                if (public_key is not None):
                    add_ssh_key(username, public_key)
                break
        if (suser is None):
            e_msg = ('User(%s) does not exist' % username)
            handle_exception(Exception(e_msg), request)

        return Response(SUserSerializer(suser).data)

    @transaction.commit_on_success
    def delete(self, request, username):
        if request.user.username == username:
            e_msg = ('Cannot delete the currently logged in user')
            handle_exception(Exception(e_msg), request)

        if (username in self.exclude_list):
            e_msg = ('Delete of restricted user(%s) is not supported.' %
                     username)
            handle_exception(Exception(e_msg), request)

        gid = None
        if (User.objects.filter(username=username).exists()):
            u = User.objects.get(username=username)
            if (u.user is not None):
                u.user.delete()
            gid = u.gid
            u.delete()
        else:
            sysusers = combined_users()
            found = False
            for u in sysusers:
                if (u.username == username):
                    found = True
                    break
            if (found is False):
                e_msg = ('User(%s) does not exist' % username)
                handle_exception(Exception(e_msg), request)

        for g in combined_groups():
            if (g.gid == gid and g.admin and
                not User.objects.filter(gid=gid).exists()):
                g.delete()

        try:
            userdel(username)
        except Exception, e:
            logger.exception(e)
            e_msg = ('A low level error occured while deleting the user: %s' %
                     username)
            handle_exception(Exception(e_msg), request)

        return Response()
