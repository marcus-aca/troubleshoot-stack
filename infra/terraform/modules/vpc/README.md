# vpc module

Creates a VPC with public and private subnets across multiple AZs.

## Inputs
- `cidr`
- `az_count`
- `public_subnet_cidrs`
- `private_subnet_cidrs`

## Outputs
- `vpc_id`
- `subnet_ids_public`
- `subnet_ids_private`

## Notes
This module is currently a scaffold; wire resources in later steps.
