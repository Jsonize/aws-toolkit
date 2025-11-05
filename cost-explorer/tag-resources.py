#!/usr/bin/env python3
import argparse
import sys
from typing import List

import boto3
from botocore.exceptions import ClientError


def _account_id():
    return boto3.client("sts").get_caller_identity()["Account"]


def tag_dynamodb(region: str, tag_key: str) -> None:
    dynamodb = boto3.client("dynamodb", region_name=region)
    tagging = boto3.client("resourcegroupstaggingapi", region_name=region)
    acct = _account_id()

    paginator = dynamodb.get_paginator("list_tables")
    tagged_ok, tagged_err = 0, 0

    print(f"[DynamoDB] Region={region} TagKey={tag_key}")
    for page in paginator.paginate():
        for table_name in page.get("TableNames", []):
            arn = f"arn:aws:dynamodb:{region}:{acct}:table/{table_name}"
            try:
                tagging.tag_resources(
                    ResourceARNList=[arn],
                    Tags={tag_key: table_name},
                )
                print(f"  ✓ Tagged table {table_name}")
                tagged_ok += 1
            except Exception as e:
                print(f"  ✗ Error tagging table {table_name}: {e}")
                tagged_err += 1

    print(f"[DynamoDB] Done. Success={tagged_ok} Errors={tagged_err}")


def tag_ecs_task_definitions(region: str, tag_key: str) -> None:
    ecs = boto3.client("ecs", region_name=region)
    tagging = boto3.client("resourcegroupstaggingapi", region_name=region)

    paginator = ecs.get_paginator("list_task_definitions")
    tagged_ok, tagged_err = 0, 0

    print(f"[ECS] Region={region} TagKey={tag_key}")
    for page in paginator.paginate():
        for td_arn in page.get("taskDefinitionArns", []):
            td_name = td_arn.split("/")[-1]
            try:
                tagging.tag_resources(
                    ResourceARNList=[td_arn],
                    Tags={tag_key: td_name},
                )
                print(f"  ✓ Tagged task definition {td_name}")
                tagged_ok += 1
            except Exception as e:
                print(f"  ✗ Error tagging task definition {td_name}: {e}")
                tagged_err += 1

    print(f"[ECS] Done. Success={tagged_ok} Errors={tagged_err}")


def _bucket_region(s3_client, bucket: str) -> str:
    try:
        resp = s3_client.get_bucket_location(Bucket=bucket)
        loc = resp.get("LocationConstraint")
        return "us-east-1" if loc is None else "eu-west-1" if loc == "EU" else loc
    except ClientError as e:
        raise RuntimeError(f"Could not get region for bucket {bucket}: {e}")


def _get_bucket_tags(s3_client, bucket: str) -> List[dict]:
    try:
        resp = s3_client.get_bucket_tagging(Bucket=bucket)
        return resp.get("TagSet", [])
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in ("NoSuchTagSet", "NoSuchTagSetError", "NoSuchTagSetException"):
            return []
        raise


def _upsert_tag(tagset: List[dict], key: str, value: str) -> List[dict]:
    for t in tagset:
        if t.get("Key") == key:
            t["Value"] = value
            break
    else:
        tagset.append({"Key": key, "Value": value})
    return tagset


def tag_s3_buckets(region: str, tag_key: str) -> None:
    s3 = boto3.client("s3")
    buckets = s3.list_buckets().get("Buckets", [])

    if region:
        print(f"[S3] Tagging only buckets in region {region}")
    else:
        print("[S3] Tagging buckets in ALL regions")

    tagged_ok, tagged_err, skipped = 0, 0, 0

    for b in buckets:
        name = b["Name"]
        try:
            bucket_region = _bucket_region(s3, name)
        except Exception as e:
            print(f"  ✗ {name}: failed to determine region: {e}")
            tagged_err += 1
            continue

        if region and bucket_region != region:
            skipped += 1
            continue

        try:
            current = _get_bucket_tags(s3, name)
            new_tags = _upsert_tag(current, tag_key, name)
            s3.put_bucket_tagging(Bucket=name, Tagging={"TagSet": new_tags})
            print(f"  ✓ Tagged bucket {name} ({bucket_region})")
            tagged_ok += 1
        except ClientError as e:
            print(f"  ✗ Error tagging bucket {name}: {e}")
            tagged_err += 1

    print(f"[S3] Done. Success={tagged_ok} Skipped={skipped} Errors={tagged_err}")


def main():
    parser = argparse.ArgumentParser(
        description="Tag AWS resources by service with a specified tag key (value = resource name)."
    )
    parser.add_argument(
        "--region",
        help="AWS region (e.g. eu-west-1). Optional for S3; required for ECS and DynamoDB.",
    )
    parser.add_argument(
        "--service",
        required=True,
        choices=["ecs", "dynamodb", "s3"],
        help="Service to tag (ecs | dynamodb | s3)",
    )
    parser.add_argument(
        "--tag",
        required=True,
        help="Tag key to apply (value will be the resource name)",
    )

    args = parser.parse_args()

    if args.service in ("ecs", "dynamodb") and not args.region:
        print(f"--region is required for {args.service}")
        sys.exit(2)

    if args.service == "dynamodb":
        tag_dynamodb(args.region, args.tag)
    elif args.service == "ecs":
        tag_ecs_task_definitions(args.region, args.tag)
    elif args.service == "s3":
        tag_s3_buckets(args.region, args.tag)
    else:
        print(f"Unsupported service: {args.service}")
        sys.exit(2)


if __name__ == "__main__":
    main()
