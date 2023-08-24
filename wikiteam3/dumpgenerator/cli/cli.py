
import argparse
import datetime
import http
import http.cookiejar
import os
import queue
import re
import sys
from typing import Tuple, Dict

import requests
import urllib3

from wikiteam3.dumpgenerator.api import check_retry_API, mediawiki_get_API_and_Index, get_WikiEngine
from wikiteam3.dumpgenerator.api.index_check import checkIndex
from wikiteam3.dumpgenerator.cli.delay import Delay
from wikiteam3.dumpgenerator.config import Config, new_config
from wikiteam3.dumpgenerator.version import getVersion
from wikiteam3.utils import url2prefix_from_config, get_random_UserAgent, mod_requests_text
from wikiteam3.utils.login import uniLogin
from wikiteam3.utils.user_agent import setup_random_UserAgent


def getArgumentParser():
    parser = argparse.ArgumentParser(description="")

    # General params
    parser.add_argument("-v", "--version", action="version", version=getVersion())
    parser.add_argument(
        "--cookies", metavar="cookies.txt", help="path to a cookies.txt file"
    )
    parser.add_argument(
        "--delay", metavar="1.5", default=1.5, type=float,
        help="adds a delay (in seconds) "
        "[NOTE: most HTTP servers have a 5s HTTP/1.1 keep-alive timeout, you should consider it "
        "if you wanna reuse the connection]"
    )
    parser.add_argument(
        "--retries", metavar="5", default=5, help="Maximum number of retries for "
    )
    parser.add_argument("--path", help="path to store wiki dump at")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="resumes previous incomplete dump (requires --path)",
    )
    parser.add_argument('--upload', action='store_true', 
                        help='Upload wikidump to Internet Archive after successfully dumped'
    )
    parser.add_argument("-g", "--uploader-arg", dest="uploader_args", action='append', default=[],
                        help="Arguments for uploader.")
    parser.add_argument("--force", action="store_true", help="")
    parser.add_argument("--user", help="Username if MedaiWiki authentication is required.")
    parser.add_argument(
        "--pass", dest="password", help="Password if MediaWiki authentication is required."
    )
    parser.add_argument(
        "--http-user", dest="http_user", help="Username if HTTP authentication is required."
    )
    parser.add_argument(
        "--http-pass", dest="http_password", help="Password if HTTP authentication is required."
    )
    parser.add_argument(
        '--insecure', action='store_true', help='Disable SSL certificate verification'
    )
    parser.add_argument(
        "--user-agent",
        type=str,
        default="wikiteam3/" + getVersion(),
        help="User-Agent to use for requests (default: wikiteam3/<version>)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help=""
    )
    parser.add_argument(
        "--stdout-log-file", dest="stdout_log_path", default=None, help="Path to copy stdout to",
    )

    # URL params
    groupWikiOrAPIOrIndex = parser.add_argument_group()
    groupWikiOrAPIOrIndex.add_argument(
        "wiki", default="", nargs="?", help="URL to wiki (e.g. http://wiki.domain.org), auto detects API and index.php"
    )
    groupWikiOrAPIOrIndex.add_argument(
        "--api", help="URL to API (e.g. http://wiki.domain.org/w/api.php)"
    )
    groupWikiOrAPIOrIndex.add_argument(
        "--index", help="URL to index.php (e.g. http://wiki.domain.org/w/index.php), (not supported with --images on newer(?) MediaWiki without --api)"
    )

    # Download params
    groupDownload = parser.add_argument_group(
        "Data to download", "What info download from the wiki"
    )
    groupDownload.add_argument(
        "--xml",
        action="store_true",
        help="Export XML dump using Special:Export (index.php). (supported with --curonly)",
    )
    groupDownload.add_argument(
        "--curonly", action="store_true", help="store only the lastest revision of pages"
    )
    groupDownload.add_argument(
        "--xmlapiexport",
        action="store_true",
        help="Export XML dump using API:revisions instead of Special:Export, use this when Special:Export fails and xmlrevisions not supported. (supported with --curonly)",
    )
    groupDownload.add_argument(
        "--xmlrevisions",
        action="store_true",
        help="Export all revisions from an API generator (API:Allrevisions). MediaWiki 1.27+ only. (not supported with --curonly)",
    )
    groupDownload.add_argument(
        "--xmlrevisions_page",
        action="store_true",
        help="[[! Development only !]] Export all revisions from an API generator, but query page by page MediaWiki 1.27+ only. (default: --curonly)",
    )
    groupDownload.add_argument(
        "--images", action="store_true", help="Generates an image dump"
    )
    groupDownload.add_argument(
        "--bypass-cdn-image-compression",
        action="store_true",
        help="Bypass CDN image compression. (CloudFlare Polish, etc.)",
    )
    groupDownload.add_argument(
        "--disable-image-verify",
        action="store_true",
        help="Don't verify image size and hash while downloading. (useful for wikis with server-side image resizing)"
    )
    groupDownload.add_argument(
        "--image-timestamp-interval",
        metavar="2019-01-02T01:36:06Z/2023-08-12T10:36:06Z",
        help="[BETA] Only download images uploaded in the given time interval. [format: ISO 8601 UTC interval] "
            "(only works with api)",
    )
    groupDownload.add_argument(
        "--ia-wbm-booster",
        type=int,
        default=0,
        choices=[0, 1, 2, 3],
        required=False,
        help="Download images from Internet Archive Wayback Machine if possible, reduce the bandwidth usage of the wiki. "
            "[0: disabled (default), 1: use earliest snapshot, 2: use latest snapshot, "
            "3: the closest snapshot to the image's upload time]", 
    )
    groupDownload.add_argument(
        "--namespaces",
        metavar="1,2,3",
        help="comma-separated value of namespaces to include (all by default)",
    )
    groupDownload.add_argument(
        "--exnamespaces",
        metavar="1,2,3",
        help="comma-separated value of namespaces to exclude",
    )
    parser.add_argument(
        "--api_chunksize", metavar="50", default=50, help="Chunk size for MediaWiki API (arvlimit, ailimit, etc.)"
    )

    # Meta info params
    groupMeta = parser.add_argument_group(
        "Meta info", "What meta info to retrieve from the wiki"
    )
    groupMeta.add_argument(
        "--get-wiki-engine", action="store_true", help="returns the wiki engine"
    )
    groupMeta.add_argument(
        "--failfast",
        action="store_true",
        help="[lack maintenance] Avoid resuming, discard failing wikis quickly. Useful only for mass downloads.",
    )
    return parser


