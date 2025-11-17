import os
import json
import requests
import base64
from typing import Optional, Tuple, Dict, Any
import boto3
from botocore.config import Config

_INSTRUCTIONS: Optional[Dict[str, Any]] = None

TELEGRAM_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
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

def load_instructions_from_s3() -> Dict[str, Any]:
    """
    Load instructions JSON from Yandex Object Storage using S3 API.
    Requires env vars: STORAGE_ACCESS_KEY, STORAGE_SECRET_KEY, STORAGE_ENDPOINT, STORAGE_BUCKET, STORAGE_OBJECT_KEY
    """
    global _INSTRUCTIONS
    if _INSTRUCTIONS is not None:
        return _INSTRUCTIONS

    access_key = os.getenv("STORAGE_ACCESS_KEY")
    secret_key = os.getenv("STORAGE_SECRET_KEY")
    endpoint = os.getenv("STORAGE_ENDPOINT", "https://storage.yandexcloud.net")
    bucket = os.getenv("STORAGE_BUCKET")
    key = os.getenv("STORAGE_OBJECT_KEY")

    if not (access_key and secret_key and bucket and key):
        # If missing, fall back to a local/default instruction (safe)
        _INSTRUCTIONS = {
            "classification_prompt": "You are an assistant that classifies whether a message is an exam question about Operating Systems. Respond in JSON: {\"is_question\": true|false, \"explanation\": \"...\"}.",
            "generation_prompt": "You are an expert in Operating Systems. Answer the exam question concisely. Requirements: structured, short, in Russian. Question: {{QUESTION}}"
        }
        return _INSTRUCTIONS

    # create S3 client pointing to Yandex Object Storage
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
    )

    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        content = obj["Body"].read()
        instructions = json.loads(content.decode("utf-8"))
        _INSTRUCTIONS = instructions
        return instructions
    except Exception as e:
        print(f"Error loading instructions from S3: {e}")
        # fallback to default minimal instruction
        _INSTRUCTIONS = {
            "classification_prompt": "You are an assistant that classifies whether a message is an exam question about Operating Systems. Respond in JSON: {\"is_question\": true|false, \"explanation\": \"...\"}.",
            "generation_prompt": "You are an expert in Operating Systems. Answer the exam question concisely. Requirements: structured, short, in Russian. Question: {{QUESTION}}"
        }
        return _INSTRUCTIONS


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
    """Extract text from photo using Yandex Vision OCR (robust version)"""
    if not VISION_API_KEY:
        raise Exception("VISION_API_KEY not configured")

    image_content = base64.b64encode(image_data).decode("utf-8")

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
                    "language_codes": ["*"]
                }
            }],
            "mimeType": "image/jpeg",
            "content": image_content
        }]
    }

    response = requests.post(YANDEX_VISION_URL, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    result = response.json()

    # --- Clean debug output (truncated for readability) ---
    print("🧩 [DEBUG] Vision response summary:")
    try:
        num_pages = len(result["results"][0]["results"][0]["textDetection"]["pages"])
        print(f"📄 Pages detected: {num_pages}")
    except Exception:
        print("⚠️ Could not count pages, raw JSON structure unexpected.")
    # Optional: print only the first 500 chars of JSON for readability
    print(json.dumps(result, indent=2, ensure_ascii=False)[:500] + "...\n")

    try:
        vision_results = result["results"][0]["results"][0]["textDetection"]
        
        if "fullText" in vision_results:
            return vision_results["fullText"].strip()

      
        pages = vision_results.get("pages", [])
        extracted_lines = []

        for page in pages:
            for block in page.get("blocks", []):
                for line in block.get("lines", []):
                    # Gather words within each line
                    words = [w.get("text", "") for w in line.get("words", []) if w.get("text")]
                    if words:
                        extracted_lines.append(" ".join(words))

        extracted_text = "\n".join(extracted_lines).strip()
        return extracted_text

    except (KeyError, IndexError, TypeError) as e:
        print("Unexpected Vision API structure:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
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

def call_yandex_gpt(messages: list, max_tokens: int = 500, temperature: float = 0.3) -> str:
    if not YC_API_KEY:
        raise Exception("YC_API_KEY not configured")

    headers = {
        "Authorization": f"Api-Key {YC_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "modelUri": MODEL_URI,
        "completionOptions": {
            "stream": False,
            "temperature": temperature,
            "maxTokens": max_tokens
        },
        "messages": messages
    }

    resp = requests.post(YANDEX_GPT_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    result = data.get("result", {})
    alts = result.get("alternatives", [])
    if not alts:
        raise Exception("No alternatives in response")
    message = alts[0].get("message", {})
    return message.get("text", "")

def generate_answer_via_yandex_gpt(question_text: str) -> str:
    instructions = load_instructions_from_s3()
    gen_template = instructions.get("generation_prompt",
                                    "You are an expert in Operating Systems. Answer the exam question concisely. Question: {{QUESTION}}")
    prompt = gen_template.replace("{{QUESTION}}", question_text)

    messages = [
        {"role": "system", "text": "You are an expert in Operating Systems. Answer exam questions concisely and in Russian. Format: short heading, bullet points, concise explanation."},
        {"role": "user", "text": prompt}
    ]

    return call_yandex_gpt(messages, max_tokens=800, temperature=0.25)

#
# def generate_reply_from_yandex_gpt(user_text: str) -> str:
#     """Generate answer using YandexGPT"""
#     headers = {
#         "Authorization": f"Api-Key {YC_API_KEY}",
#         "Content-Type": "application/json",
#     }
#
#     payload = {
#         "modelUri": MODEL_URI,
#         "completionOptions": {
#             "stream": False,
#             "temperature": 0.3,
#             "maxTokens": 800
#         },
#         "messages": [
#             {
#                 "role": "system",
#                 "text": "Ты эксперт по операционным системам. Отвечай кратко и по существу на экзаменационные вопросы. Форматируй ответ четко и структурированно."
#             },
#             {
#                 "role": "user",
#                 "text": f"Ответь на следующий вопрос по операционным системам: {user_text}"
#             }
#         ]
#     }
#
#     resp = requests.post(YANDEX_GPT_URL, headers=headers, json=payload, timeout=30)
#     resp.raise_for_status()
#     data = resp.json()
#
#     result = data.get("result", {})
#     alts = result.get("alternatives", [])
#     if not alts:
#         raise Exception("No alternatives in response")
#
#     message = alts[0].get("message", {})
#     return message.get("text", GENERATION_ERROR_RESPONSE)

def simple_keyword_classify(text: str) -> bool:
    question_indicators = ["?", "вопрос", "объясните", "расскажите", "что такое", "как", "почему"]
    os_keywords = ["операционная система", "ос", "процесс", "поток", "память",
                   "файловая система", "deadlock", "взаимное исключение", "синхронизация",
                   "виртуальная память", "планирование", "диспетчеризация"]
    text_lower = text.lower()
    has_question = any(ind in text_lower for ind in question_indicators)
    has_os = any(k in text_lower for k in os_keywords)
    return has_question and has_os


def classify_with_yandex_gpt(text: str) -> Tuple[bool, Optional[str]]:
    """
    Ask YandexGPT to classify whether text is an OS exam question.
    Returns (is_question, explanation)
    """
    instructions = load_instructions_from_s3()
    classification_prompt = instructions.get("classification_prompt",
                                             "You are an assistant that classifies whether a message is an exam question about Operating Systems. Respond in JSON with keys {\"is_question\": true|false, \"explanation\": \"short\"}.")

    # Build messages
    messages = [
        {"role": "system", "text": "You are a classifier. Answer only in valid JSON."},
        {"role": "user", "text": f"{classification_prompt}\n\nMessage: {text}"}
    ]

    try:
        resp_text = call_yandex_gpt(messages, max_tokens=150, temperature=0.0)
        # Try to find JSON inside resp_text
        # Some LLMs wrap with backticks - attempt robust parse
        try:
            # if response is exactly JSON, parse directly
            parsed = json.loads(resp_text)
        except Exception:
            # try to extract first {...} block
            start = resp_text.find("{")
            end = resp_text.rfind("}")
            if start != -1 and end != -1 and end > start:
                parsed = json.loads(resp_text[start:end+1])
            else:
                raise
        is_q = bool(parsed.get("is_question", False))
        explanation = parsed.get("explanation", "")
        return is_q, explanation
    except Exception as e:
        print(f"Classification error: {e}")
        # fallback to simple keyword approach if LLM fails
        try:
            return simple_keyword_classify(text), "fallback_keyword"
        except Exception:
            return False, None


def send_telegram_message(chat_id: int, text: str):
    """Send message to Telegram"""
    payload = {"chat_id": chat_id, "text": text}
    r = requests.post(f"{TG_API}/sendMessage", json=payload, timeout=15)
    r.raise_for_status()

def handle_text_message(text: str, chat_id: int):
    if text.startswith("/start") or text.startswith("/help"):
        send_telegram_message(chat_id, START_RESPONSE)
        return

    # Use YandexGPT classifier
    try:
        is_q, explanation = classify_with_yandex_gpt(text)
    except Exception as e:
        print(f"Classifier exception: {e}")
        is_q = False

    if not is_q:
        send_telegram_message(chat_id, NON_QUESTION_RESPONSE)
        return

    # It's a question — generate answer via YandexGPT using generation template
    try:
        reply = generate_answer_via_yandex_gpt(text)
        send_telegram_message(chat_id, reply)
    except Exception as e:
        print(f"GPT generation error: {e}")
        send_telegram_message(chat_id, GENERATION_ERROR_RESPONSE)
def handle_photo_message(photos: list, chat_id: int):
    """Process photo message with debugging — sends all received photos back."""
    try:
        # Telegram sends multiple photo sizes for one image
        count = len(photos)
        send_telegram_message(chat_id, f"📸 Получено {count} изображений от Telegram (разные размеры).")

        for idx, photo in enumerate(photos):
            file_id = photo["file_id"]
            width = photo.get("width")
            height = photo.get("height")
            size = photo.get("file_size")

            # Log info
            print(f"[DEBUG] Photo #{idx+1}: file_id={file_id}, {width}x{height}, size={size}")

            # Send file info to user
            send_telegram_message(
                chat_id,
                f"🖼 Фото #{idx+1} — {width}x{height}, file_id={file_id}, size={size}"
            )

            # Re-send each version of the photo back to user
            requests.post(
                f"{TG_API}/sendPhoto",
                data={"chat_id": chat_id, "photo": file_id},
                timeout=10
            )

        # Use the largest photo (last in the list)
        photo = photos[-1]
        file_id = photo["file_id"]
        send_telegram_message(chat_id, f"✅ Использую последнее фото (file_id={file_id}) для OCR.")

        # Download full image
        image_data = download_photo_from_telegram(file_id)
        print(f"[DEBUG] Downloaded {len(image_data)} bytes from Telegram")

        # Process with Yandex Vision
        extracted_text = process_photo_with_vision(image_data)

        if not extracted_text:
            send_telegram_message(chat_id, "⚠️Не удалось распознать текст на фотографии.")
            return

        # Send extracted text for verification
        send_telegram_message(chat_id, f"🧾 Распознанный текст:\n\n{extracted_text[:4000]}")

        # Process extracted text as regular text message
        handle_text_message(extracted_text, chat_id)

    except Exception as e:
        print(f"Photo processing error: {e}")
        send_telegram_message(chat_id, f"❌ Ошибка обработки фото: {e}")

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
