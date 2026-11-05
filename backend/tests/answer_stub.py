"""Offline provider that returns actual context excerpts, never canned facts."""
import re
from types import SimpleNamespace


class ExtractiveAnswerClient:
    def __init__(self):
        self.chat = self
        self.completions = self

    def create(self, *, messages, **kwargs):
        content = messages[-1]["content"]
        passages = re.findall(r"\[(\d+)\] Source:[^\n]*\n(.*?)(?=\n\n\[\d+\] Source:|\n\nQuestion:)",
                              content, flags=re.S)
        answer = "\n".join(f"{quote.strip()} [{index}]" for index, quote in passages)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=answer))])
