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

from django.db import transaction
from storageadmin.models import User, Setup, OauthApp
from storageadmin.views import UserView
from oauth2_provider.models import Application as OauthApplication
from django.contrib.auth.models import User as DjangoUser


class SetupUserView(UserView):

    authentication_classes = ()
    permission_classes = ()

    @transaction.commit_on_success
    def post(self, request):
        setup = Setup.objects.all()[0]
        setup.setup_user = True
        setup.save()

        # Create user
        res = super(SetupUserView, self).post(request)
        # Create cliapp id and secret for oauth
        name = 'cliapp'
        user = User.objects.get(username=request.DATA['username'])
        duser = DjangoUser.objects.get(username=request.DATA['username'])
        client_type = OauthApplication.CLIENT_CONFIDENTIAL
        auth_grant_type = OauthApplication.GRANT_CLIENT_CREDENTIALS
        app = OauthApplication(name=name, client_type=client_type,
                               authorization_grant_type=auth_grant_type,
                               user=duser)
        app.save()
        oauth_app = OauthApp(name=name, application=app, user=user)
        oauth_app.save()
        return res

    def put(self, request, username):
        pass

    def delete(self, request, username):
        pass
