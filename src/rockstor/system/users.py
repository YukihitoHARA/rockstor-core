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

from exceptions import CommandException
from osi import run_command
import subprocess
import re
import os
import pwd
import grp

import logging
logger = logging.getLogger(__name__)

USERADD = '/usr/sbin/useradd'
GROUPADD = '/usr/sbin/groupadd'
USERDEL = '/usr/sbin/userdel'
GROUPDEL = '/usr/sbin/groupdel'
PASSWD = '/usr/bin/passwd'
USERMOD = '/usr/sbin/usermod'
SMBPASSWD = '/usr/bin/smbpasswd'
CHOWN = '/usr/bin/chown'


def get_users(min_uid=5000, uname=None):
    users = {}
    for u in pwd.getpwall():
        users[u.pw_name] = (u.pw_uid, u.pw_gid,)
    return users


def get_groups():
    groups = {}
    for g in grp.getgrall():
        groups[g.gr_name] = g.gr_gid
    return groups


def userdel(uname):
    try:
        pwd.getpwnam(uname)
    except KeyError:
        # user doesn't exist
        return

    return run_command([USERDEL, '-r', uname])


def groupdel(groupname):
    try:
        return run_command([GROUPDEL, groupname])
    except CommandException, e:
        if (e.rc != 6):
            raise e


def get_epasswd(username):
    with open('/etc/shadow') as sfo:
        for l in sfo.readlines():
            fields = l.split(':')
            if (re.match(fields[0], username) is not None):
                return fields[1]
    return None


def usermod(username, passwd):
    cmd = [PASSWD, '--stdin', username]
    p = subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, stdin=subprocess.PIPE)
    out, err = p.communicate(input=passwd)
    rc = p.returncode
    if (rc != 0):
        raise CommandException(out, err, rc)
    return (out, err, rc)


def smbpasswd(username, passwd):
    cmd = [SMBPASSWD, '-s', '-a', username]
    p = subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, stdin=subprocess.PIPE)
    pstr = ('%s\n%s\n' % (passwd, passwd))
    out, err = p.communicate(input=pstr)
    rc = p.returncode
    if (rc != 0):
        raise CommandException(out, err, rc)
    return (out, err, rc)


def update_shell(username, shell):
    return run_command([USERMOD, '-s', shell, username])


def useradd(username, shell, uid=None, gid=None):
    cmd = [USERADD, '-s', shell, '-m', username]
    if (uid is not None):
        cmd.insert(-1, '-u')
        cmd.insert(-1, str(uid))
    if (gid is not None):
        cmd.insert(-1, '-g')
        cmd.insert(-1, str(gid))
    return run_command(cmd)


def groupadd(groupname, gid=None):
    cmd = ([GROUPADD, groupname])
    if (gid is not None):
        cmd.insert(-1, '-g')
        cmd.insert(-1, gid)
    return run_command(cmd)


def add_ssh_key(username, key):
    SSH_DIR = '/home/%s/.ssh' % username
    AUTH_KEYS = '%s/authorized_keys' % SSH_DIR
    if (not os.path.isdir(SSH_DIR)):
        os.mkdir(SSH_DIR)
    with open(AUTH_KEYS, 'w') as afo:
        afo.write('%s\n' % key)
    os.chmod(AUTH_KEYS, 0600)
    run_command([CHOWN, '%s:%s' % (username, username), AUTH_KEYS])
