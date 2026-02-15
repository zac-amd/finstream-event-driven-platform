# =============================================================================
# FinStream - AWS Infrastructure (Terraform)
# =============================================================================
# Demonstrates: ECS Fargate, MSK, RDS, ElastiCache, ALB, CloudWatch
# =============================================================================

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

variable "environment" { default = "dev" }
variable "region" { default = "us-east-1" }
variable "project_name" { default = "finstream" }

provider "aws" { region = var.region }

# -----------------------------------------------------------------------------
# VPC & Networking
# -----------------------------------------------------------------------------
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${var.project_name}-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["${var.region}a", "${var.region}b", "${var.region}c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = var.environment == "dev"

  tags = { Project = var.project_name, Environment = var.environment }
}

# -----------------------------------------------------------------------------
# ECS Cluster
# -----------------------------------------------------------------------------
resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"
  setting { name = "containerInsights", value = "enabled" }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]
  default_capacity_provider_strategy { capacity_provider = "FARGATE_SPOT", weight = 1 }
}

# -----------------------------------------------------------------------------
# Application Load Balancer
# -----------------------------------------------------------------------------
resource "aws_lb" "main" {
  name               = "${var.project_name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = module.vpc.public_subnets
}

resource "aws_lb_target_group" "api" {
  name        = "${var.project_name}-api-tg"
  port        = 8080
  protocol    = "HTTP"
  vpc_id      = module.vpc.vpc_id
  target_type = "ip"
  health_check { path = "/health", healthy_threshold = 2, interval = 30 }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"
  default_action { type = "forward", target_group_arn = aws_lb_target_group.api.arn }
}

# -----------------------------------------------------------------------------
# Security Groups
# -----------------------------------------------------------------------------
resource "aws_security_group" "alb" {
  name   = "${var.project_name}-alb-sg"
  vpc_id = module.vpc.vpc_id
  ingress { from_port = 80, to_port = 80, protocol = "tcp", cidr_blocks = ["0.0.0.0/0"] }
  ingress { from_port = 443, to_port = 443, protocol = "tcp", cidr_blocks = ["0.0.0.0/0"] }
  egress { from_port = 0, to_port = 0, protocol = "-1", cidr_blocks = ["0.0.0.0/0"] }
}

resource "aws_security_group" "ecs" {
  name   = "${var.project_name}-ecs-sg"
  vpc_id = module.vpc.vpc_id
  ingress { from_port = 0, to_port = 65535, protocol = "tcp", security_groups = [aws_security_group.alb.id] }
  egress { from_port = 0, to_port = 0, protocol = "-1", cidr_blocks = ["0.0.0.0/0"] }
}

# -----------------------------------------------------------------------------
# ECR Repositories
# -----------------------------------------------------------------------------
locals {
  services = ["market-simulator", "stream-processor", "alert-service", "api-gateway"]
}

resource "aws_ecr_repository" "services" {
  for_each             = toset(local.services)
  name                 = "${var.project_name}/${each.key}"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

# -----------------------------------------------------------------------------
# RDS (TimescaleDB)
# -----------------------------------------------------------------------------
resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnet"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_db_instance" "timescale" {
  identifier           = "${var.project_name}-timescale"
  engine               = "postgres"
  engine_version       = "15"
  instance_class       = var.environment == "dev" ? "db.t3.micro" : "db.r6g.large"
  allocated_storage    = 20
  db_name              = "finstream"
  username             = "finstream"
  password             = "CHANGE_ME_IN_SECRETS"
  db_subnet_group_name = aws_db_subnet_group.main.name
  skip_final_snapshot  = var.environment == "dev"
}

# -----------------------------------------------------------------------------
# ElastiCache (Redis)
# -----------------------------------------------------------------------------
resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project_name}-redis-subnet"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id         = "${var.project_name}-redis"
  engine             = "redis"
  node_type          = var.environment == "dev" ? "cache.t3.micro" : "cache.r6g.large"
  num_cache_nodes    = 1
  port               = 6379
  subnet_group_name  = aws_elasticache_subnet_group.main.name
}

# -----------------------------------------------------------------------------
# MSK (Kafka)
# -----------------------------------------------------------------------------
resource "aws_msk_cluster" "main" {
  cluster_name           = "${var.project_name}-kafka"
  kafka_version          = "3.5.1"
  number_of_broker_nodes = var.environment == "dev" ? 2 : 3

  broker_node_group_info {
    instance_type   = var.environment == "dev" ? "kafka.t3.small" : "kafka.m5.large"
    client_subnets  = slice(module.vpc.private_subnets, 0, var.environment == "dev" ? 2 : 3)
    security_groups = [aws_security_group.ecs.id]
    storage_info { ebs_storage_info { volume_size = 100 } }
  }
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------
output "alb_dns" { value = aws_lb.main.dns_name }
output "ecr_repos" { value = { for k, v in aws_ecr_repository.services : k => v.repository_url } }
output "msk_bootstrap" { value = aws_msk_cluster.main.bootstrap_brokers_tls }
output "rds_endpoint" { value = aws_db_instance.timescale.endpoint }
output "redis_endpoint" { value = aws_elasticache_cluster.redis.cache_nodes[0].address }
