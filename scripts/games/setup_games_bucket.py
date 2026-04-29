import boto3
import json
import os

AWS_CREDS = '/opt/openclaw/.aws/.aws/credentials'
AWS_REGION = 'us-east-1'
BUCKET = 'agent-cody-games-ACCOUNT_ID'
ACCOUNT = os.environ.get('AWS_ACCOUNT_ID', 'ACCOUNT_ID')

os.environ['AWS_SHARED_CREDENTIALS_FILE'] = AWS_CREDS

session = boto3.Session(profile_name=os.environ.get('AWS_PROFILE', 'default'))
s3 = session.client('s3', region_name=AWS_REGION)

# Create bucket
try:
    s3.create_bucket(Bucket=BUCKET)
    print(f"Created bucket: {BUCKET}")
except s3.exceptions.BucketAlreadyOwnedByYou:
    print(f"Bucket already exists: {BUCKET}")
except Exception as e:
    print(f"Create error: {e}")

# Disable block public access
s3.put_public_access_block(
    Bucket=BUCKET,
    PublicAccessBlockConfiguration={
        'BlockPublicAcls': False,
        'IgnorePublicAcls': False,
        'BlockPublicPolicy': False,
        'RestrictPublicBuckets': False
    }
)
print("Public access unblocked")

# Set bucket policy for public read
policy = {
    "Version": "2012-10-17",
    "Statement": [{
        "Sid": "PublicReadGetObject",
        "Effect": "Allow",
        "Principal": "*",
        "Action": "s3:GetObject",
        "Resource": f"arn:aws:s3:::{BUCKET}/*"
    }]
}
s3.put_bucket_policy(Bucket=BUCKET, Policy=json.dumps(policy))
print("Public read policy applied")

# Enable static website hosting
s3.put_bucket_website(
    Bucket=BUCKET,
    WebsiteConfiguration={
        'IndexDocument': {'Suffix': 'index.html'},
        'ErrorDocument': {'Key': 'error.html'}
    }
)
print("Static website hosting enabled")
print(f"\nGames URL base: http://{BUCKET}.s3-website-{AWS_REGION}.amazonaws.com/")
