# Copyright (C) 2011-2023 WikiTeam developers and MediaWiki Client Tools
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
# Instructions: https://github.com/mediawiki-client-tools/mediawiki-dump-generator/blob/python3/USAGE.md


import argparse
import os
import re
import shutil
import subprocess
import sys
import time

# This is only to check IDE configuration
current_directory = os.getcwd()
print("Current working directory:", current_directory)

from wikiteam3.dumpgenerator.config import Config
from wikiteam3.utils import domain2prefix

def main():
    parser = argparse.ArgumentParser(prog="launcher")

    parser.add_argument("listofapis")
    parser.add_argument("--7z-path", dest="path7z", metavar="path-to-7z")
    parser.add_argument("--generator-arg", "-g", dest="generator_args", action="append")

    args = parser.parse_args()

    listofapis = args.listofapis

    # None -> literal '7z', which will find the executable in PATH when running subprocesses
    # otherwise -> resolve as path relative to current dir, then make absolute because we will change working dir later
    path7z = str(Path(".", args.path7z).absolute()) if args.path7z is not None else "7z"

    generator_args = args.generator_args if args.generator_args is not None else []

    print("Reading list of APIs from", listofapis)

    wikis = None

    with open(listofapis) as f:
        wikis = f.read().splitlines()

    print("%d APIs found" % (len(wikis)))

    for wiki in wikis:
        print("\n# Downloading", wiki)
        wiki = wiki.lower()
        # Make the prefix in standard way; api and index must be defined, not important which is which
        prefix = domain2prefix(config=Config(api=wiki, index=wiki))

        if zipfilename := next(
            (
                f
                for f in os.listdir(".")
                if f.endswith(".7z") and f.split("-")[0] == prefix
            ),
            None,
        ):
            print(
                "Skipping... This wiki was downloaded and compressed before in",
                zipfilename,
            )
            # Get the archive's file list.
            if (sys.version_info[0] == 3) and (sys.version_info[1] > 0):
                archivecontent = subprocess.check_output(
                    [path7z, "l", zipfilename, "-scsUTF-8"],
                    text=True,
                    encoding="UTF-8",
                    errors="strict",
                )
                if re.search(r"%s.+-history\.xml" % (prefix), archivecontent) is None:
                    # We should perhaps not create an archive in this case, but we continue anyway.
                    print("ERROR: The archive contains no history!")
                if re.search(r"SpecialVersion\.html", archivecontent) is None:
                    print(
                        "WARNING: The archive doesn't contain SpecialVersion.html, this may indicate that download didn't finish."
                    )
            else:
                print("WARNING: Content of the archive not checked, we need 3.1+.")
                # TODO: Find a way like grep -q below without doing a 7z l multiple times?
            continue

        # download
        started = False  # was this wiki download started before? then resume
        wikidir = ""
        for f in os.listdir("."):
            # Ignores date stamp, doesn't check directories
            if f.endswith("wikidump") and f.split("-")[0] == prefix:
                wikidir = f
                started = True
                break  # stop searching, do not explore subdirectories

        subenv = dict(os.environ)
        subenv["PYTHONPATH"] = os.pathsep.join(sys.path)

        # time.sleep(60)
        # Uncomment what above and add --delay=60 in the py calls below for broken wiki farms
        # such as editthis.info, wiki-site.com, wikkii (adjust the value as needed;
        # typically they don't provide any crawl-delay value in their robots.txt).
        if started and wikidir:  # then resume
            print("Resuming download, using directory", wikidir)
            subprocess.call(
                [
                    sys.executable,
                    "-m",
                    "wikiteam3.dumpgenerator",
                    f"--api={wiki}",
                    "--xml",
                    "--images",
                    "--resume",
                    f"--path={wikidir}",
                ]
                + generator_args,
                shell=False,
                env=subenv,
            )
        else:  # download from scratch
            subprocess.call(
                [
                    sys.executable,
                    "-m",
                    "wikiteam3.dumpgenerator",
                    f"--api={wiki}",
                    "--xml",
                    "--images",
                ]
                + generator_args,
                shell=False,
                env=subenv,
            )
            started = True
            # save wikidir now
            for f in os.listdir("."):
                # Ignores date stamp, doesn't check directories
                if f.endswith("wikidump") and f.split("-")[0] == prefix:
                    wikidir = f
                    break  # stop searching, do not explore subdirectories

        prefix = wikidir.split("-wikidump")[0]

        # Start of integrity check section
        # 1st check
        finished = False

        # Check if the process was initiated, the directory exists, and the prefix is defined
        if started and wikidir and prefix:
            # Check for the closing XML tag </mediawiki> in the last line of the history file
            if subprocess.call(
                [f'tail -n 1 {wikidir}/{prefix}-history.xml | grep -q "</mediawiki>"'],
                shell=True,
            ):
                print(
                    "No </mediawiki> tag found: dump failed, needs fixing; resume didn't work. Exiting."
                )
            else:
                finished = True

        # If the 1st check passed
        if finished:
            time.sleep(1)
            os.chdir(wikidir)
            print("Changed directory to", os.getcwd())

            # 2nd check
            # Perform a basic integrity check for the XML files
            # Count various XML tags to assess file integrity
            subprocess.call(
                'grep -c "<title(.*?)>" *.xml;grep -c "<page(.*?)>" *.xml;grep -c "</page>" *.xml; grep -c "<revision(.*?)>" *.xml;grep -c "</revision>" *.xml',
                shell=True,
            )
        # End of integrity check section

            # Start of compression section
            # Compress history, titles, index, SpecialVersion, errors log, and siteinfo into an archive
            pathHistoryTmp = Path("..", f"{prefix}-history.xml.7z.tmp")
            pathHistoryFinal = Path("..", f"{prefix}-history.xml.7z")
            pathFullTmp = Path("..", f"{prefix}-wikidump.7z.tmp")
            pathFullFinal = Path("..", f"{prefix}-wikidump.7z")

            # Make an archive with all the text and metadata at default compression.
            # You can also add config.txt if you don't care about your computer and user names being published or you don't use full paths so that they're not stored in it.
            compressed = subprocess.call(
                [
                    path7z,
                    "a",
                    "-ms=off",
                    "--",
                    str(pathHistoryTmp),
                    f"{prefix}-history.xml",
                    f"{prefix}-titles.txt",
                    "index.html",
                    "SpecialVersion.html",
                    "errors.log",
                    "siteinfo.json",
                ],
                shell=False,
            )
            if compressed < 2:
                pathHistoryTmp.rename(pathHistoryFinal)
            else:
                print("ERROR: Compression failed, will have to retry next time")
                pathHistoryTmp.unlink()

            # Compress any images and other media files into another archive
            shutil.copy(pathHistoryFinal, pathFullTmp)

            subprocess.call(
                [
                    path7z,
                    "a",
                    "-ms=off",
                    "-mx=1",
                    "--",
                    str(pathFullTmp),
                    f"{prefix}-images.txt",
                    "images/",
                ],
                shell=False,
            )

            pathFullTmp.rename(pathFullFinal)
            # End of compression section

            os.chdir("..")
            print("Changed directory to", os.getcwd())
            time.sleep(1)


if __name__ == "__main__":
    main()