from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..ai_generator import generate_challenge_with_ai
from ..database.db import (
    get_challenge_quota,
    create_challenge,
    create_challenge_quota,
    reset_quota_if_needed,
    get_user_challenges,
    update_challenge_with_optimistic_locking
)
from ..utils import authenticate_and_get_user_details
from ..database.models import get_db
import json
from datetime import datetime

router = APIRouter()


class ChallengeRequest(BaseModel):
    difficulty: str

    class Config:
        json_schema_extra = {"example": {"difficulty": "easy"}}


class UpdateChallengeRequest(BaseModel):
    """Request model for updating a challenge with optimistic locking"""
    version: int  # Current version the client is updating from
    title: str = None
    options: list = None
    correct_answer_id: int = None
    explanation: str = None

    class Config:
        json_schema_extra = {
            "example": {
                "version": 1,
                "title": "Updated Title",
                "explanation": "Updated explanation"
            }
        }


def challenge_to_dict(challenge_obj):
    """Convert Challenge model to dictionary with version included"""
    return {
        "id": challenge_obj.id,
        "difficulty": challenge_obj.difficulty,
        "title": challenge_obj.title,
        "options": json.loads(challenge_obj.options),
        "correct_answer_id": challenge_obj.correct_answer_id,
        "explanation": challenge_obj.explanation,
        "timestamp": challenge_obj.date_created.isoformat(),
        "version": challenge_obj.version
    }


@router.post("/generate-challenge")
async def generate_challenge(request: ChallengeRequest, request_obj: Request, db: Session = Depends(get_db)):
    try:
        user_details = authenticate_and_get_user_details(request_obj)
        user_id = user_details.get("user_id")

        quota = get_challenge_quota(db, user_id)
        if not quota:
            quota = create_challenge_quota(db, user_id)

        quota = reset_quota_if_needed(db, quota)

        if quota.quota_remaining <= 0:
            raise HTTPException(status_code=429, detail="Quota exhausted")

        challenge_data = generate_challenge_with_ai(request.difficulty)

        new_challenge = create_challenge(
            db=db,
            difficulty=request.difficulty,
            created_by=user_id,
            title=challenge_data["title"],
            options=json.dumps(challenge_data["options"]),
            correct_answer_id=challenge_data["correct_answer_id"],
            explanation=challenge_data["explanation"]
        )

        quota.quota_remaining -= 1
        db.commit()

        return challenge_to_dict(new_challenge)

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/my-history")
async def my_history(request: Request, db: Session = Depends(get_db)):
    user_details = authenticate_and_get_user_details(request)
    user_id = user_details.get("user_id")

    challenges = get_user_challenges(db, user_id)
    return {"challenges": [challenge_to_dict(c) for c in challenges]}


@router.get("/quota")
async def get_quota(request: Request, db: Session = Depends(get_db)):
    user_details = authenticate_and_get_user_details(request)
    user_id = user_details.get("user_id")

    quota = get_challenge_quota(db, user_id)
    if not quota:
        return {
            "user_id": user_id,
            "quota_remaining": 0,
            "last_reset_date": datetime.now()
        }

    quota = reset_quota_if_needed(db, quota)
    return quota


@router.patch("/challenge/{challenge_id}")
async def update_challenge(
    challenge_id: int,
    update_request: UpdateChallengeRequest,
    request_obj: Request,
    db: Session = Depends(get_db)
):
    """
    Update a challenge using optimistic locking.
    
    The client must provide the current version of the resource.
    If the version doesn't match, a 409 Conflict is returned with the current version.
    """
    try:
        user_details = authenticate_and_get_user_details(request_obj)
        user_id = user_details.get("user_id")
        
        # Prepare update parameters (only include fields that are not None)
        update_params = {}
        if update_request.title is not None:
            update_params["title"] = update_request.title
        if update_request.options is not None:
            update_params["options"] = json.dumps(update_request.options)
        if update_request.correct_answer_id is not None:
            update_params["correct_answer_id"] = update_request.correct_answer_id
        if update_request.explanation is not None:
            update_params["explanation"] = update_request.explanation
        
        # Attempt update with optimistic locking
        challenge, success = update_challenge_with_optimistic_locking(
            db=db,
            challenge_id=challenge_id,
            current_version=update_request.version,
            **update_params
        )
        
        if challenge is None:
            raise HTTPException(status_code=404, detail="Challenge not found")
        
        if not success:
            # Version conflict - resource was modified
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "Conflict",
                    "message": f"Resource was modified. Current version is {challenge.version}, you submitted version {update_request.version}",
                    "current_version": challenge.version
                }
            )
        
        return challenge_to_dict(challenge)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
