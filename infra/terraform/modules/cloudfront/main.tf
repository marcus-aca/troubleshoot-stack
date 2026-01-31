locals {
  aliases = var.custom_domain_name != null && var.custom_domain_name != "" ? [var.custom_domain_name] : []
  create_alias_record = (
    var.custom_domain_name != null &&
    var.custom_domain_name != "" &&
    var.hosted_zone_id != null &&
    var.hosted_zone_id != ""
  )
}

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

resource "aws_cloudfront_origin_access_control" "this" {
  name                              = "${var.bucket_name}-oac"
  description                       = "OAC for ${var.bucket_name}"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "this" {
  count = var.enabled ? 1 : 0

  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = var.default_root_object
  price_class         = var.price_class

  origin {
    domain_name              = var.bucket_regional_domain_name
    origin_id                = "s3-frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.this.id
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD", "OPTIONS"]
    target_origin_id = "s3-frontend"

    viewer_protocol_policy = "redirect-to-https"
    cache_policy_id        = data.aws_cloudfront_cache_policy.caching_optimized.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = var.certificate_arn == null
    acm_certificate_arn            = var.certificate_arn
    ssl_support_method             = var.certificate_arn == null ? null : "sni-only"
    minimum_protocol_version       = var.minimum_protocol_version
  }

  aliases = local.aliases
}

data "aws_iam_policy_document" "bucket_access" {
  count = var.enabled ? 1 : 0

  statement {
    sid     = "AllowCloudFrontRead"
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = [
      "${var.bucket_arn}/*"
    ]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.this[0].arn]
    }
  }
}

resource "aws_s3_bucket_policy" "this" {
  count  = var.enabled ? 1 : 0
  bucket = var.bucket_name
  policy = data.aws_iam_policy_document.bucket_access[0].json
}

resource "aws_route53_record" "custom_domain" {
  count   = var.enabled && local.create_alias_record ? 1 : 0
  zone_id = var.hosted_zone_id
  name    = var.custom_domain_name
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.this[0].domain_name
    zone_id                = aws_cloudfront_distribution.this[0].hosted_zone_id
    evaluate_target_health = false
  }
}
