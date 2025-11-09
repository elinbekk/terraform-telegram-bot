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