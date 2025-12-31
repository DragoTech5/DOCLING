"""
Web Scraper - Fetch and extract content from websites
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


@dataclass
class ScrapedPage:
    """Result of scraping a web page."""
    url: str
    title: str
    content: str
    text: str
    word_count: int
    links: list[str]
    images: list[str]
    metadata: dict[str, Any]


@dataclass
class ScrapeResult:
    """Result of a scraping operation."""
    success: bool
    page: ScrapedPage | None
    error: str | None


# Default headers for requests
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


def clean_text(text: str) -> str:
    """Clean and normalize text content."""
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove leading/trailing whitespace per line
    lines = [line.strip() for line in text.split('\n')]
    # Remove empty lines
    lines = [line for line in lines if line]
    return '\n'.join(lines)


def extract_text_from_html(html: str, base_url: str) -> ScrapedPage:
    """Extract clean text and metadata from HTML."""
    soup = BeautifulSoup(html, 'lxml')

    # Remove script and style elements
    for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript']):
        element.decompose()

    # Get title
    title = ''
    if soup.title:
        title = soup.title.string or ''
    elif soup.find('h1'):
        title = soup.find('h1').get_text() or ''

    # Get meta description
    meta_desc = ''
    meta_tag = soup.find('meta', attrs={'name': 'description'})
    if meta_tag:
        meta_desc = meta_tag.get('content', '')

    # Get main content
    main_content = soup.find('main') or soup.find('article') or soup.find('body')
    if main_content:
        text = main_content.get_text(separator='\n')
    else:
        text = soup.get_text(separator='\n')

    text = clean_text(text)

    # Extract links
    links = []
    for link in soup.find_all('a', href=True):
        href = link['href']
        absolute_url = urljoin(base_url, href)
        if absolute_url.startswith(('http://', 'https://')):
            links.append(absolute_url)

    # Extract images
    images = []
    for img in soup.find_all('img', src=True):
        src = img['src']
        absolute_url = urljoin(base_url, src)
        if absolute_url.startswith(('http://', 'https://')):
            images.append(absolute_url)

    # Build metadata
    metadata = {
        'description': meta_desc,
    }

    # Get Open Graph metadata
    for og_tag in soup.find_all('meta', property=lambda x: x and x.startswith('og:')):
        prop = og_tag.get('property', '').replace('og:', '')
        content = og_tag.get('content', '')
        metadata[f'og_{prop}'] = content

    return ScrapedPage(
        url=base_url,
        title=title.strip(),
        content=html,
        text=text,
        word_count=len(text.split()),
        links=list(set(links))[:100],  # Limit links
        images=list(set(images))[:50],  # Limit images
        metadata=metadata,
    )


async def fetch_url(url: str, timeout: int = 30) -> tuple[str | None, str | None]:
    """Fetch content from a URL."""
    try:
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=timeout,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

            # Check content type
            content_type = response.headers.get('content-type', '')
            if 'text/html' not in content_type and 'application/xhtml' not in content_type:
                return None, f"Unsupported content type: {content_type}"

            return response.text, None

    except httpx.HTTPStatusError as e:
        return None, f"HTTP error {e.response.status_code}"
    except httpx.RequestError as e:
        return None, f"Request error: {str(e)}"
    except Exception as e:
        return None, f"Error: {str(e)}"


async def scrape_url(url: str, timeout: int = 30) -> ScrapeResult:
    """Scrape a single URL."""
    html, error = await fetch_url(url, timeout)

    if error:
        return ScrapeResult(success=False, page=None, error=error)

    try:
        page = extract_text_from_html(html, url)
        return ScrapeResult(success=True, page=page, error=None)
    except Exception as e:
        return ScrapeResult(success=False, page=None, error=str(e))


async def scrape_urls(urls: list[str], timeout: int = 30) -> list[ScrapeResult]:
    """Scrape multiple URLs concurrently."""
    tasks = [scrape_url(url, timeout) for url in urls]
    return await asyncio.gather(*tasks)


def is_same_domain(url1: str, url2: str) -> bool:
    """Check if two URLs are from the same domain."""
    domain1 = urlparse(url1).netloc
    domain2 = urlparse(url2).netloc
    return domain1 == domain2


async def crawl_website(
    start_url: str,
    max_pages: int = 10,
    same_domain_only: bool = True,
    timeout: int = 30,
) -> list[ScrapeResult]:
    """
    Crawl a website starting from a URL.

    Args:
        start_url: Starting URL to crawl
        max_pages: Maximum number of pages to crawl
        same_domain_only: Only crawl pages from the same domain
        timeout: Request timeout in seconds

    Returns:
        List of ScrapeResult for each crawled page
    """
    visited = set()
    to_visit = [start_url]
    results = []

    while to_visit and len(visited) < max_pages:
        url = to_visit.pop(0)

        if url in visited:
            continue

        visited.add(url)

        result = await scrape_url(url, timeout)
        results.append(result)

        if result.success and result.page:
            # Add new links to visit
            for link in result.page.links:
                if link not in visited and link not in to_visit:
                    if not same_domain_only or is_same_domain(start_url, link):
                        to_visit.append(link)

    return results


def convert_html_to_markdown(html: str) -> str:
    """Convert HTML to a simple markdown representation."""
    soup = BeautifulSoup(html, 'lxml')

    # Remove unwanted elements
    for element in soup(['script', 'style', 'nav', 'footer', 'aside', 'noscript']):
        element.decompose()

    result_parts = []

    def process_element(element, depth=0):
        if element.name is None:
            text = element.string
            if text and text.strip():
                result_parts.append(text.strip())
            return

        if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            level = int(element.name[1])
            text = element.get_text().strip()
            if text:
                result_parts.append(f"\n{'#' * level} {text}\n")

        elif element.name == 'p':
            text = element.get_text().strip()
            if text:
                result_parts.append(f"\n{text}\n")

        elif element.name in ['ul', 'ol']:
            for i, li in enumerate(element.find_all('li', recursive=False)):
                prefix = f"{i + 1}." if element.name == 'ol' else "-"
                text = li.get_text().strip()
                if text:
                    result_parts.append(f"{prefix} {text}")

        elif element.name == 'a':
            text = element.get_text().strip()
            href = element.get('href', '')
            if text and href:
                result_parts.append(f"[{text}]({href})")

        elif element.name == 'code':
            text = element.get_text()
            if '\n' in text:
                result_parts.append(f"```\n{text}\n```")
            else:
                result_parts.append(f"`{text}`")

        elif element.name == 'pre':
            text = element.get_text()
            result_parts.append(f"```\n{text}\n```")

        elif element.name == 'blockquote':
            text = element.get_text().strip()
            if text:
                lines = text.split('\n')
                quoted = '\n'.join(f"> {line}" for line in lines)
                result_parts.append(quoted)

        elif element.name in ['strong', 'b']:
            text = element.get_text().strip()
            if text:
                result_parts.append(f"**{text}**")

        elif element.name in ['em', 'i']:
            text = element.get_text().strip()
            if text:
                result_parts.append(f"*{text}*")

        else:
            for child in element.children:
                process_element(child, depth + 1)

    main = soup.find('main') or soup.find('article') or soup.find('body')
    if main:
        for child in main.children:
            process_element(child)

    # Clean up result
    result = '\n'.join(result_parts)
    result = re.sub(r'\n{3,}', '\n\n', result)  # Max 2 newlines
    return result.strip()
