variable "cidr" {
  type        = string
  description = "CIDR block for the VPC."
}

variable "az_count" {
  type        = number
  description = "Number of availability zones to use."
}

variable "public_subnet_cidrs" {
  type        = list(string)
  description = "CIDR blocks for public subnets."
}

variable "private_subnet_cidrs" {
  type        = list(string)
  description = "CIDR blocks for private subnets."
}
