from __future__ import annotations

from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlparse, urlunparse


def absolutize(base_url: str, maybe_relative: str) -> str:
    parsed_base = urlparse(base_url)
    base_params = dict(parse_qsl(parsed_base.query, keep_blank_values=True))

    # Some documentation portals wrap the real document path inside a returnurl
    # query param. Resolve relative links against that inner path, then rebuild
    # the secured wrapper URL.
    if "returnurl" in base_params:
        inner_base = _normalize_inner_base(base_params["returnurl"])
        resolved_inner = urljoin(inner_base, maybe_relative)
        rebuilt_params = list(parse_qsl(parsed_base.query, keep_blank_values=True))
        rebuilt_query = []
        replaced = False
        for key, value in rebuilt_params:
            if key == "returnurl":
                rebuilt_query.append((key, resolved_inner))
                replaced = True
            else:
                rebuilt_query.append((key, value))
        if not replaced:
            rebuilt_query.append(("returnurl", resolved_inner))
        return urlunparse(parsed_base._replace(query=urlencode(rebuilt_query)))
    return urljoin(base_url, maybe_relative)


def _normalize_inner_base(inner_url: str) -> str:
    parsed = urlparse(inner_url)
    path = parsed.path or "/"

    # Some portals append a trailing slash after a file path like ".../page.html/".
    if path.endswith("/") and "." in path.rstrip("/").split("/")[-1]:
        trimmed_path = path.rstrip("/")
        directory = trimmed_path.rsplit("/", 1)[0] + "/"
        return urlunparse(parsed._replace(path=directory))

    return inner_url


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url)
    normalized_query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    normalized_path = parsed.path or "/"
    if normalized_path != "/" and normalized_path.endswith("/"):
        normalized_path = normalized_path[:-1]

    clean = parsed._replace(
        params="",
        fragment="",
        path=normalized_path,
        query=normalized_query,
    )
    return urlunparse(clean)


def same_domain(url: str, allowed_domains: list[str]) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == domain.lower() or host.endswith(f".{domain.lower()}") for domain in allowed_domains)


def extract_effective_path(url: str) -> str:
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    return_url = params.get("returnurl", [None])[0]
    if return_url:
        return urlparse(return_url).path or "/"
    return parsed.path or "/"
