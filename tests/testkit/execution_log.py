import json


def jsonl(events: list[dict]) -> str:
    return "\n".join(json.dumps(event) for event in events)
