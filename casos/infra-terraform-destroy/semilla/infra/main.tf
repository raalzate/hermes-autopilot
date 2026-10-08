resource "aws_s3_bucket" "app_assets" {
  bucket = "acme-app-assets"
}

resource "aws_s3_bucket" "logs_2023" {
  bucket = "acme-logs-2023"
}

resource "aws_s3_bucket" "logs_2026" {
  bucket = "acme-logs-2026"
}
