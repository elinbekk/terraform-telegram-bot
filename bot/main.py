import os
import json
import requests
import base64
from typing import Optional, List, Dict, Any

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
YC_API_KEY = os.getenv("YC_API_KEY")
FOLDER_ID = os.getenv("FOLDER_ID")
MODEL_URI = os.getenv("MODEL_URI", f"gpt://{FOLDER_ID}/yandexgpt-lite")
VISION_API_KEY = os.getenv("VISION_API_KEY")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
YANDEX_GPT_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
YANDEX_VISION_URL = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"

# Global commands responses
START_RESPONSE = "Я помогу ответить на экзаменационный вопрос по «Операционным системам».\nПрисылайте вопрос — фото или текстом."
HELP_RESPONSE = START_RESPONSE
NON_QUESTION_RESPONSE = "Я не могу понять вопрос.\nПришлите экзаменационный вопрос по «Операционным системам» — фото или текстом."
GENERATION_ERROR_RESPONSE = "Я не смог подготовить ответ на экзаменационный вопрос."
MULTIPLE_PHOTOS_RESPONSE = "Я могу обработать только одну фотографию."
PHOTO_PROCESSING_ERROR_RESPONSE = "Я не могу обработать эту фотографию."
UNSUPPORTED_MESSAGE_RESPONSE = "Я могу обработать только текстовое сообщение или фотографию."

def get_telegram_file_url(file_id: str) -> str:
    """Get direct URL for Telegram file"""
    response = requests.get(f"{TG_API}/getFile?file_id={file_id}", timeout=10)
    response.raise_for_status()
    file_path = response.json()["result"]["file_path"]
    return f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"

def download_photo_from_telegram(file_id: str) -> bytes:
    """Download photo from Telegram and return as bytes"""
    file_url = get_telegram_file_url(file_id)
    response = requests.get(file_url, timeout=30)
    response.raise_for_status()
    return response.content

def process_photo_with_vision(image_data: bytes) -> str:
    """Extract text from photo using Yandex Vision OCR"""
    if not VISION_API_KEY:
        raise Exception("VISION_API_KEY not configured")

    # Encode image to base64
    image_content = base64.b64encode(image_data).decode('utf-8')

    headers = {
        "Authorization": f"Api-Key {VISION_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "folderId": FOLDER_ID,
        "analyze_specs": [{
            "features": [{
                "type": "TEXT_DETECTION",
                "text_detection_config": {
                    "language_codes": ["*"]  # Auto-detect language
                }
            }],
            "mimeType": "image/jpeg",
            "content": image_content
        }]
    }

    response = requests.post(YANDEX_VISION_URL, headers=headers, json=payload, timeout=30)
    response.raise_for_status()

    result = response.json()

    # Extract text from Vision response
    try:
        text_annotations = result["results"][0]["results"][0]["textDetection"]["pages"][0]["blocks"]
        extracted_text = ""

        for block in text_annotations:
            for line in block["lines"]:
                extracted_text += line["text"] + "\n"

        return extracted_text.strip()

    except (KeyError, IndexError) as e:
        raise Exception("Failed to extract text from Vision response") from e

def classify_question(text: str) -> bool:
    """Determine if text is an exam question about Operating Systems"""
    # Simple keyword-based classification (can be enhanced with YandexGPT)
    question_indicators = ["?", "вопрос", "объясните", "расскажите", "что такое", "как", "почему"]
    os_keywords = ["операционная система", "ОС", "процесс", "поток", "память",
                   "файловая система", "deadlock", "взаимное исключение", "синхронизация",
                   "виртуальная память", "планирование", "диспетчеризация"]

    text_lower = text.lower()

    # Check if it contains question indicators and OS-related terms
    has_question = any(indicator in text_lower for indicator in question_indicators)
    has_os_content = any(keyword in text_lower for keyword in os_keywords)

    return has_question and has_os_content

def generate_reply_from_yandex_gpt(user_text: str) -> str:
    """Generate answer using YandexGPT"""
    headers = {
        "Authorization": f"Api-Key {YC_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "modelUri": MODEL_URI,
        "completionOptions": {
            "stream": False,
            "temperature": 0.3,
            "maxTokens": 800
        },
        "messages": [
            {
                "role": "system",
                "text": "Ты эксперт по операционным системам. Отвечай кратко и по существу на экзаменационные вопросы. Форматируй ответ четко и структурированно."
            },
            {
                "role": "user",
                "text": f"Ответь на следующий вопрос по операционным системам: {user_text}"
            }
        ]
    }

    resp = requests.post(YANDEX_GPT_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    result = data.get("result", {})
    alts = result.get("alternatives", [])
    if not alts:
        raise Exception("No alternatives in response")

    message = alts[0].get("message", {})
    return message.get("text", GENERATION_ERROR_RESPONSE)

def send_telegram_message(chat_id: int, text: str):
    """Send message to Telegram"""
    payload = {"chat_id": chat_id, "text": text}
    r = requests.post(f"{TG_API}/sendMessage", json=payload, timeout=15)
    r.raise_for_status()

def handle_text_message(text: str, chat_id: int):
    """Process text message"""
    if text.startswith("/start") or text.startswith("/help"):
        send_telegram_message(chat_id, START_RESPONSE)
        return

    # Classify if it's a question about Operating Systems
    if classify_question(text):
        try:
            reply = generate_reply_from_yandex_gpt(text)
            send_telegram_message(chat_id, reply)
        except Exception as e:
            print(f"GPT Error: {e}")
            send_telegram_message(chat_id, GENERATION_ERROR_RESPONSE)
    else:
        send_telegram_message(chat_id, NON_QUESTION_RESPONSE)

def handle_photo_message(photos: list, chat_id: int):
    """Process photo message"""
    # if len(photos) > 1:
    #     send_telegram_message(chat_id, MULTIPLE_PHOTOS_RESPONSE)
        # return

    try:
        # Get the highest quality photo (last in the array)
        photo = photos[-1]
        file_id = photo["file_id"]

        # Download photo
        image_data = download_photo_from_telegram(file_id)

        # Process with Yandex Vision
        extracted_text = process_photo_with_vision(image_data)

        if not extracted_text:
            send_telegram_message(chat_id, "Не удалось распознать текст на фотографии.")
            return

        # Process extracted text as regular text message
        handle_text_message(extracted_text, chat_id)

    except Exception as e:
        print(f"Photo processing error: {e}")
        send_telegram_message(chat_id, PHOTO_PROCESSING_ERROR_RESPONSE)

def handler(event, context):
    """Main handler function"""
    try:
        body = event.get("body")
        update = json.loads(body) if isinstance(body, str) else body
    except Exception as e:
        print(f"JSON parsing error: {e}")
        return {"statusCode": 400, "body": "Bad request"}

    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"statusCode": 200, "body": "No message to handle"}

    chat_id = message["chat"]["id"]

    try:
        if "text" in message:
            handle_text_message(message["text"], chat_id)

        elif "photo" in message:
            handle_photo_message(message["photo"], chat_id)

        else:
            send_telegram_message(chat_id, UNSUPPORTED_MESSAGE_RESPONSE)

    except Exception as e:
        print(f"Handler error: {e}")
        send_telegram_message(chat_id, "Произошла ошибка при обработке сообщения.")

    return {"statusCode": 200, "body": "ok"}