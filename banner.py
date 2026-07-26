"""
Minimal client for a public Ellucian Banner 9 "Browse Classes" self-service
API (the same endpoints https://<host>/StudentRegistrationSsb/ssb/... serves
to any anonymous visitor searching for classes).

Stdlib only - no pip installs required, matching the rest of this repo
(the local watcher uses curl.exe, the cloud check uses curl+jq).
"""
import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "class-bot-discover/1.0"


class BannerClient:
    def __init__(self, host, timeout=25):
        self.base = f"https://{host}/StudentRegistrationSsb/ssb"
        self.timeout = timeout
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def _request(self, method, path, params=None, data=None):
        url = f"{self.base}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, method=method, headers={"User-Agent": USER_AGENT})
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"{method} {path} -> HTTP {exc.code}") from exc

    def _get_json(self, path, params=None):
        raw = self._request("GET", path, params=params)
        return json.loads(raw) if raw else None

    def prime(self, term):
        """Start a session and select a term, same handshake a browser does
        before it's allowed to hit classSearch/searchResults."""
        self._request("GET", "/term/termSelection", params={"mode": "search"})
        self._request(
            "POST",
            "/term/search",
            data={
                "term": term or "",
                "studyPath": "",
                "studyPathText": "",
                "startDatepicker": "",
                "endDatepicker": "",
            },
        )

    def get_vocab(self, name, term=""):
        """name is one of: subject, campus, partOfTerm, instructionalMethod,
        attribute, instructor, ... (the classSearch/get_<name> family)."""
        return self._get_json(
            f"/classSearch/get_{name}",
            params={"searchTerm": "", "term": term, "offset": 1, "max": 500},
        )

    def get_terms(self, search_term=""):
        return self._get_json(
            "/classSearch/getTerms",
            params={"searchTerm": search_term, "offset": 1, "max": 50},
        )

    def search(self, term, subject="", course="", page_offset=0, page_max=500):
        params = {
            "txt_term": term,
            "pageOffset": page_offset,
            "pageMaxSize": page_max,
            "sortColumn": "subjectDescription",
            "sortDirection": "asc",
        }
        if subject:
            params["txt_subject"] = subject
        if course:
            params["txt_courseNumber"] = course
        return self._get_json("/searchResults/searchResults", params=params) or {}
