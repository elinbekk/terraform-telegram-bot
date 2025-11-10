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

provider "yandex" {
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
  description        = "Telegram bot function with Vision OCR (vvot00)"
  folder_id          = var.folder_id
  runtime            = "python311"
  entrypoint         = "main.handler"
  memory             = 1024  # Increased for image processing
  execution_timeout  = 60   # Increased timeout for image processing
  service_account_id = null

  # environment = {
  #   TELEGRAM_BOT_TOKEN = var.telegram_bot_token
  #   YC_API_KEY         = var.yc_api_key
  #   FOLDER_ID          = var.folder_id
  #   MODEL_URI          = "gpt://${var.folder_id}/yandexgpt-lite"
  #   VISION_API_KEY     = var.yc_api_key  # New environment variable
  # }
  environment = {
    TELEGRAM_BOT_TOKEN = var.telegram_bot_token
    YC_API_KEY         = var.yc_api_key
    FOLDER_ID          = var.folder_id
    MODEL_URI          = "gpt://${var.folder_id}/yandexgpt-lite"
    VISION_API_KEY     = var.yc_api_key

    # Storage credentials + object info for the function to read instructions
    STORAGE_ACCESS_KEY = var.s3_access_key
    STORAGE_SECRET_KEY = var.s3_secret_key
    STORAGE_ENDPOINT   = var.s3_endpoint
    STORAGE_BUCKET     = yandex_storage_bucket.bot_docs.bucket
    STORAGE_OBJECT_KEY = var.instruction_object_key
  }

  content {
    zip_filename = data.archive_file.function_zip.output_path
  }

  user_hash = filesha256(data.archive_file.function_zip.output_path)
  # depends_on = [data.archive_file.function_zip]
  depends_on = [data.archive_file.function_zip, yandex_storage_object.instruction_file]

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


resource "yandex_storage_bucket" "bot_docs" {
  bucket     = var.instruction_bucket_name
  acl        = "private" # prefer private; we'll fetch with credentials
  folder_id  = var.folder_id
  # optionally website / other settings
}

resource "yandex_storage_object" "instruction_file" {
  bucket      = yandex_storage_bucket.bot_docs.bucket
  key         = var.instruction_object_key
  source      = "${path.module}/yandexgpt_instructions.json"
  content_type = "application/json"
  acl         = "private"
}
