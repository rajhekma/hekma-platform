import boto3
import os
import json


def get_s3_connection():
    return boto3.resource('s3',
                          region_name='us-west-1')


def delete_files_in_folder_s3(bucket_name, folder):
    s3 = get_s3_connection()
    bucket = s3.Bucket(bucket_name)
    for obj in bucket.objects.filter(Prefix=folder):
        s3.Object(bucket.name, obj.key).delete()


def list_files_s3(bucket_name, prefix):
    s3 = get_s3_connection()
    bucket = s3.Bucket(bucket_name)
    #objs = list(bucket.objects.all())
    objs = list(bucket.objects.filter(Prefix=prefix))
    return objs
    #for i in range(0, len(objs)):
    #    print(objs[i].key)


def write_file_s3(bucket_name, filepath, json_dict):
    s3 = get_s3_connection()
    s3.Object(bucket_name, filepath).put(Body=json_dict)


def read_file_s3(bucket_name, filepath):
    s3 = get_s3_connection()
    return s3.Object(bucket_name, filepath).get()['Body'].read().decode('utf-8')
