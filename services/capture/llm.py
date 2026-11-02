"""Local LLM (Ollama) used only to read and structure captured page text.

Runs entirely on this machine (default model `llama3`, configurable with
OLLAMA_MODEL). No API key; nothing leaves the machine. All output is passed
through `grounding.ground` before it is stored.
"""
import json
import logging

import httpx

log = logging.getLogger(__name__)

FIELDS_SPEC = """Return JSON. Copy text EXACTLY as it appears in the page text; never paraphrase, translate or guess.
Use null for anything not present. Fields:
- advertiser_name: the advertiser / page / company running the ad
- author: who paid for the ad, only if the text says so (e.g. "Paid for by X")
- headline: the ad's headline or title
- ad_copy: the main ad body text
- description: secondary ad text (link description), if any
- call_to_action: button text such as "Learn more"
- creative_type: ad format exactly as written (e.g. "Video ad"), if any
- ad_id: the ad's ID number exactly as written, if any
- landing_page_url: a destination URL copied from a [[LINK:...]] marker, if any
- first_date_text / last_date_text: the start / end dates exactly as written on the page"""

SEGMENT_PROMPT = 'Below is the text of ONE advertisement card from a public ad library.\n' + FIELDS_SPEC + \
    '\nReturn a single JSON object with exactly those keys.\n\nPAGE TEXT:\n'
PAGE_PROMPT = 'Below is the text of a public ad-library page that may list several advertisements.\n' + FIELDS_SPEC + \
    '\nReturn {"ads": [ ...one object per advertisement... ]}. Return {"ads": []} if there are none.\n\nPAGE TEXT:\n'


class LLMUnavailable(Exception):
    pass


class OllamaExtractor:
    def __init__(self, base_url, model, timeout=180, client_factory=None):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout
        self.client_factory = client_factory or (lambda: httpx.AsyncClient(timeout=timeout, follow_redirects=False))

    async def status(self):
        try:
            async with self.client_factory() as client:
                res = await client.get(self.base_url + '/api/tags', timeout=3)
                res.raise_for_status()
                names = [m.get('name', '') for m in res.json().get('models', [])]
        except (httpx.HTTPError, ValueError):
            return {'available': False, 'model': self.model,
                    'detail': 'Ollama is not running. Install it from https://ollama.com, then run `ollama pull '
                              f'{self.model}`.'}
        have = any(n == self.model or n.split(':')[0] == self.model for n in names)
        return {'available': have, 'model': self.model,
                'detail': None if have else f'Model not installed. Run `ollama pull {self.model}`.'}

    async def _ask(self, prompt):
        body = {'model': self.model, 'stream': False, 'format': 'json',
                'options': {'temperature': 0, 'num_ctx': 4096},
                'messages': [{'role': 'user', 'content': prompt}]}
        try:
            async with self.client_factory() as client:
                res = await client.post(self.base_url + '/api/chat', json=body)
                res.raise_for_status()
                content = res.json()['message']['content']
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise LLMUnavailable(f'Local LLM request failed ({type(exc).__name__}).') from exc
        try:
            return json.loads(content)
        except ValueError:
            log.warning('LLM returned non-JSON output')
            return {}

    async def extract_segment(self, segment_text):
        data = await self._ask(SEGMENT_PROMPT + str(segment_text)[:3000])
        return data if isinstance(data, dict) else {}

    async def extract_page(self, page_text, chunk_chars=5000):
        """For pages without recognizable ad anchors: chunk the text and collect every proposed ad."""
        found = []
        for chunk in _chunks(page_text, chunk_chars):
            data = await self._ask(PAGE_PROMPT + chunk)
            ads = data.get('ads') if isinstance(data, dict) else None
            found.extend(({'candidate': a, 'source': chunk} for a in ads or [] if isinstance(a, dict)))
        return found


def _chunks(text, size):
    lines, chunk = str(text).splitlines(), []
    for line in lines:
        if chunk and sum(len(x) + 1 for x in chunk) + len(line) > size:
            yield '\n'.join(chunk)
            chunk = []
        chunk.append(line[:size])
    if chunk:
        yield '\n'.join(chunk)
