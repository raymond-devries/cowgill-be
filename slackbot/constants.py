from enum import Enum

from pydantic import BaseModel

KEEP_IT_IN_THE_HERD = "C0A2GBX3SKW"


class Classifier(Enum):
    GIVEAWAY = "An item that is being given away for free. Ensure the item is free, not being sold."
    UNKNOWN = "Classification is not defined."


class MessageClassified(BaseModel):
    classified: Classifier
