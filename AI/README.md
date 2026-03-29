# AutomationCvEmail

AutomationCvEmail is an AI-powered CV processing service built with **FastAPI, Celery, Redis, and OpenAI**.
It automatically **analyzes candidate CVs, extracts structured information, rewrites the CV professionally, and generates recruiter-ready candidate introduction emails**.

The system is designed for recruitment workflows where agencies need to quickly convert raw CVs into **high-quality anonymized candidate profiles and marketing emails** for potential employers.

---

# Key Features

### CV Processing Pipeline

* Download CV from a remote URL
* Extract text from **PDF or DOCX**
* Extract candidate photo from the document
* Process the CV with AI to produce a structured candidate profile

### AI-Powered CV Enhancement

* Rewrite CV for professional presentation
* Tailor CV content for **UK education recruitment**
* Improve language, structure, and impact

### Email Generation

Automatically generates a **candidate introduction email** suitable for sending to hiring managers.

### Structured Data Extraction

Extracts real candidate data including:

* Name
* Email
* WhatsApp / phone
* Skills
* Location
* Employment history
* Total experience

### Background Processing

Heavy tasks run asynchronously using **Celery + Redis**, preventing API blocking.

### CV Quality Check

Automatically categorizes candidates based on calculated experience:

* pass
* fail
* manual review

---

# Tech Stack

| Component        | Technology         |
| ---------------- | ------------------ |
| API Framework    | FastAPI            |
| Background Jobs  | Celery             |
| Queue / Broker   | Redis              |
| AI Processing    | OpenAI GPT-4o      |
| Document Parsing | PyPDF, python-docx |
| Image Processing | Pillow             |
| PDF Generation   | WeasyPrint         |
| Template Engine  | Jinja2             |
| Data Validation  | Pydantic           |

---

# Project Structure

```
AutomationCvEmail/
│
├── app/
│   ├── api/
│   │   └── v1/
│   │       └── routes.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   └── celery_app.py
│   │
│   ├── services/
│   │   ├── ai_service.py
│   │   ├── file_service.py
│   │   └── pdf_service.py
│   │
│   ├── schemas/
│   │   └── cv_schema.py
│   │
│   ├── tasks.py
│   ├── main.py
│   │
│   ├── prompts/
│   │   ├── cv_instruction.txt
│   │   ├── email_instruction.txt
│   │   └── rewrite_instruction.txt
│   │
│   ├── templates/
│   └── static/
│
└── README.md
```

---

# System Architecture

```
Client
   │
   ▼
FastAPI API
   │
   ▼
Redis Queue
   │
   ▼
Celery Worker
   │
   ├── File Download
   ├── Text Extraction
   ├── Photo Extraction
   ├── AI CV Analysis
   ├── Experience Calculation
   └── Response Formatting
```

---

# Processing Flow

1. User submits CV URL to the API.
2. API pushes a background job to Celery.
3. Worker downloads and parses the CV.
4. AI processes the document and produces structured output.
5. Experience is calculated programmatically.
6. CV data and email draft are generated.
7. User polls the task endpoint to retrieve results.

---

# Installation

## 1. Clone the repository

```
git clone https://gitlab.com/FrostSight/cv-regeneration-and-email-writing-for-okia.git
cd AutomationCvEmail
```

---

## 2. Create a virtual environment

```
python -m venv venv
source venv/bin/activate
```

Windows

```
venv\Scripts\activate
```

---

## 3. Install dependencies

```
pip install -r requirements.txt
```

---

## 4. Environment variables

Create `.env`

```
OPENAI_API_KEY=your_openai_api_key
REDIS_URL=redis://localhost:6379/3
APP_BASE_URL=http://127.0.0.1:8000/
```

---

# Running the Application

## Start Redis

```
redis-server
```

---

## Start FastAPI Server

```
uvicorn app.main:app --reload
```

API docs:

```
http://localhost:8000/docs
```

---

## Start Celery Worker

```
celery -A app.core.celery_app.celery_app worker --loglevel=info
```

---

# API Endpoints

## Submit CV for processing

```
POST /api/v1/regeneration
```

Example request

```
{
  "cv_url": "https://example.com/candidate_cv.pdf",
  "additional_info": {
    "job_role": ["Teaching Assistant"],
    "skills": ["Behaviour Management", "SEN Support"],
    "current_location": "London"
  }
}
```

Response

```
{
  "status": "processing",
  "task_id": "12345"
}
```

---

## Check task status

```
GET /api/v1/tasks/{task_id}
```

Response when complete

```
{
  "status": "completed",
  "result": {
    "status": "success",
    "quality_check": "pass",
    "personal_info": {...},
    "data_extracted": {...}
  }
}
```

---

## Rewrite CV Content

```
POST /api/v1/rewrite
```

Example

```
{
  "cv_data": {...},
  "instruction": "Make the profile more concise."
}
```

---

# AI Prompt System

Prompts are stored in:

```
app/prompts/
```

This allows easy modification without changing code.

Prompts control:

* CV rewriting
* recruiter email generation
* structured information extraction

---

# Future Improvements

Possible enhancements:

* OCR support for scanned PDFs
* Cloud storage integration (S3 / GCS)
* Rate limiting and request validation
* Candidate ranking and matching
* Monitoring and observability
