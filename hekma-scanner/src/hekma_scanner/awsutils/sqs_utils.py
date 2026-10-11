import boto3
import os
import json


def get_sqs_connection():
    return boto3.resource('sqs',
                          region_name=os.getenv("AWS_REGION", "us-west-1"))


def send_sqs_message(queue_name, content):
    sqs = get_sqs_connection()

    # Get the queue
    queue = sqs.get_queue_by_name(QueueName=queue_name)

    if "CMS" in queue_name:
        message = content
    else:
        message = "{\"email\":\"" +content+ "\"}"


    # Create a new message
    response = queue.send_message(MessageBody=str(message))

    # The response is NOT a resource, but gives you a message ID and MD5
    print(response.get('MessageId'))
    print(response.get('MD5OfMessageBody'))


