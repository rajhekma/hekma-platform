import json
import os
from stream_chat import StreamChat
import traceback
from pathlib import Path


def get_getstream_secrets(env: str = "dev"):
    global client

    # Try environment-specific variables first, then fallback to generic
    api_key =  os.getenv("GETSTREAM_API_KEY")
    api_secret =  os.getenv("GETSTREAM_API_SECRET")

    if not api_key or not api_secret:
        raise ValueError(f"GetStream credentials for environment '{env}' not found in environment variables.")

    credentials = {
        'api_key': api_key,
        'api_secret': api_secret
    }

    client = StreamChat(
        api_key=api_key,
        api_secret=api_secret
    )

    return credentials, client



def get_token(user_id: str, client, credentials):
    """
    Generate a Stream Chat access token for a user.

    Args:
        user_id (str): The ID of the user.
        env (str): Environment name, defaults to 'dev'.

    Returns:
        dict: Contains 'user_id' and 'token'.

    Raises:
        ValueError: If user_id is empty or invalid.
        Exception: If token generation fails.
    """
    if not user_id:
        raise ValueError("user_id is required")

    try:

        # Generate token
        token = client.create_token(user_id)
        return {
            'user_id': user_id,
            'token': token,
            'api_key': credentials['api_key']
        }
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"Failed to generate token: {str(e)}")


def get_user_channels(user_id: str, client):
    """
    Fetch all channels where the given user is a member.
    """
    try:
        # Filter channels where user_id is a member
        filter_conditions = {
            "type": "messaging",
            "members": {"$in": [user_id]}  # Use the provided user_id
        }

        channels = client.query_channels(filter_conditions=filter_conditions)
        # Format response for easier consumption
        result = []
        for ch in channels["channels"]:
            channel_data = ch.get("channel", {})
            state = ch.get("state", {})

            result.append({
                "channel_id": channel_data.get("id"),
                "name": channel_data.get("name")
            })
        return {"channels": result}
    except Exception as e:
        traceback.print_exc()
        return {
            'statusCode': 400,
            'body': json.dumps({'error': f"Failed to get user channels: {str(e)}"})
        }


def create_or_update_user(user : dict, client):
    client.update_user(user)


def create_or_get_channel(users, channel_id, client):
    """
    If channel exists, return existing details.
    If not, create it after ensuring all users exist.
    """
    try:
        channel = client.channel("messaging", channel_id)
        try:
            channel_state = channel.query()  # Check if channel exists
            return {
                "status": "existing",
                "channel_id": channel.id,
                "members": [m["user"]["id"] for m in channel_state["members"]],
                "created_at": channel_state["channel"]["created_at"]
            }
        except Exception:
            # Channel doesn't exist, create it
            member_ids = [u["id"] for u in users]
            channel = client.channel("messaging", channel_id, {"members": member_ids})
            channel.create(user_id=member_ids[0])  # Explicitly create the channel
            return {
                "status": "created",
                "channel_id": channel.id,
                "members": member_ids
            }

    except Exception as e:
        traceback.print_exc()
        return {
            'statusCode': 400,
            'body': json.dumps({'error': f"Error: {str(e)}"})
        }




def post_resource_type_handler(event, context):
    event = event['body-json']
    print(event)
    if 'env' not in event:
        env = "dev"
    else:
        env = event['env']
    credentials, client=get_getstream_secrets(env)
    if "type" not in event or not (str(event['type']) == "token" or str(event['type']) == "user_channels"  or str(event['type']) == "create_or_get_channel"):
        return {
            'statusCode': 400,
            'body': json.dumps({'error': "Invalid or missing 'type'. Must be 'token' or 'channel'"})
        }
    else:
        type=event['type']

    if type == "token" and "user" not in event:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': "Invalid or missing user for token"})
        }
    elif type == "token":

        user = event['user']
        create_or_update_user(user, client)
        return get_token(user['id'], client, credentials)

    if type == "user_channels" and "user" not in event:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': "Invalid or missing user for channel"})
        }
    elif type == "user_channels":
        user = event['user']
        create_or_update_user(user, client)

        return get_user_channels(user['id'], client)

    if type == "create_or_get_channel" and "users" not in event:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': "Invalid or missing users for token"})
        }
    elif type == "create_or_get_channel":
        users = event['users']
        client.update_users(users)
        return create_or_get_channel(users, event['channel_id'], client)



if __name__ == '__main__':
    credentials=get_getstream_secrets()
    user = {
        "id": "123",
        "name": "Test user"
    }
    create_or_update_user(user)
    print(get_token(user["id"]))
    print(get_user_channels(user["id"]))
    users = [user,{
        "id": "124",
        "name": "Test user"
    }]
    client.update_users(users)
    print(create_or_get_channel(users, "check-it"))
    #print(get_channel("123", credentials, created_by_id="123"))