def checkParameters(args=argparse.Namespace()) -> bool:

    passed = True

    # Don't mix download params and meta info params
    if (args.xml or args.images) and (args.get_wiki_engine):
        print("ERROR: Don't mix download params and meta info params")
        passed = False

    # No download params and no meta info params? Exit
    if (not args.xml and not args.images) and (not args.get_wiki_engine):
        print("ERROR: Use at least one download param or meta info param")
        passed = False

    # Check user and pass (one requires both)
    if (args.user and not args.password) or (args.password and not args.user):
        print("ERROR: Both --user and --pass are required for authentication.")
        passed = False

    # Check http-user and http-pass (one requires both)
    if (args.http_user and not args.http_password) or (args.http_password and not args.http_user):
        print("ERROR: Both --http-user and --http-pass are required for authentication.")
        passed = False

    # --curonly requires --xml
    if args.curonly and not args.xml:
        print("ERROR: --curonly requires --xml")
        passed = False
    
    # --xmlrevisions not supported with --curonly
    if args.xmlrevisions and args.curonly:
        print("ERROR: --xmlrevisions not supported with --curonly")
        passed = False
    
    # Check URLs
    for url in [args.api, args.index, args.wiki]:
        if url and (not url.startswith("http://") and not url.startswith("https://")):
            print(url)
            print("ERROR: URLs must start with http:// or https://")
            passed = False
    
    return passed

