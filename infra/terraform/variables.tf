variable "region" {
  type    = string
  default = "ap-south-1"
}
variable "project" {
  type    = string
  default = "schoolroom"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,24}$", var.project))
    error_message = "Use 3–25 lowercase letters, digits or hyphens, starting with a letter."
  }
}
variable "admin_cidr" {
  type        = string
  description = "Your public IPv4 address in /32 notation, used for HTTPS access."
  validation {
    condition     = can(cidrnetmask(var.admin_cidr)) && endswith(var.admin_cidr, "/32")
    error_message = "Provide one IPv4 address with /32."
  }
}
variable "instance_type" {
  type    = string
  default = "t3.medium"
}
variable "k3s_version" {
  type        = string
  description = "Explicit K3s release to install, such as v1.34.1+k3s1. Verify support before applying."
  validation {
    condition     = can(regex("^v[0-9]+[.][0-9]+[.][0-9]+[+]k3s[0-9]+$", var.k3s_version))
    error_message = "Provide a pinned K3s version."
  }
}
