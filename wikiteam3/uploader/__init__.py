#!/usr/bin/env python3

# Uploader uploads a set of already-generated wiki dumps to the Internet Archive.
# Copyright (C) 2011-2023 WikiTeam developers and MediaWiki Client Tools
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

# To learn more, read the documentation:
#     https://github.com/mediawiki-client-tools/mediawiki-dump-generator


from wikiteam3.uploader import Uploader


def main():
    Uploader()