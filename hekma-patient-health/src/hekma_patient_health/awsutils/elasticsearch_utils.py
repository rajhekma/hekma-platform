from elasticsearch import Elasticsearch, RequestsHttpConnection, helpers
from requests_aws4auth import AWS4Auth
import boto3
import os
import json

def get_redis_credentials():
    return {
        "host": os.getenv("REDIS_HOST", "localhost"),
        "port": os.getenv("REDIS_PORT", "6379"),
        "password": os.getenv("REDIS_PASSWORD", ""),
    }


def set_aws_environment(secret_name, region_name):
    response = get_secret(secret_name, region_name)
    result=json.loads(response["SecretString"])
    os.environ['access_key'] = result['access_key']
    os.environ['secret_key'] = result['secret_key']



def get_secret(secret_name, region_name="us-east-1"):
    client = boto3.client("secretsmanager", region_name=region_name)
    return client.get_secret_value(SecretId=secret_name)


if __name__ == '__main__':
    secret_name = "redis_nonprod"
    secret_region = "us-west-1"
    #set_aws_environment(secret_name, secret_region)
    #set_redis_credentials()

class ElasticSearchConnection:
    def __init__(self):

        password = ()
        if 'env' in os.environ:
            environment = os.environ['env']
        else:
            environment = 'nonprod'
        if environment == "prod":
            print("Production")
            host = os.getenv("ES_HOST_PROD")
            region = os.getenv("ES_REGION_PROD", "us-east-1")
            self.index_prefix = os.getenv("ES_INDEX_PREFIX_PROD", "")
            password = None
            if os.getenv("ES_USER_PROD"):
                 password = (os.getenv("ES_USER_PROD"), os.getenv("ES_PASSWORD_PROD"))
        else:
            print("Non Production")
            host = os.getenv("ES_HOST_DEV", "search-dev-hekma-lxpg5an3me7sbg5khpoeaw3a4m.us-east-1.es.amazonaws.com")
            region = os.getenv("ES_REGION_DEV", "us-east-1")
            self.index_prefix = os.getenv("ES_INDEX_PREFIX_DEV", "restored_")
            es_user = os.getenv("ES_USER_DEV")
            es_password = os.getenv("ES_PASSWORD_DEV")
            password = (es_user, es_password) if es_user and es_password else None
        service = 'es'
        #awsauth = AWS4Auth(os.environ['access_key'], os.environ['secret_key'], region, service)

        self.es = Elasticsearch(
            hosts=[{'host': host, 'port': 443}],
            http_auth=password,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            timeout=30
        )

    def get_check(self):
        print("success")
        document = {"title": "Moneyball", "director": "Bennett Miller", "year": "2011"}
        self.es.index(index="movies", doc_type="_doc", id="5", body=document)
        print(self.es.get(index="movies", doc_type="_doc", id="5"))

    def perform_bulk(self, index, doc):
        return helpers.bulk(self.es, doc, index=self.index_prefix + index)

    def search(self, index, param:dict = None, body:dict = None):
        return self.es.search(body=body, index=self.index_prefix + index, params=param)

    def count(self, index, param:dict = None, body:dict = None):
        return self.es.count(body=body, index=self.index_prefix + index, params=param)

    def put_json(self, index, doc, doc_id):
        return self.es.index(index=self.index_prefix + index,  id=doc_id, body=doc)


if __name__ == '__main__':

    host = 'http://74.208.223.174/'

    # Connect to the Elasticsearch server
    es = Elasticsearch("http://74.208.223.174:9200")

    # Check connection
    if es.ping():
        print("Connected to Elasticsearch")
    else:
        print("Could not connect to Elasticsearch")

    response = es.search(
        index='restored_medication_order',
        body={
            "query": {
                "match_all": {}
            }
        }
    )
    print(response)

    quit()