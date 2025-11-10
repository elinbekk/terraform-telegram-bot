variable "cloud_id" {
  description = "Yandex Cloud ID"
  type        = string
}

variable "folder_id" {
  description = "Yandex Folder ID"
  type        = string
}

variable "yc_api_key" {
  description = "Yandex Cloud API Key for YandexGPT"
  type        = string
  sensitive   = true
}

variable "vision_api_key" {
  description = "Yandex Vision API Key for OCR"
  type        = string
  sensitive   = true
}

variable "telegram_bot_token" {
  description = "Telegram Bot Token"
  type        = string
  sensitive   = true
}

variable "webhook_path_suffix" {
  description = "Секретная часть пути для webhook (для простоты можно взять пару символов из токена)"
  type        = string
  default     = "hook"
}

variable "function_zip_path" {
  description = "Путь до zip архива функции"
  type        = string
  default     = "../function.zip"
}

variable "s3_access_key" {
  description = "Access key for Object Storage (S3)"
  type        = string
  sensitive   = true
}

variable "s3_secret_key" {
  description = "Secret key for Object Storage (S3)"
  type        = string
  sensitive   = true
}

variable "s3_endpoint" {
  description = "S3 endpoint (default: https://storage.yandexcloud.net)"
  type        = string
  default     = "https://storage.yandexcloud.net"
}

variable "instruction_object_key" {
  description = "Key (path) for the instructions file in the bucket"
  type        = string
  default     = "yandexgpt_instructions.json"
}

variable "instruction_bucket_name" {
  description = "Name of bucket to store instructions"
  type        = string
  default     = "" # set in terraform.tfvars
}
