#!/bin/sh
# Starts SeaweedFS with an S3 gateway. The S3 credentials file is generated from
# environment variables at start-up, so no secret is stored in the repository or image.
set -eu

: "${S3_ACCESS_KEY:?S3_ACCESS_KEY is required}"
: "${S3_SECRET_KEY:?S3_SECRET_KEY is required}"

umask 077
cat > /tmp/s3.json <<JSON
{"identities":[{"name":"workshoppro","credentials":[{"accessKey":"${S3_ACCESS_KEY}","secretKey":"${S3_SECRET_KEY}"}],"actions":["Admin","Read","Write","List","Tagging"]}]}
JSON

exec weed server -dir=/data -s3 -s3.port=8333 -s3.config=/tmp/s3.json
