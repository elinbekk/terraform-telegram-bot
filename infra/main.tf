terraform {
  required_providers {
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
    yandex = {
      source = "yandex-cloud/yandex"
      version = "~> 0.112"
    }
    http = {
      source  = "hashicorp/http"
      version = "~> 3.4"
    }
  }
  required_version = ">= 0.13"
}
@@ -12,6 +20,16 @@ provider "yandex" {
  zone = "ru-central1-a"
}

#######################################################
# Automatically create ZIP archive from bot directory
#######################################################
data "archive_file" "function_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../bot"
  output_path = "${path.module}/../function.zip"
  excludes    = ["__pycache__/*", "*.pyc", ".DS_Store", "package/*"]
}

# Create serverless function with full configuration
resource "yandex_function" "telegram_bot" {
  name               = "telegram-bot"
@@ -32,11 +50,11 @@ resource "yandex_function" "telegram_bot" {
  }

  content {
    zip_filename = data.archive_file.function_zip.output_path
  }

  user_hash = filesha256(data.archive_file.function_zip.output_path)
  depends_on = [data.archive_file.function_zip]
}

# Grant public invoke rights (needed for API Gateway and Telegram)
@@ -70,4 +88,24 @@ EOF

output "webhook_url" {
  value = "https://${yandex_api_gateway.tg_gateway.domain}/webhook/${var.webhook_path_suffix}"
}

############################################
# Register Telegram Webhook (on apply)
############################################
data "http" "telegram_webhook_register" {
  depends_on = [yandex_api_gateway.tg_gateway, yandex_function.telegram_bot]

  url    = "https://api.telegram.org/bot${var.telegram_bot_token}/setWebhook"
  method = "POST"

  request_body = jsonencode({
    url = "https://${yandex_api_gateway.tg_gateway.domain}/webhook/${var.webhook_path_suffix}"
  })

  # Optional header, Telegram accepts plain form but JSON works too
  request_headers = {
    "Content-Type" = "application/json"
  }
}
