#!/usr/bin/env python3

# Copyright (C) 2011 WikiTeam
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

# using a list of wikia subdomains, it downloads all dumps available in Special:Statistics pages
# you can use the list available at the "listofwikis" directory, the file is called wikia.com and it contains +200k wikis


import os
import re
import sys

import requests


class WikiaDownloader:

    """
    instructions:

    it requires a list of wikia wikis
    there is one in the repository (listofwikis directory)

    run it: python wikiadownloader.py

    it you want to resume: python wikiadownloader.py wikitostartfrom

    where wikitostartfrom is the last downloaded wiki in the previous session

    """

    def __init__():

        with open("./wikiteam3/listsofwikis/mediawiki/wikia.com") as wikia_list_file:
            wikia = wikia_list_file.read().strip().split("\n")

        print(len(wikia), "wikis in Wikia list")

        start = "!"
        if len(sys.argv) > 1:
            start = sys.argv[1]

        for wiki in wikia:
            wiki = wiki.lower()
            prefix = ""
            if "http://" in wiki:
                prefix = wiki.split("http://")[1]
            else:
                prefix = wiki.split(".")[0]
                wiki = "https://" + wiki
            if prefix < start:
                continue
            print("\n<" + prefix + ">")
            print(" starting...")

            WikiaDownloader.url = "%s/wiki/Special:Statistics" % (wiki)
            try:
                WikiaDownloader.download(wiki)

            except requests.exceptions.HTTPError as http_error:
                print(
                    " error: returned code %d with reason: %s" % http_error[0],
                    http_error[1],
                )

    def download(wiki):

        with requests.Session().get(
            "%s/wiki/Special:Statistics" % (wiki)
        ) as get_response:
            get_response.raise_for_status()
            html = get_response.text

        match = re.compile(
            r'(?i)<a href="(?P<urldump>http://[^<>]+pages_(?P<dump>current|full)\.xml\.(?P<compression>gz|7z|bz2))">(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2}) (?P<time>\d\d:\d\d:\d\d)'
        )

        for i in match.finditer(html):
            urldump = i.group("urldump")
            dump = i.group("dump")
            date = "{}-{}-{}".format(i.group("year"), i.group("month"), i.group("day"))
            compression = i.group("compression")

            sys.stderr.write("Downloading: ", wiki, dump.lower())

            # {"name":"pages_full.xml.gz","timestamp":1273755409,"mwtimestamp":"20100513125649"}
            # {"name":"pages_current.xml.gz","timestamp":1270731925,"mwtimestamp":"20100408130525"}

            # -q, turn off verbose
            os.system(
                'wget -q -c "%s" -O %s-%s-pages-meta-%s.%s'
                % (
                    urldump,
                    WikiaDownloader.prefix,
                    date,
                    dump.lower() == "current-only" and "current-only" or "history",
                    compression,
                )
            )

        if not match.search(html):
            print(" error: no dumps available")


if __name__ == "__main__":
    WikiaDownloader()
