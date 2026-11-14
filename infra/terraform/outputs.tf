output "instance_id" {
  value = aws_instance.node.id
}
output "public_ip" {
  value = aws_instance.node.public_ip
}
output "backup_bucket" {
  value = aws_s3_bucket.backup.id
}
output "connect_command" {
  value = "aws ssm start-session --target ${aws_instance.node.id} --region ${var.region}"
}
