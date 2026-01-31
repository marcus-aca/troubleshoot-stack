# cloudfront

Creates a CloudFront distribution backed by a private S3 bucket using Origin Access Control (OAC).
Optionally creates a Route 53 alias record for a custom domain.

## Inputs
- `enabled`: Whether to create the distribution.
- `bucket_name`: S3 bucket name.
- `bucket_arn`: S3 bucket ARN.
- `bucket_regional_domain_name`: S3 bucket regional domain name.
- `custom_domain_name`: Custom domain (optional).
- `certificate_arn`: ACM cert ARN in us-east-1 (optional, required for custom domain).
- `hosted_zone_id`: Route 53 hosted zone ID for alias record (optional).
- `default_root_object`: Default root object.
- `price_class`: CloudFront price class.
- `minimum_protocol_version`: Minimum TLS version.

## Outputs
- `distribution_id`
- `distribution_arn`
- `distribution_domain_name`
- `oac_id`