def get_parameters(params=None) -> Tuple[Config, Dict]:
    # if not params:
    #     params = sys.argv

    parser = getArgumentParser()
    args = parser.parse_args(params)
    if checkParameters(args) is not True:
        print("\n\n")
        parser.print_help()
        sys.exit(1)
    # print (args)

    ########################################

    # Create session
    mod_requests_text(requests) # monkey patch # type: ignore
    session = requests.Session()
    def print_request(r: requests.Response, *args, **kwargs):
        # TODO: use logging
        # print("H:", r.request.headers)
        print(f"Resp: {r.request.method} {r.status_code} {r.reason} {r.url}")
        if r.raw._connection.sock:
            print(f"Conn: {r.raw._connection.sock.getsockname()} -> {r.raw._connection.sock.getpeername()[0]}")

    if args.verbose:
        session.hooks['response'].append(print_request)

    # Disable SSL verification
    if args.insecure:
        session.verify = False
        requests.packages.urllib3.disable_warnings() # type: ignore
        print("WARNING: SSL certificate verification disabled")

    # Custom session retry
    try:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        # Courtesy datashaman https://stackoverflow.com/a/35504626
        class CustomRetry(Retry):
            def increment(self, method=None, url=None, *args, **kwargs):
                if '_pool' in kwargs:
                    conn = kwargs['_pool'] # type: urllib3.connectionpool.HTTPSConnectionPool
                    if 'response' in kwargs:
                        try:
                            # drain conn in advance so that it won't be put back into conn.pool
                            kwargs['response'].drain_conn()
                        except:
                            pass
                    # Useless, retry happens inside urllib3
                    # for adapters in session.adapters.values():
                    #     adapters: HTTPAdapter
                    #     adapters.poolmanager.clear()

                    # Close existing connection so that a new connection will be used
                    if hasattr(conn, 'pool'):
                        pool = conn.pool  # type: queue.Queue
                        try:
                            # Don't directly use this, This closes connection pool by making conn.pool = None
                            conn.close()
                        except:
                            pass
                        conn.pool = pool
                return super(CustomRetry, self).increment(method=method, url=url, *args, **kwargs)

            def sleep(self, response=None):
                backoff = self.get_backoff_time()
                if backoff <= 0:
                    return
                if response is not None:
                    msg = 'req retry (%s)' % response.status
                else:
                    msg = None
                Delay(config=None, msg=msg, delay=backoff+5)

        __retries__ = CustomRetry(
            total=int(args.retries), backoff_factor=1,
            status_forcelist=[500, 502, 503, 504, 429],
            allowed_methods=['DELETE', 'PUT', 'GET', 'OPTIONS', 'TRACE', 'HEAD', 'POST']
        )
        session.mount("https://", HTTPAdapter(max_retries=__retries__))
        session.mount("http://", HTTPAdapter(max_retries=__retries__))
    except:
        # Our urllib3/requests is too old
        pass

    # Set cookies
    cj = http.cookiejar.MozillaCookieJar()
    if args.cookies:
        cj.load(args.cookies)
        print("Using cookies from %s" % args.cookies)
    session.cookies = cj

    # Setup user agent
    if args.user_agent:
        session.headers.update({"User-Agent": args.user_agent})
    if args.user_agent == "random":
        session.headers.update({"User-Agent": get_random_UserAgent()})
        setup_random_UserAgent(session) # monkey patch

    # Set accept header
    session.headers.update({"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})

    # Set HTTP Basic Auth
    if args.http_user and args.http_password:
        session.auth = (args.user, args.password)

    # Execute meta info params
    if args.wiki:
        if args.get_wiki_engine:
            print(get_WikiEngine(url=args.wiki, session=session))
            sys.exit(0)

    # Get API and index and verify
    api = args.api if args.api else ""
    index = args.index if args.index else ""
    if api == "" or index == "":
        if args.wiki:
            if get_WikiEngine(args.wiki, session=session) == "MediaWiki":
                api2, index2 = mediawiki_get_API_and_Index(args.wiki, session=session)
                if not api:
                    api = api2
                if not index:
                    index = index2
            else:
                print("ERROR: Unsupported wiki. Wiki engines supported are: MediaWiki")
                sys.exit(1)
        else:
            if api == "":
                pass
            elif index == "":
                index = "/".join(api.split("/")[:-1]) + "/index.php"

    # print (api)
    # print (index)
    index2 = None

    check, checkedapi = False, None
    if api:
        check, checkedapi = check_retry_API(
            api=api,
            apiclient=args.xmlrevisions,
            session=session,
        )

    if api and check:
        # Replace the index URL we got from the API check
        index2 = check[1]
        api = checkedapi
        print("API is OK: ",  checkedapi)
    else:
        if index and not args.wiki:
            print("API not available. Trying with index.php only.")
            args.api = None
        else:
            print("Error in API. Please, provide a correct path to API")
            sys.exit(1)

    # login if needed
    # TODO: Re-login after session expires
    if args.user and args.password:
        _session = uniLogin(api=api, index=index, session=session, username=args.user, password=args.password)
        if _session:
            session = _session
            print("-- Login OK --")
        else:
            print("-- Login failed --")

    # check index
    if index and checkIndex(index=index, cookies=args.cookies, session=session):
        print("index.php is OK")
    else:
        index = index2
        if index and index.startswith("//"):
            index = args.wiki.split("//")[0] + index
        if index and checkIndex(index=index, cookies=args.cookies, session=session):
            print("index.php is OK")
        else:
            try:
                index = "/".join(index.split("/")[:-1])
            except AttributeError:
                index = None
            if index and checkIndex(index=index, cookies=args.cookies, session=session):
                print("index.php is OK")
            else:
                print("Error in index.php.")
                if not args.xmlrevisions:
                    print(
                        "Please, provide a correct path to index.php or use --xmlrevisions. Terminating."
                    )
                    sys.exit(1)


    namespaces = ["all"]
    exnamespaces = []
    # Process namespace inclusions
    if args.namespaces:
        # fix, why - ?  and... --namespaces= all with a space works?
        if (
            re.search(r"[^\d, \-]", args.namespaces)
            and args.namespaces.lower() != "all"
        ):
            print(
                "Invalid namespace values.\nValid format is integer(s) separated by commas"
            )
            sys.exit(1)
        else:
            ns = re.sub(" ", "", args.namespaces)
            if ns.lower() == "all":
                namespaces = ["all"]
            else:
                namespaces = [int(i) for i in ns.split(",")]

    # Process namespace exclusions
    if args.exnamespaces:
        if re.search(r"[^\d, \-]", args.exnamespaces):
            print(
                "Invalid namespace values.\nValid format is integer(s) separated by commas"
            )
            sys.exit(1)
        else:
            ns = re.sub(" ", "", args.exnamespaces)
            if ns.lower() == "all":
                print("You cannot exclude all namespaces.")
                sys.exit(1)
            else:
                exnamespaces = [int(i) for i in ns.split(",")]


    config = new_config({
        "curonly": args.curonly,
        "date": datetime.datetime.now().strftime("%Y%m%d"),
        "api": api,
        "failfast": args.failfast,
        "http_method": "POST",
        "api_chunksize": int(args.api_chunksize),
        "index": index,
        "images": args.images,
        "logs": False,
        "xml": args.xml,
        "xmlapiexport": args.xmlapiexport,
        "xmlrevisions": args.xmlrevisions or args.xmlrevisions_page,
        "xmlrevisions_page": args.xmlrevisions_page,
        "namespaces": namespaces,
        "exnamespaces": exnamespaces,
        "path": args.path and os.path.normpath(args.path) or "",
        "cookies": args.cookies or "",
        "delay": args.delay,
        "retries": int(args.retries),
    })

    other = {
        "resume": args.resume,
        "filenamelimit": 240,  # Filename not be longer than 240 **bytes**. (MediaWiki r98430 2011-09-29)
        "force": args.force,
        "session": session,
        "stdout_log_path": args.stdout_log_path,
        "bypass_cdn_image_compression": args.bypass_cdn_image_compression,
        "disable_image_verify": args.disable_image_verify,
        "image_timestamp_interval": args.image_timestamp_interval,
        "ia_wbm_booster": args.ia_wbm_booster,
        "upload": args.upload,
        "uploader_args": args.uploader_args,
    }

    # calculating path, if not defined by user with --path=
    if not config.path:
        config.path = "./{}-{}-wikidump".format(
            url2prefix_from_config(config=config),
            config.date,
        )
        print("No --path argument provided. Defaulting to:")
        print("  [working_directory]/[domain_prefix]-[date]-wikidump")
        print("Which expands to:")
        print("  " + config.path)

    if config.delay == 1.5:
        print(f"--delay is the default value of {config.delay}")
        print(
            f"There will be a {config.delay} second delay between HTTP calls in order to keep the server from timing you out."
        )
        print(
            "If you know that this is unnecessary, you can manually specify '--delay 0.0'."
        )

    return config, other
