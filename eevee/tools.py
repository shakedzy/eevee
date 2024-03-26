import re
import inspect
import requests
from tqdm import tqdm
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from .color_logger import get_logger
from .settings import Settings
from .package_types import ToolsDefType


def handle_tool_error(e: Exception) -> None:
    get_logger().error(f'ERROR [{e.__class__.__name__} in {inspect.stack()[1].function}]: {str(e)}', color='red')


def web_search(query: str, max_results: int = 10) -> str:
    """
    Searched the web for the provided query, and returns the title, URL and description of the results.
    Search results are separated by: =====

    Example of two search results:

    Title: Welcome to My Site
    URL: http://www.mysite.xyz
    Description: This is my private website, see my stuff here
    =====
    Title: Grapes Online
    URL: http://www.grapes.com
    Description: This is the number one site for grapes fans and lovers
    """
    if max_results < 1: max_results = 1
    elif max_results > 10: max_results = 10

    ddgs = DDGS()
    outputs = list()
        
    results = ddgs.text(query, max_results=max_results)

    try:
        for result in tqdm(results):
            url = result['href']
            if url is None:
                continue
            body = result['body']
            title = result['title'] or ''
            outputs.append(f"Title: {title}\nURL: {url}\nDescription: {body}\n")
    
    except Exception as e:
        handle_tool_error(e)
        return f"Error while searching the web: {e}"

    if outputs:
        return '\n=====\n'.join(outputs)
    else:
        return "No results"


def surf(url: str) -> str:
    """
    Surfs to the provided URL and returns a simple version of the page text. Images and styling are excluded.
    """
    try:
        headers = {'User-Agent': Settings().web.user_agent}
        response = requests.get(url, timeout=Settings().web.surf_timeout_seconds, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            text = soup.get_text()

            # Clean whitespaces
            text = re.sub(pattern=r'[ \t]+', repl=' ', string=text)  # Replace multiple spaces and tabs with a single space
            text = re.sub(pattern=r'\n{3,}', repl='\n\n', string=text)  # Replace more than two newlines with two newlines
            text = text.strip()

            return text 
        else:
            raise RuntimeError(f"ERROR: Failed to retrieve the webpage. Status code: {response.status_code}")
    except Exception as e:
        handle_tool_error(e)
        return f"ERROR: {e}"



tools_params_definitions: ToolsDefType = {
    web_search: [("query", {"type": "string", "description": "The query to search on the web"}, True),
                 ("max_results", {"type": "number", "description": "Maximal number of results to retrieve. Must be between 1 and 10, default is 10."}, False)],
    surf: [("url", {"type": "string", "description": "The URL of the page to scrape"}, True)],
}