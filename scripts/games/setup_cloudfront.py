import boto3, os, json

os.environ['AWS_SHARED_CREDENTIALS_FILE'] = '/opt/openclaw/.aws/.aws/credentials'
session = boto3.Session(profile_name=os.environ.get('AWS_PROFILE', 'default'))
s3 = session.client('s3', region_name='us-east-1')
cf = session.client('cloudfront', region_name='us-east-1')

BUCKET = 'agent-cody-games-ACCOUNT_ID'
REGION = 'us-east-1'

# Upload index.html
s3.put_object(
    Bucket=BUCKET,
    Key='index.html',
    Body=open('/opt/openclaw/.openclaw/workspace/games/index.html', 'rb').read(),
    ContentType='text/html',
    CacheControl='max-age=60'
)
print("Uploaded index.html")

# Create CloudFront distribution
origin_domain = f"{BUCKET}.s3-website-{REGION}.amazonaws.com"

resp = cf.create_distribution(
    DistributionConfig={
        'CallerReference': 'agent-cody-games-v1',
        'Comment': 'Agent Cody Games',
        'DefaultCacheBehavior': {
            'TargetOriginId': 'S3-games',
            'ViewerProtocolPolicy': 'redirect-to-https',
            'CachePolicyId': '658327ea-f89d-4fab-a63d-7e88639e58f6',  # CachingOptimized
            'AllowedMethods': {
                'Quantity': 2,
                'Items': ['GET', 'HEAD'],
                'CachedMethods': {'Quantity': 2, 'Items': ['GET', 'HEAD']}
            },
            'Compress': True,
        },
        'Origins': {
            'Quantity': 1,
            'Items': [{
                'Id': 'S3-games',
                'DomainName': origin_domain,
                'CustomOriginConfig': {
                    'HTTPPort': 80,
                    'HTTPSPort': 443,
                    'OriginProtocolPolicy': 'http-only',
                }
            }]
        },
        'Enabled': True,
        'DefaultRootObject': 'index.html',
        'PriceClass': 'PriceClass_100',
        'HttpVersion': 'http2',
        'IsIPV6Enabled': True,
    }
)

dist = resp['Distribution']
domain = dist['DomainName']
dist_id = dist['Id']
print(f"\nCloudFront distribution created!")
print(f"ID: {dist_id}")
print(f"Domain: https://{domain}")
print(f"\nGames will be available at:")
print(f"  https://{domain}/snake.html")
print(f"  https://{domain}/index.html")
print(f"\nNote: Takes ~15 min to fully deploy globally.")
