import boto3, os, mimetypes

os.environ['AWS_SHARED_CREDENTIALS_FILE'] = '/opt/openclaw/.aws/.aws/credentials'
os.environ['AWS_CONFIG_FILE'] = '/opt/openclaw/.aws/.aws/config'
session = boto3.Session(profile_name=os.environ.get('AWS_PROFILE', 'default'))
s3 = session.client('s3', region_name='us-east-1')

BUCKET = 'agent-cody-games-ACCOUNT_ID'
GAMES_DIR = '/opt/openclaw/.openclaw/workspace/games'

for fname in os.listdir(GAMES_DIR):
    if not fname.endswith('.html') and not fname.endswith('.js'):
        continue
    fpath = os.path.join(GAMES_DIR, fname)
    ct, _ = mimetypes.guess_type(fname)
    s3.put_object(
        Bucket=BUCKET,
        Key=fname,
        Body=open(fpath, 'rb').read(),
        ContentType=ct or 'text/html',
        CacheControl='max-age=60'
    )
    print(f"Uploaded: {fname}")

print("Done.")
