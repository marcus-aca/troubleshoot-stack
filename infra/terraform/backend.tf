terraform {
  backend "s3" {
    bucket         = "troubleshooter-terraform-state"
    key            = "terraform.tfstate"
    region         = "us-west-2"
    dynamodb_table = "troubleshooter-terraform-locks"
    encrypt        = true
  }
}
