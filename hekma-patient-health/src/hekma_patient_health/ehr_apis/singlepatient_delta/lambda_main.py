from awsutils.sqs_utils import *


def resource_type_handler(event, context):
    print(event)
    hekma_mail = event['params']['querystring']['hekmaMail']
    send_sqs_message("oneUpHealthConsentQueue", hekma_mail)
    return "success"
