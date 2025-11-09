terraform {
  required_providers {
    yandex = {
      source = "yandex-cloud/yandex"
      version = "~> 0.112"
    }
  }
  required_version = ">= 0.13"
}

provider "yandex" {
  zone = "ru-central1-a"
}

# Create serverless function with full configuration
resource "yandex_function" "telegram_bot" {
  name               = "telegram-bot"
  description        = "Telegram bot function with Vision OCR (vvot00)"
  folder_id          = var.folder_id
  runtime            = "python311"
  entrypoint         = "main.handler"
  memory             = 512  # Increased for image processing
  execution_timeout  = 10   # Increased timeout for image processing
  service_account_id = null

  environment = {
    TELEGRAM_BOT_TOKEN = var.telegram_bot_token
    YC_API_KEY         = var.yc_api_key
    FOLDER_ID          = var.folder_id
    MODEL_URI          = "gpt://${var.folder_id}/yandexgpt-lite"
    VISION_API_KEY     = var.yc_api_key  # New environment variable
  }

  content {
    zip_filename = var.function_zip_path
  }

  # user_hash is optional but can be used to force updates
  user_hash = filesha256(var.function_zip_path)
}

# Grant public invoke rights (needed for API Gateway and Telegram)
resource "yandex_function_iam_binding" "invoker_public" {
  function_id = yandex_function.telegram_bot.id
  role        = "serverless.functions.invoker"
  members     = ["system:allUsers"]
}

resource "yandex_api_gateway" "tg_gateway" {
  name        = "telegram-bot-gateway"
  description = "API Gateway для приема webhook от Telegram"
  folder_id   = var.folder_id

  spec = <<EOF
openapi: 3.0.0
info:
  title: Telegram Bot Webhook
  version: 1.0.0
paths:
  /webhook/${var.webhook_path_suffix}:
    post:
      x-yc-apigateway-integration:
        type: cloud_functions
        function_id: ${yandex_function.telegram_bot.id}
      responses:
        '200':
          description: OK
EOF
}

output "webhook_url" {
  value = "https://${yandex_api_gateway.tg_gateway.domain}/webhook/${var.webhook_path_suffix}"
}