resource "aws_security_group" "voice_sg" {
  name        = "${var.project_name}-sg"
  description = "Security group for Voice Medical API"

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  ingress {
    description = "FastAPI"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Ollama"
    from_port   = 11434
    to_port     = 11434
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-sg"
  }
}

data "aws_ami" "ubuntu_2204" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

locals {
  selected_ami_id = var.ami_id != "" ? var.ami_id : data.aws_ami.ubuntu_2204.id
}

resource "aws_instance" "voice_api" {
  ami                    = local.selected_ami_id
  instance_type          = var.instance_type
  key_name               = var.key_name
  vpc_security_group_ids = [aws_security_group.voice_sg.id]

  user_data = <<-EOT
    #!/bin/bash
    set -eux
    apt-get update -y
    apt-get install -y docker.io docker-compose-plugin git
    systemctl enable docker
    systemctl start docker
  EOT

  tags = {
    Name = "${var.project_name}-ec2"
  }
}
