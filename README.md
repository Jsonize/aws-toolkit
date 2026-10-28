# aws-toolkit

A collection of small scripts for day-to-day AWS housekeeping.

## Contents

| Script | Purpose |
| --- | --- |
| [`cost-explorer/tag-resources.py`](cost-explorer/tag-resources.py) | Bulk-tag DynamoDB tables, ECS task definitions or S3 buckets with their own name, so costs can be broken down per resource in Cost Explorer. |

## Requirements

- Python 3.8+
- [`boto3`](https://pypi.org/project/boto3/)
- AWS credentials configured the usual way (environment variables, `~/.aws/credentials`, SSO profile, instance role, ...)

```sh
pip install boto3
```

## cost-explorer/tag-resources.py

Applies a tag to every resource of a given service. The tag **key** is whatever you pass with `--tag`; the tag **value** is the resource's name. Combined with a [cost allocation tag](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/cost-alloc-tags.html), this lets you group and filter costs per table, task definition or bucket in Cost Explorer.

### Usage

```sh
python3 cost-explorer/tag-resources.py --service <ecs|dynamodb|s3> --tag <TagKey> [--region <region>]
```

| Option | Required | Description |
| --- | --- | --- |
| `--service` | yes | `dynamodb`, `ecs` or `s3` |
| `--tag` | yes | Tag key to apply. The value is set to the resource name. |
| `--region` | for `dynamodb` and `ecs` | AWS region to process. For `s3` it is optional: if given, only buckets in that region are tagged; if omitted, buckets in all regions are tagged. |

Use `AWS_PROFILE=...` to select a credentials profile.

### Examples

```sh
# Tag all DynamoDB tables in eu-central-1 with ResourceName=<table name>
python3 cost-explorer/tag-resources.py --service dynamodb --region eu-central-1 --tag ResourceName

# Tag all active ECS task definitions in eu-central-1
python3 cost-explorer/tag-resources.py --service ecs --region eu-central-1 --tag ResourceName

# Tag every S3 bucket in the account, regardless of region
AWS_PROFILE=prod python3 cost-explorer/tag-resources.py --service s3 --tag ResourceName
```

### What gets tagged

| Service | Resources | Tag value |
| --- | --- | --- |
| `dynamodb` | All tables in the region | Table name |
| `ecs` | All **active** task definition revisions in the region | `family:revision` (e.g. `my-service:42`) |
| `s3` | All buckets in the account (optionally filtered by region) | Bucket name |

Notes:

- Existing tags are preserved. If a resource already has a tag with the same key, its value is overwritten.
- For S3, the script reads the bucket's current tag set and writes it back with the new tag added, since `PutBucketTagging` replaces the whole set.
- The script reports each resource as it goes and prints a success/error summary at the end. A failure on one resource does not stop the run.

### Required IAM permissions

| Service | Actions |
| --- | --- |
| `dynamodb` | `sts:GetCallerIdentity`, `dynamodb:ListTables`, `dynamodb:TagResource`, `tag:TagResources` |
| `ecs` | `ecs:ListTaskDefinitions`, `ecs:TagResource`, `tag:TagResources` |
| `s3` | `s3:ListAllMyBuckets`, `s3:GetBucketLocation`, `s3:GetBucketTagging`, `s3:PutBucketTagging` |

### Using the tag in Cost Explorer

1. Run the script for each service/region you care about.
2. In the AWS Billing console, go to **Cost allocation tags** and activate the tag key you used.
3. Wait for the tag to appear in Cost Explorer (this can take up to 24 hours), then group or filter by it.
