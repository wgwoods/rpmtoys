#!/usr/bin/python3
# rpmtoys/repo.py - dumb bits for handling yum/dnf repos
# Copyright (C) 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Author: Will Woods <wwoods@redhat.com>

import os


# fun fact: this is waaayyy faster than reading repodata
def iter_repo_rpms(paths):
    if type(paths) == str:
        paths = [paths]
    for path in paths:
        for top, dirs, files in os.walk(path):
            for f in files:
                if f.endswith(".rpm"):
                    yield os.path.join(top, f)
