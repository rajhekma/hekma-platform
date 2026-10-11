import boto3

region = 'us-east-1'
instance_id = 'i-04b37abf040b795a1'
ec2 = boto3.client('ec2', region_name=region)


def process(action):
    if action == 'start':
        ec2.start_instances(InstanceIds=[instance_id])
        return "Instance started!"
    elif action == 'stop':
        ec2.stop_instances(InstanceIds=[instance_id])
        return "Instance stopped!"
    else:
        response = ec2.describe_instance_status(InstanceIds=[instance_id], IncludeAllInstances=True)
        return response['InstanceStatuses'][0]['InstanceState']['Name']


def resource_type_handler(event, context):
    event = event['params']['querystring']
    action = "State"
    if 'action' in event:
        action = event['action']
    return {"Instance State":process(action)}