import os
import random
from logging import Logger

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_bolt.context.ack import Ack
from slack_bolt.context.respond import Respond
from slack_sdk import WebClient

from slackbot.constants import KEEP_IT_IN_THE_HERD, Classifier
from slackbot.utilities import channel_message, message_is_classifier, only_channel, thread_message

# This sample slack application uses SocketMode
# For the companion getting started setup guide,
# see: https://docs.slack.dev/tools/bolt-python/getting-started

# logging.basicConfig(level=logging.DEBUG)
# Initializes your app with your bot token
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))


@app.command("/website")
def website(ack: Ack, respond: Respond, logger: Logger) -> None:
    ack()
    respond("https://cowgilltrailcollective.com/")
    logger.info("Website URL posted")


@app.event(
    "message",
    [
        channel_message,
        only_channel(KEEP_IT_IN_THE_HERD),
    ],
)
def give_away_message(event: dict, client: WebClient, ack: Ack) -> None:
    ack()
    if not message_is_classifier(event, Classifier.GIVEAWAY):
        return

    channel_id = event["channel"]
    user = event["user"]

    client.chat_postEphemeral(
        channel=channel_id,
        user=event["user"],
        text=f"<@{user}> looks like you are giving something away! It is recommended to allow people at least 24 hours "
        "to respond to the thread before determining who to select for the giveaway. If you want, just tag me in the "
        "thread when you are ready to select someone and I will choose someone randomly from the people who responded "
        "in the thread!",
    )


@app.event("app_mention", [only_channel(KEEP_IT_IN_THE_HERD), thread_message])
def keep_it_in_the_herd_select(event: dict, client: WebClient, logger: Logger) -> None:
    channel_id = event["channel"]
    thread_ts = event["thread_ts"]
    original_user = event["parent_user_id"]

    # Get all messages in the thread
    result = client.conversations_replies(channel=channel_id, ts=thread_ts)

    if event["user"] != original_user:
        client.chat_postEphemeral(
            channel=channel_id,
            user=event["user"],
            thread_ts=thread_ts,
            text="Only the person who originally posted can select a user!",
        )
        return

    # Extract unique users, excluding bots and the original user
    users = {
        message["user"]
        for message in result["messages"]
        if (not message.get("bot_id")) and (message.get("user") != original_user)
    }

    if not users:
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="No other users found in this thread!",
        )
        return

    # Select a random user
    selected_user = random.choice(list(users))
    client.chat_postMessage(
        channel=channel_id,
        thread_ts=thread_ts,
        text=f"<@{selected_user}> you have been selected!",
    )
    logger.info(f"Selected user: {selected_user}")


# Start your app
if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
