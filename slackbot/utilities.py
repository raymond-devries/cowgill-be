import os
from functools import cache
from typing import Callable

import llm
from llm import Model

from slackbot.constants import Classifier, MessageClassified


@cache
def model() -> Model:
    model = llm.get_model("openrouter/qwen/qwen3-8b")
    model.key = os.environ["OPEN_ROUTER_KEY"]
    return model


def classify(message: str) -> Classifier:
    print(f"Classifying message: {message}")
    response = model().prompt(
        message,
        system=f"Classify this slack message. Classification options: ({[x.value for x in Classifier]}).",
        schema=MessageClassified,
    )
    classification = MessageClassified.model_validate_json(response.text()).classified
    print(classification)
    return classification


def message_is_classifier(event: dict, classifier: Classifier) -> bool:
    return classify(event["text"]) == classifier


def only_channel(channel_id: str) -> Callable[[dict], bool]:
    return lambda event: event["channel"] == channel_id


def channel_message(event: dict) -> bool:
    return event.get("thread_ts") is None


def thread_message(event: dict) -> bool:
    return event.get("thread_ts") is not None
