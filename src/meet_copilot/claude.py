import asyncio
import json
import logging
import re
import threading

log = logging.getLogger(__name__)


class EventLoopThread:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True, name="claude-loop").start()

    def run(self, coroutine, timeout=None):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout)


class ClaudeChat:
    def __init__(self, runner, model, system_prompt, max_turns=40):
        self.runner = runner
        self.model = model
        self.system_prompt = system_prompt
        self.max_turns = max_turns
        self.client = None
        self.turns = 0
        self.lock = threading.Lock()

    def ask(self, prompt, timeout=90):
        with self.lock:
            return self.runner.run(self._ask(prompt), timeout)

    def warm(self, timeout=60):
        with self.lock:
            if self.client is None:
                self.runner.run(self._connect(), timeout)

    def reset(self, system_prompt=None):
        with self.lock:
            if system_prompt is not None:
                self.system_prompt = system_prompt
            self.runner.run(self._close())

    def close(self):
        self.reset()

    async def _ask(self, prompt):
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

        if self.client is None or self.turns >= self.max_turns:
            await self._close()
            await self._connect()
        await self.client.query(prompt)
        parts = []
        async for message in self.client.receive_response():
            if isinstance(message, AssistantMessage):
                parts.extend(block.text for block in message.content if isinstance(block, TextBlock))
            elif isinstance(message, ResultMessage):
                break
        self.turns += 1
        return "".join(parts).strip()

    async def _connect(self):
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

        options = ClaudeAgentOptions(
            model=self.model,
            system_prompt=self.system_prompt,
            tools=[],
            allowed_tools=[],
            setting_sources=[],
            strict_mcp_config=True,
            mcp_servers={},
            plugins=[],
        )
        self.client = ClaudeSDKClient(options=options)
        await self.client.connect()
        self.turns = 0

    async def _close(self):
        if self.client is not None:
            try:
                await self.client.disconnect()
            except Exception as error:
                log.warning("closing claude client: %s", error)
        self.client = None


def extract_json(text):
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    pairs = sorted((("{", "}"), ("[", "]")), key=lambda pair: _position(candidate, pair[0]))
    for opener, closer in pairs:
        start, end = candidate.find(opener), candidate.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"respuesta sin JSON: {text[:200]}")


def _position(text, token):
    index = text.find(token)
    return index if index != -1 else len(text)
