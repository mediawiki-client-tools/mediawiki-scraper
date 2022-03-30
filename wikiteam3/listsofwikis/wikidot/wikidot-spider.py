#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (C) 2018 WikiTeam developers
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

import random
import re
import requests
import time

from dumpgenerator.user_agent import UserAgent
from urllib.parse import unquote


def main():
    requests.Session().headers = {"User-Agent": str(UserAgent())}

    wikis = []
    with open("wikidot-spider.txt", "r") as wikidot_spider_file:
        wikis = wikidot_spider_file.read().strip().splitlines()

    for i in range(1, 1000000):
        url = random.choice(wikis)
        print("URL search", url)
        try:
            html = requests.Session().get(url).read().decode("utf-8")
        except Exception:
            print("Search error")
            time.sleep(30)
            continue
        html = unquote(html)
        match = re.findall(r"://([^/]+?\.wikidot\.com)", html)
        for wiki in match:
            wiki = "http://" + wiki
            if not wiki in wikis:
                wikis.append(wiki)
                wikis.sort()
                print(wiki)
        with open("wikidot-spider.txt", "w") as wikidot_spider_file:
            wikis2 = []
            for wiki in wikis:
                wiki = re.sub(r"https?://www\.", "http://", wiki)
                if not wiki in wikis2:
                    wikis2.append(wiki)
            wikis = wikis2
            wikis.sort()
            wikidot_spider_file.write("\n".join(wikis))
        print("%d wikis found" % (len(wikis)))
        sleep = random.randint(1, 5)
        print("Sleeping %d seconds" % (sleep))
        time.sleep(sleep)


if __name__ == "__main__":
    main()
