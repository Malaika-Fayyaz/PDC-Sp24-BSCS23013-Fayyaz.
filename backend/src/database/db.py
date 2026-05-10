from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from . import models


def get_challenge_quota(db: Session, user_id: str):
    return (db.query(models.ChallengeQuota)
            .filter(models.ChallengeQuota.user_id == user_id)
            .first())


def create_challenge_quota(db: Session, user_id: str):
    db_quota = models.ChallengeQuota(user_id=user_id)
    db.add(db_quota)
    db.commit()
    db.refresh(db_quota)
    return db_quota


def reset_quota_if_needed(db: Session, quota: models.ChallengeQuota):
    now = datetime.now()
    if now - quota.last_reset_date > timedelta(hours=24):
        quota.quota_remaining = 10
        quota.last_reset_date = now
        db.commit()
        db.refresh(quota)
    return quota


def create_challenge(
    db: Session,
    difficulty: str,
    created_by: str,
    title: str,
    options: str,
    correct_answer_id: int,
    explanation: str
):
    db_challenge = models.Challenge(
        difficulty=difficulty,
        created_by=created_by,
        title=title,
        options=options,
        correct_answer_id=correct_answer_id,
        explanation=explanation
    )
    db.add(db_challenge)
    db.commit()
    db.refresh(db_challenge)
    return db_challenge


def get_user_challenges(db: Session, user_id: str):
    return db.query(models.Challenge).filter(models.Challenge.created_by == user_id).all()


def update_challenge_with_optimistic_locking(
    db: Session,
    challenge_id: int,
    current_version: int,
    title: str = None,
    options: str = None,
    correct_answer_id: int = None,
    explanation: str = None
):
    """
    Update a challenge using optimistic locking.
    
    Returns:
        - (challenge, True) if update successful
        - (challenge, False) if version conflict (stale update)
    """
    challenge = db.query(models.Challenge).filter(
        models.Challenge.id == challenge_id
    ).first()
    
    if not challenge:
        return None, None  # Not found
    
    # Check if version matches (optimistic lock)
    if challenge.version != current_version:
        return challenge, False  # Version mismatch - conflict!
    
    # Version matches, proceed with update
    if title is not None:
        challenge.title = title
    if options is not None:
        challenge.options = options
    if correct_answer_id is not None:
        challenge.correct_answer_id = correct_answer_id
    if explanation is not None:
        challenge.explanation = explanation
    
    # Increment version
    challenge.version += 1
    
    db.commit()
    db.refresh(challenge)
    
    return challenge, True  # Success
