---
name: web-browser
description: Extract web content, scrape data, capture screenshots, and interact with web pages using Playwright. Use when the user asks to browse a website, extract web data, scrape content, take screenshots, fill forms, click elements, or automate web interactions.
license: Apache-2.0
user_invocable: true
model: inherit
color: blue
---

# Web Browser Tool (Playwright)

Extract content from web pages, capture screenshots, fill forms, and automate web interactions using Playwright. Use via `run_command` to execute Python scripts in the output folder.

## Prerequisites

Install Playwright before first use:

```bash
pip install playwright
playwright install chromium
```

## When to Use This Skill

Use when the task requires:
- Browsing or fetching content from a website
- Extracting text, tables, or specific page elements
- Screenshots or PDFs of web pages
- Form submission or page interaction
- JavaScript-rendered or dynamic content

## Workflow

1. Write a Python script to the output folder with `write_output`
2. Run it with `run_command` (cwd is the output folder)
3. Read results from stdout or files written to output

## Extract Page Content

```python
from playwright.sync_api import sync_playwright
import json

def extract_content(url: str) -> dict:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        result = {
            "title": page.title(),
            "url": page.url,
            "text": page.inner_text("body"),
        }
        browser.close()
        return result

print(json.dumps(extract_content("https://example.com")))
```

## Extract Specific Elements

```python
from playwright.sync_api import sync_playwright
import json

def extract_elements(url: str, selector: str) -> list:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        page.wait_for_selector(selector, timeout=10000)
        elements = page.locator(selector).all_inner_texts()
        browser.close()
        return elements

print(json.dumps(extract_elements("https://example.com", "h1, h2, h3")))
```

## Extract Table Data

```python
from playwright.sync_api import sync_playwright
import json

def extract_table(url: str, table_selector: str = "table") -> list:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        page.wait_for_selector(table_selector)
        headers = page.locator(table_selector + " th").all_inner_texts()
        rows = []
        for row in page.locator(table_selector + " tbody tr").all():
            cells = row.locator("td").all_inner_texts()
            if headers and len(cells) == len(headers):
                rows.append(dict(zip(headers, cells)))
            else:
                rows.append(cells)
        browser.close()
        return rows

print(json.dumps(extract_table("https://example.com/data", "table.data-table")))
```

## Capture Screenshot

```python
from playwright.sync_api import sync_playwright

def capture_screenshot(url: str, output_path: str, full_page: bool = True):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.screenshot(path=output_path, full_page=full_page)
        browser.close()

capture_screenshot("https://example.com", "screenshot.png")
```

## Fill Form and Submit

```python
from playwright.sync_api import sync_playwright
import json

def fill_and_submit(url: str, form_data: dict, submit_button: str) -> dict:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        for selector, value in form_data.items():
            page.fill(selector, value)
        page.click(submit_button)
        page.wait_for_load_state("networkidle")
        result = {"url": page.url, "title": page.title()}
        browser.close()
        return result

form_data = {
    "input[name='username']": "user@example.com",
    "input[name='password']": "password123",
}
print(json.dumps(fill_and_submit("https://example.com/login", form_data, "button[type='submit']")))
```

## Selector Reference

```python
page.locator("#element-id")
page.locator(".class-name")
page.locator("[data-testid='value']")
page.get_by_text("Click me")
page.get_by_role("button", name="Submit")
page.get_by_label("Email address")
```

## Error Handling

```python
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        content = page.inner_text("body")
        browser.close()
except Exception as exc:
    print(json.dumps({"success": False, "error": str(exc)}))
```

## Notes

- `run_command` executes in the output folder; write scripts there first
- Increase timeout for slow pages: `page.goto(url, timeout=60000)`
- Respect robots.txt and rate limits
- Playwright is not pre-installed; run `pip install playwright && playwright install chromium` first
