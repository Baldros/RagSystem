from rag_project.utils.url import absolutize, canonicalize_url


def test_canonicalize_url_removes_fragment_and_sorts_query() -> None:
    value = canonicalize_url("https://docs.example.com/path/?b=2&a=1#anchor")
    assert value == "https://docs.example.com/path?a=1&b=2"


def test_absolutize_resolves_returnurl_relative_links_for_secured_docs() -> None:
    value = absolutize(
        "https://ansyshelp.ansys.com/public/account/secured?returnurl=/Views/Secured/corp/v261/en/flu_ug/flu_ug.html/",
        "flu_ug_materials_task_page.html",
    )
    assert (
        value
        == "https://ansyshelp.ansys.com/public/account/secured?returnurl=%2FViews%2FSecured%2Fcorp%2Fv261%2Fen%2Fflu_ug%2Fflu_ug_materials_task_page.html"
    )
