locals {
  project_tag = local.name
}

resource "aws_s3_bucket" "evidence" {
  bucket = "${local.name}-evidence-${random_id.evidence_suffix.hex}"
  tags   = local.tags
}

resource "aws_s3_bucket_versioning" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  versioning_configuration { status = "Enabled" }
}

resource "random_id" "evidence_suffix" {
  byte_length = 4
}
