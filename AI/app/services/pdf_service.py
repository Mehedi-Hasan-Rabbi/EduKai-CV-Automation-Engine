# AutomationCvEmail/app/services/pdf_service.py
import os, uuid
from weasyprint import HTML
from jinja2 import Environment, FileSystemLoader
from app.schemas.cv_schema import CVStructuredData

OUTPUT_DIR = "app/static/generated"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def generate_and_save_pdf(data: CVStructuredData, base_url: str) -> str:
    # Setup Jinja2
    env = Environment(loader=FileSystemLoader('app/templates'))
    template = env.get_template('cv_template.html')
    
    logo_path = "file://" + os.path.abspath("app/static/edukai_logo.png")
    
    html_content = template.render(cv=data, logo_path=logo_path)
    
    if data.name:
        data.name = data.name.strip().split(" ")[0]
    
    # Generate Filename (Unique to avoid overwriting)
    clean_name = data.name.replace(" ", "_") # Clean filename using the sanitized name
    unique_id = uuid.uuid4().hex[:6]
    filename = f"{clean_name}_{unique_id}.pdf"
    file_path = os.path.join(OUTPUT_DIR, filename)
    
    print(f"Generating PDF at: {file_path}")
    HTML(string=html_content).write_pdf(file_path)
    
    return filename, file_path