# AutomationCvEmail/app/services/ai_service.py
import os
from typing import Optional
from pathlib import Path
from openai import OpenAI
from app.core.config import settings
from app.schemas.cv_schema import AIAnalysisResult, AdditionalInfo, CVDataInput

sync_client = OpenAI(api_key=settings.OPENAI_API_KEY)

def load_prompt_from_file(filename: str) -> str:
    try:
        current_file_dir = Path(__file__).resolve().parent
        prompt_path = current_file_dir.parent / "prompts" / filename
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"Error reading prompt file {filename}: {e}")
        return ""

def _get_system_prompt():
    cv_instructions = load_prompt_from_file("cv_instruction.txt")
    email_instructions = load_prompt_from_file("email_instruction.txt")
    
    return f"""
    You are an expert UK Education Recruiter for 'Edukai'.
    
    YOUR TASK IS TWOFOLD:
    1. REWRITE the CV (Anonymized) for the Client.
    2. EXTRACT the REAL personal details for the Agency.

    --- PART 1: CV REWRITING INSTRUCTIONS (ANONYMIZED) ---
    {cv_instructions}
    
    --- PART 2: EMAIL DRAFTING INSTRUCTIONS ---
    {email_instructions}
    CRITICAL: The Email Subject must be STRICTLY PROFESSIONAL. NO EMOJIS.
    
    --- PART 3: DATA EXTRACTION (REAL INFO) ---
    - Extract the candidate's REAL Full Name, Email, and Phone/Whatsapp.
    - Calculate the TOTAL years of relevant experience.
    """

def generate_regeneration_content_sync(raw_text: str, additional_info: AdditionalInfo = None) -> AIAnalysisResult:
    user_content = f"Here is the Raw Candidate CV Text:\n\n{raw_text}"
    
    if additional_info:
        user_content += "\n\n--- ADDITIONAL CONTEXT/OVERRIDES ---\n"
        if additional_info.job_role:
            user_content += f"Target Job Roles: {', '.join(additional_info.job_role)}\n"
        if additional_info.skills:
            user_content += f"Key Skills to Highlight: {', '.join(additional_info.skills)}\n"
        if additional_info.current_location:
            user_content += f"Candidate Location: {additional_info.current_location}\n"
        if additional_info.experience:
            user_content += f"Candidate stated experience: {additional_info.experience}\n"
    
    # Call OpenAI
    try:
        completion = sync_client.beta.chat.completions.parse(
            model="gpt-4o-2024-08-06",
            messages=[
                {"role": "system", "content": _get_system_prompt()},
                {"role": "user", "content": user_content},
            ],
            response_format=AIAnalysisResult,
        )
        return completion.choices[0].message.parsed
    except Exception as e:
        print(f"OpenAI Error: {e}")
        raise e

# SYNC FUNCTION FOR REWRITE TASK 
def generate_rewrite_content_sync(current_data: CVDataInput, custom_instruction: Optional[str] = None) -> CVDataInput:
    base_instructions = load_prompt_from_file("rewrite_instruction.txt")
    
    system_prompt = f"""
    {base_instructions}
    
    CRITICAL: Return the result in the exact same JSON structure.
    """
    
    user_content = f"Here is the Current CV JSON:\n{current_data.model_dump_json()}"
    
    if custom_instruction and custom_instruction.strip():
        user_content += f"\n\nUSER EXTRA INSTRUCTION: {custom_instruction}"
    
    try:
        completion = sync_client.beta.chat.completions.parse(
            model="gpt-4o-2024-08-06",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format=CVDataInput, 
        )
        return completion.choices[0].message.parsed
    except Exception as e:
        print(f"OpenAI Rewrite Error: {e}")
        raise e