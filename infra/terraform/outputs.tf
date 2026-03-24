output "instance_public_ip" {
  value       = aws_instance.voice_api.public_ip
  description = "Public IP of EC2 instance"
}

output "instance_id" {
  value       = aws_instance.voice_api.id
  description = "EC2 instance id"
}

output "selected_ami_id" {
  value       = aws_instance.voice_api.ami
  description = "AMI id used by the EC2 instance"
}
