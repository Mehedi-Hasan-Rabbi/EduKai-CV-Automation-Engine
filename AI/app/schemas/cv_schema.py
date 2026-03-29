# AutomationCvEmail/app/schemas/cv_schema.py
from pydantic import BaseModel, Field
from typing import List, Optional, Literal

# INPUTS 
class AdditionalInfo(BaseModel):
    experience: Optional[float | int | str] = None
    skills: Optional[List[str]] = None
    job_role: Optional[List[str]] = None
    current_location: Optional[str] = None

class RegenerationRequest(BaseModel):
    id: Optional[int] = None
    cv_url: str
    additional_info: Optional[AdditionalInfo] = None

# INTERNAL AI STRUCTURES 
class EmploymentHistory(BaseModel):
    date_range: str
    role: str
    company: str
    responsibilities: List[str]

class PersonalInfoExtraction(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    whatsapp: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    location: Optional[str] = None
    total_years_experience: Optional[float] = Field(description="Total relevant experience in years. Return 0 if fresher.")
    experience_summary: str = Field(description="e.g. '5 years' or 'Fresher'")

class AIAnalysisResult(BaseModel):
    name: str = Field(description="First name only (Anonymized)")
    role: List[str] = Field(description="List of current professional titles or roles")
    location: str
    availability: str
    professional_profile: str
    employment_history: List[EmploymentHistory]
    qualifications: List[str]
    interests: Optional[str] = None
    email_subject: str
    email_body: str
    extracted_personal_info: PersonalInfoExtraction

# OUTPUTS 
class PersonalInfoResponse(BaseModel):
    full_name: Optional[str]
    email: Optional[str]
    whatsapp: Optional[str]
    skill: List[str]
    job_role: Optional[List[str]] = None
    experience: str
    location: Optional[str]

class RegenerationResponse(BaseModel):
    status: str
    message: str
    quality_check: Literal["pass", "fail", "manual review"]
    extracted_photo_url: Optional[str] = Field(default=None, description="URL to the candidate's extracted photo")
    data_extracted: dict 
    personal_info: PersonalInfoResponse

class CVDataInput(BaseModel):
    name: str
    role: List[str] = Field(description="List of current professional titles or roles")
    location: str
    availability: str
    professional_profile: str
    employment_history: List[EmploymentHistory]
    qualifications: List[str]
    interests: Optional[str] = None
    email_subject: str
    email_body: str

class RewriteRequest(BaseModel):
    cv_data: CVDataInput
    instruction: Optional[str] = Field(default=None, description="Optional custom instruction for the editor")

class RewriteResponse(BaseModel):
    status: str
    task_id: str
    message: str