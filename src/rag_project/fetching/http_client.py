from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.support.ui import WebDriverWait

from rag_project.discovery.toc import extract_toc_entries as extract_toc_entries_from_html
from rag_project.utils.url import absolutize


LOGGER = logging.getLogger(__name__)

COOKIE_BUTTON_XPATH = (
    "//button["
    "contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept') "
    "or contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree') "
    "or contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'allow all') "
    "or contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'cookies')"
    "]"
)

COOKIE_OVERLAY_SELECTORS = [
    "[id*='cookie']",
    "[class*='cookie']",
    "[id*='consent']",
    "[class*='consent']",
    "[aria-label*='cookie']",
]


@dataclass(slots=True)
class HttpResponse:
    url: str
    status_code: int
    text: str
    headers: dict


class HttpClient:
    def __init__(
        self,
        user_agent: str,
        timeout_seconds: int,
        headless: bool = False,
        retry_attempts: int = 3,
        retry_backoff_seconds: float = 2.0,
    ) -> None:
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.headless = headless
        self.retry_attempts = max(1, retry_attempts)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self._driver = None
        self._response_cache: dict[str, HttpResponse] = {}

    def _get_driver(self):
        if self._driver is None:
            edge_options = Options()
            edge_options.page_load_strategy = "eager"
            if self.headless:
                edge_options.add_argument("--headless=new")
                edge_options.add_argument("--disable-gpu")
            edge_options.add_argument("--no-sandbox")
            edge_options.add_argument("--disable-dev-shm-usage")
            edge_options.add_argument("--window-size=1920,1080")
            edge_options.add_argument("--disable-extensions")
            edge_options.add_argument("--disable-background-networking")
            edge_options.add_argument("--log-level=3")
            edge_options.add_argument(f"user-agent={self.user_agent}")
            edge_options.add_experimental_option("excludeSwitches", ["enable-logging"])

            service = Service(log_output=os.devnull)
            self._driver = webdriver.Edge(options=edge_options, service=service)
            self._driver.set_page_load_timeout(self.timeout_seconds)
            LOGGER.info("Edge browser started in %s mode", "headless" if self.headless else "visible")
            if not self.headless:
                self._driver.maximize_window()
        return self._driver

    def get(self, url: str, conditional_headers: dict | None = None) -> HttpResponse:
        del conditional_headers
        cached = self._response_cache.get(url)
        if cached is not None:
            return cached

        driver = self._prepare_page(url)
        response = self._build_response(driver)
        self._cache_response(url, response)
        return response

    def extract_toc_entries(self, url: str, css_selectors: list[str]) -> list[dict]:
        cached = self._response_cache.get(url)
        if cached is not None:
            return extract_toc_entries_from_html(
                html=cached.text,
                base_url=cached.url,
                css_selectors=css_selectors,
            )

        driver = self._prepare_page(url)
        # Cache the rendered snapshot discovered during TOC extraction so the
        # processing stage can reuse it instead of navigating again.
        response = self._build_response(driver)
        self._cache_response(url, response)
        return self._collect_toc_entries_from_dom(driver, css_selectors)

    def _build_response(self, driver) -> HttpResponse:
        return HttpResponse(
            url=driver.current_url,
            status_code=200,
            text=self._capture_rendered_html(driver),
            headers={},
        )

    def _cache_response(self, requested_url: str, response: HttpResponse) -> None:
        self._response_cache[requested_url] = response
        if response.url not in self._response_cache:
            self._response_cache[response.url] = response

    def _prepare_page(self, url: str):
        last_error: Exception | None = None
        for attempt in range(1, self.retry_attempts + 1):
            driver = self._get_driver()
            try:
                LOGGER.info("Opening URL: %s", url)
                if self.retry_attempts > 1:
                    LOGGER.debug("Fetch attempt %s/%s for %s", attempt, self.retry_attempts, url)
                self._navigate(driver, url)
                self._wait_for_initial_dom(driver)
                self._dismiss_cookie_popups(driver)
                self._expand_navigation(driver)
                self._wait_for_content(driver)
                self._flatten_same_origin_iframes(driver)
                return driver
            except WebDriverException as exc:
                last_error = exc
                LOGGER.warning(
                    "Fetch attempt %s/%s failed for %s: %s",
                    attempt,
                    self.retry_attempts,
                    url,
                    exc,
                )
                self._restart_driver()
                if attempt < self.retry_attempts and self.retry_backoff_seconds:
                    time.sleep(self.retry_backoff_seconds)
        LOGGER.error("Failed to fetch %s after %s attempt(s): %s", url, self.retry_attempts, last_error)
        raise last_error  # type: ignore[misc]

    def _navigate(self, driver, url: str) -> None:
        try:
            driver.get(url)
        except TimeoutException:
            LOGGER.warning(
                "Page load timeout for %s after %ss; using the partially loaded DOM",
                url,
                self.timeout_seconds,
            )
            try:
                driver.execute_script("window.stop();")
            except WebDriverException:
                LOGGER.debug("Could not stop page loading after timeout")

    def _wait_for_initial_dom(self, driver) -> None:
        WebDriverWait(driver, self.timeout_seconds).until(
            lambda current_driver: current_driver.execute_script("return document.readyState") in {"interactive", "complete"}
        )
        time.sleep(1.5)

    def _wait_for_content(self, driver) -> None:
        content_probe_script = """
        const rootLinks = document.querySelectorAll("a[href]").length;
        const iframeStats = Array.from(document.querySelectorAll("iframe")).map((iframe) => {
            try {
                const doc = iframe.contentDocument;
                const hrefs = doc ? doc.querySelectorAll("a[href]").length : 0;
                return { accessible: true, hrefs };
            } catch (err) {
                return { accessible: false, hrefs: 0 };
            }
        });
        return {
            rootLinks,
            iframeLinks: iframeStats.map((item) => item.hrefs),
            maxIframeLinks: iframeStats.length ? Math.max(...iframeStats.map((item) => item.hrefs)) : 0,
            accessibleIframeCount: iframeStats.filter((item) => item.accessible).length,
        };
        """
        try:
            WebDriverWait(driver, self.timeout_seconds).until(
                lambda current_driver: (
                    lambda stats: stats["maxIframeLinks"] > 20
                    or (
                        stats["accessibleIframeCount"] == 0
                        and stats["rootLinks"] > 20
                    )
                )(current_driver.execute_script(content_probe_script))
            )
        except TimeoutException:
            LOGGER.debug("Timed out waiting for richer content, continuing with current DOM")

    def _dismiss_cookie_popups(self, driver) -> None:
        self._click_cookie_buttons(driver)
        self._remove_cookie_overlays(driver)
        time.sleep(1.0)

    def _click_cookie_buttons(self, driver) -> None:
        try:
            buttons = driver.find_elements(By.XPATH, COOKIE_BUTTON_XPATH)
            for button in buttons[:5]:
                if button.is_displayed() and button.is_enabled():
                    try:
                        driver.execute_script("arguments[0].click();", button)
                        LOGGER.info("Clicked a cookie/consent button automatically")
                        time.sleep(0.8)
                        return
                    except WebDriverException:
                        continue
        except WebDriverException:
            LOGGER.debug("Failed to inspect cookie buttons")

    def _remove_cookie_overlays(self, driver) -> None:
        selectors = ", ".join(COOKIE_OVERLAY_SELECTORS)
        script = f"""
        const elements = document.querySelectorAll("{selectors}");
        for (const el of elements) {{
            el.style.display = "none";
            el.remove();
        }}
        document.body.style.overflow = "auto";
        return elements.length;
        """
        try:
            removed = driver.execute_script(script)
            if removed:
                LOGGER.info("Removed %s cookie/consent overlay elements", removed)
        except WebDriverException:
            LOGGER.debug("Failed to remove cookie overlays")

    def _flatten_same_origin_iframes(self, driver) -> None:
        script = """
        const iframes = Array.from(document.querySelectorAll("iframe"));
        let flattened = 0;
        for (const iframe of iframes) {
            try {
                const doc = iframe.contentDocument;
                if (!doc || !doc.body) continue;
                const wrapper = document.createElement("div");
                wrapper.setAttribute("data-flattened-iframe", "true");
                const iframeUrl = iframe.contentWindow && iframe.contentWindow.location
                    ? iframe.contentWindow.location.href
                    : iframe.getAttribute("src");
                if (iframeUrl) {
                    wrapper.setAttribute("data-base-url", iframeUrl);
                }
                wrapper.innerHTML = doc.body.innerHTML;
                iframe.replaceWith(wrapper);
                flattened += 1;
            } catch (err) {
                // Cross-origin iframe or inaccessible frame.
            }
        }
        return flattened;
        """
        try:
            flattened = driver.execute_script(script)
            if flattened:
                LOGGER.info("Flattened %s same-origin iframe(s)", flattened)
        except WebDriverException:
            LOGGER.debug("Failed to flatten iframes")

    def _expand_navigation(self, driver) -> None:
        expand_xpath = (
            "//a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'expand all')]"
            " | //button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'expand all')]"
            " | //a[contains(@title, 'Expand')]"
            " | //button[contains(@title, 'Expand')]"
        )
        try:
            controls = driver.find_elements(By.XPATH, expand_xpath)
            for control in controls[:5]:
                if control.is_displayed() and control.is_enabled():
                    try:
                        driver.execute_script("arguments[0].click();", control)
                        LOGGER.info("Expanded navigation tree")
                        time.sleep(1.5)
                        return
                    except WebDriverException:
                        continue
        except WebDriverException:
            LOGGER.debug("Failed to expand navigation")

    def _capture_rendered_html(self, driver) -> str:
        try:
            return driver.execute_script("return document.documentElement.outerHTML;")
        except WebDriverException:
            return driver.page_source

    def _collect_toc_entries_from_dom(self, driver, css_selectors: list[str]) -> list[dict]:
        script = """
        const selectors = arguments[0];
        const nodeDepth = (anchor, stopNode) => {
            let depth = 1;
            let current = anchor.parentElement;
            while (current && current !== stopNode) {
                if (["DL", "UL", "OL"].includes(current.tagName)) depth += 1;
                current = current.parentElement;
            }
            return depth;
        };

        const resolveBaseUrl = (node) => {
            let current = node;
            while (current) {
                if (current.getAttribute) {
                    const baseUrl = current.getAttribute("data-base-url");
                    if (baseUrl) return baseUrl;
                }
                current = current.parentElement;
            }
            return document.baseURI;
        };

        const collectFromRoots = (roots, results, seen, startOrder) => {
            let order = startOrder;
            for (const root of roots) {
                const anchors = root.querySelectorAll("a[href]");
                for (const anchor of anchors) {
                    const href = anchor.getAttribute("href");
                    if (!href || href.startsWith("javascript:")) continue;
                    const baseUrl = resolveBaseUrl(anchor);
                    const key = baseUrl + "::" + href + "::" + (anchor.textContent || "");
                    if (seen.has(key)) continue;
                    seen.add(key);
                    results.push({
                        href,
                        text: (anchor.textContent || "").trim().replace(/\\s+/g, " "),
                        level: nodeDepth(anchor, root),
                        order,
                        base_url: baseUrl,
                    });
                    order += 1;
                }
            }
            return order;
        };

        const containers = [];
        for (const selector of selectors) {
            containers.push(...document.querySelectorAll(selector));
        }

        const results = [];
        const seen = new Set();
        let order = collectFromRoots(containers.length ? containers : [document.body], results, seen, 0);
        if (containers.length && results.length < 5) {
            collectFromRoots([document.body], results, seen, order);
        }

        return results;
        """
        raw_entries = driver.execute_script(script, css_selectors) or []
        entries: list[dict] = []
        seen_urls: set[str] = set()
        for entry in raw_entries:
            absolute_url = absolutize(entry.get("base_url") or driver.current_url, entry["href"])
            if absolute_url in seen_urls:
                continue
            seen_urls.add(absolute_url)
            entries.append(
                {
                    "url": absolute_url,
                    "text": entry.get("text", ""),
                    "level": entry.get("level", 1),
                    "order": entry.get("order", 0),
                }
            )
        return entries

    def close(self) -> None:
        if self._driver:
            try:
                self._driver.quit()
            except WebDriverException:
                pass
            self._driver = None

    def _restart_driver(self) -> None:
        LOGGER.info("Restarting browser session")
        self.close()

    def __del__(self):
        self.close()
