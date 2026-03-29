# AutomationCvEmail/app/tasks.py
import os
import re
from typing import Optional
from datetime import datetime
from app.core.celery_app import celery_app
from app.services.ai_service import generate_regeneration_content_sync, generate_rewrite_content_sync
from app.schemas.cv_schema import AdditionalInfo, PersonalInfoResponse, CVDataInput
from app.services.file_service import download_file_sync, extract_text_from_bytes, extract_candidate_photo

def calculate_true_experience(employment_history) -> float:
    total_months = 0
    current_year = datetime.now().year
    
    year_pattern = r"(\d{4})"
    
    for job in employment_history:
        try:
            d_range = job.date_range.lower()
            years = re.findall(year_pattern, d_range)
            
            start_year = 0
            end_year = 0
            
            if not years:
                continue
            
            # Case 1: "2015 - 2018" -> [2015, 2018]
            if len(years) >= 2:
                start_year = int(years[0])
                end_year = int(years[1])
            
            # Case 2: "2021 - Present" -> [2021]
            elif len(years) == 1:
                start_year = int(years[0])
                if "present" in d_range or "current" in d_range or "now" in d_range:
                    end_year = current_year
                else:
                    end_year = start_year + 1 
            
            if end_year >= start_year:
                duration = end_year - start_year
                
                if duration == 0: duration = 0.5
                
                total_months += (duration * 12)
        
        except Exception:
            continue
    
    # Convert months to years (1 decimal place)
    return round(total_months / 12, 1)

# --- CELERY TASK ---
@celery_app.task(bind=True, max_retries=3)
def regenerate_cv_task(self, cv_url: str, additional_info_dict: dict = None):
    try:
        # Convert dict back to Pydantic
        additional_info = AdditionalInfo(**additional_info_dict) if additional_info_dict else None
        
        # Download
        file_bytes, filename = download_file_sync(cv_url)
        
        # Extract Text
        raw_text = extract_text_from_bytes(file_bytes, filename)
        
        # Extract Photo
        base_url = os.getenv("APP_BASE_URL", "http://localhost:8000/")
        photo_url = extract_candidate_photo(file_bytes, filename, base_url)
        
        # AI Processing
        ai_result = generate_regeneration_content_sync(raw_text, additional_info)
        
        calculated_years = calculate_true_experience(ai_result.employment_history)
        
        ai_result.extracted_personal_info.total_years_experience = calculated_years
        
        if calculated_years == 0:
            ai_result.extracted_personal_info.experience_summary = "Fresher"
        else:
            ai_result.extracted_personal_info.experience_summary = f"{calculated_years} Years"
        
        # Logic: Quality Check
        quality_status = "manual review"
        if calculated_years >= 0.5:
            quality_status = "pass"
        else:
            quality_status = "fail"
        
        provided_job_roles = additional_info.job_role if additional_info else None

        # Format Response
        personal_info_resp = PersonalInfoResponse(
            full_name=ai_result.extracted_personal_info.full_name,
            email=ai_result.extracted_personal_info.email,
            whatsapp=ai_result.extracted_personal_info.whatsapp,
            skill=ai_result.extracted_personal_info.skills,
            job_role=provided_job_roles,
            experience=ai_result.extracted_personal_info.experience_summary, # Now uses our math
            location=ai_result.extracted_personal_info.location
        ).model_dump()
        
        data_extracted = ai_result.model_dump(exclude={'extracted_personal_info'})
        
        return {
            "status": "success",
            "message": "CV analysis completed.",
            "quality_check": quality_status,
            "extracted_photo_url": photo_url,
            "data_extracted": data_extracted,
            "personal_info": personal_info_resp
        }
    
    except Exception as e:
        print(f"Task Failed: {e}")
        raise self.retry(exc=e, countdown=10 * (2 ** self.request.retries))

@celery_app.task(bind=True, max_retries=3)
def rewrite_cv_task(self, cv_data_dict: dict, instruction: Optional[str] = None):
    try:
        # Convert Dict -> Pydantic
        cv_data_input = CVDataInput(**cv_data_dict)
        
        # Call AI to Rewrite
        rewritten_result = generate_rewrite_content_sync(cv_data_input, instruction)
        
        # Return format
        return {
            "status": "success",
            "message": "CV rewritten successfully.",
            "data_extracted": rewritten_result.model_dump()
        }
    
    except Exception as e:
        print(f"Rewrite Task Failed: {e}")
        raise self.retry(exc=e, countdown=10 * (2 ** self.request.retries))