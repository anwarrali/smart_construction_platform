"""Deterministic, conservative evidence acceptance; no semantic verifier model.

Only extractive claims are accepted. Paraphrases, arithmetic, causal conclusions
and outside knowledge abstain until a separately evaluated verifier exists.
This establishes support by a source, not truth or engineering approval.
"""
import json
import re
import unicodedata


def normalized(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split()).strip(' .,:;!?"“”\'\n')


def supported_sentences(content):
    # Require the whole sentence, preserving negation and applicability. A
    # substring such as "approved" in "not approved" is not supported.
    return {normalized(part) for part in re.split(r"(?<!\d)[.!?](?!\d)\s+|\n", content)} | {normalized(content)}


def conflicting_values(chunks):
    templates = {}
    for item in chunks:
        for sentence in re.split(r"[.;\n]", item.chunk.content):
            value = normalized(sentence)
            numbers = tuple(re.findall(r"\d+(?:[.,]\d+)?", value))
            if not numbers:
                continue
            template = re.sub(r"\d+(?:[.,]\d+)?", "#", value)
            # Same wording/applicability, different numbers: cannot choose one.
            if template in templates and templates[template] != numbers:
                return True
            templates[template] = numbers
    return False


def validate(reply, chunks):
    if conflicting_values(chunks):
        return "CONFLICTING_EVIDENCE", []
    if reply.startswith(("{", "[")):
        try:
            payload = json.loads(reply)
            if set(payload) != {"claims"} or not payload["claims"]:
                return "INVALID_OUTPUT", []
            fragments = []
            for claim in payload["claims"]:
                if set(claim) != {"quote", "citations"} or not isinstance(claim["quote"], str):
                    return "INVALID_OUTPUT", []
                if not claim["citations"] or any(type(i) is not int for i in claim["citations"]):
                    return "INVALID_OUTPUT", []
                fragments.append(claim["quote"] + " " + " ".join(f"[{i}]" for i in claim["citations"]))
            reply = "\n".join(fragments)
        except (ValueError, TypeError, KeyError, AttributeError):
            return "INVALID_OUTPUT", []
    used = set()
    end = 0
    for match in re.finditer(r"(.*?)(\[\d+\](?:\s*\[\d+\])*)", reply, flags=re.S):
        claim = normalized(match[1])
        ids = [int(i) for i in re.findall(r"\[(\d+)\]", match[2])]
        if not claim or any(i < 1 or i > len(chunks) for i in ids):
            return "UNSUPPORTED", []
        if not any(claim in supported_sentences(chunks[i - 1].chunk.content) for i in ids):
            return "UNSUPPORTED", []
        # Every attached citation must support the text, not just one of them.
        if any(claim not in supported_sentences(chunks[i - 1].chunk.content) for i in ids):
            return "UNSUPPORTED", []
        used.update(ids)
        end = match.end()
    if not used or normalized(reply[end:]):
        return "UNSUPPORTED", []
    return "SUPPORTED_EXCERPTS", sorted(used)
