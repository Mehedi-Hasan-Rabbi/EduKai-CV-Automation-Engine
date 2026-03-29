# AutomationCvEmail/app/api/v1/routes.py
from fastapi import APIRouter
from celery.result import AsyncResult
from app.tasks import regenerate_cv_task, rewrite_cv_task
from app.schemas.cv_schema import RegenerationRequest, RewriteRequest, RewriteResponse

router = APIRouter()

@router.post("/regeneration", status_code=202)
async def regenerate_cv_endpoint(payload: RegenerationRequest):
    info_dict = payload.additional_info.model_dump() if payload.additional_info else None
    task = regenerate_cv_task.delay(payload.cv_url, info_dict)
    
    return {
        "status": "processing",
        "task_id": task.id,
        "message": "CV queued for regeneration. Poll /tasks/{task_id} for results."
    }

@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    task_result = AsyncResult(task_id)
    
    if task_result.state == 'SUCCESS':
        return {
            "status": "completed",
            "result": task_result.result 
        }
    elif task_result.state == 'FAILURE':
        return {"status": "failed", "error": str(task_result.result)}
        
    return {"status": task_result.state} 

@router.post("/rewrite", status_code=202, response_model=RewriteResponse)
async def rewrite_cv_endpoint(payload: RewriteRequest):
    data_dict = payload.cv_data.model_dump()
    task = rewrite_cv_task.delay(data_dict, payload.instruction)
    
    return RewriteResponse(
        status="processing",
        task_id=task.id,
        message="CV rewrite queued. Poll /tasks/{task_id} for results."
    )