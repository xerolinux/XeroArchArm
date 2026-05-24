"""Background worker that queries the Arch Linux package search API (aarch64 only)."""
import json
import urllib.request
import urllib.parse

from PySide6.QtCore import QThread, Signal

_API           = 'https://archlinux.org/packages/search/json/'
_VALID_ARCHES  = {'aarch64', 'any'}   # 'any' = arch-independent packages


class PkgSearchWorker(QThread):
    # list of (pkgname, repo, arch, desc)
    results = Signal(list)
    failed  = Signal(str)

    def __init__(self, query: str, parent=None):
        super().__init__(parent)
        self._query = query

    def run(self) -> None:
        try:
            # Request aarch64 from the API; also fetch 'any' arch separately
            # because the API's arch filter is exact-match.
            results_combined: list[dict] = []
            for arch in ('aarch64', 'any'):
                params = urllib.parse.urlencode({'q': self._query, 'arch': arch})
                req = urllib.request.Request(
                    f'{_API}?{params}',
                    headers={'User-Agent': 'XeroPi4/1.0'},
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read())
                results_combined.extend(data.get('results', []))

            # De-duplicate by pkgname (keep first occurrence)
            seen: set[str] = set()
            out: list[tuple] = []
            for r in results_combined:
                arch = r.get('arch', '')
                # Client-side safety filter — drop anything not aarch64/any
                if arch not in _VALID_ARCHES:
                    continue
                pkg = r['pkgname']
                if pkg in seen:
                    continue
                seen.add(pkg)
                out.append((pkg, r.get('repo', '?'), arch, r.get('pkgdesc', '')))
                if len(out) >= 60:
                    break

            self.results.emit(out)
        except Exception as e:
            self.failed.emit(str(e))
