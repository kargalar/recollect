from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse
import datetime
import shutil
from pathlib import Path

from database import SessionLocal, Activity, AppTag, Tag
from config import BASE_DIR, get_images_path, load_config, save_config

app = FastAPI(title="Recollect Activity API")

# Create directories if they don't exist
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

ACTIVITY_RANGES = {"all", "today", "week", "month"}
STATS_RANGES = {"all", "today", "7d", "30d"}


def period_start(range_name, allowed_ranges):
    if range_name not in allowed_ranges:
        raise HTTPException(status_code=400, detail="Unsupported date range")
    if range_name == "all":
        return None

    now = datetime.datetime.now(datetime.timezone.utc)
    if range_name == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    days = {"week": 7, "month": 30, "7d": 7, "30d": 30}
    return now - datetime.timedelta(days=days[range_name])


def safe_reset_images_path(path):
    resolved = path.resolve()
    protected_paths = (
        BASE_DIR.resolve(),
        (BASE_DIR / "static").resolve(),
        (BASE_DIR / "venv").resolve(),
        (BASE_DIR / "icons").resolve(),
    )
    if (
        resolved == Path(resolved.anchor)
        or resolved == protected_paths[0]
        or any(protected in resolved.parents for protected in protected_paths[1:])
    ):
        raise HTTPException(status_code=400, detail="Screenshot directory cannot be reset")
    return resolved


def resolve_stored_path(path):
    stored_path = Path(path)
    return stored_path if stored_path.is_absolute() else BASE_DIR / stored_path

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class AppTagUpdate(BaseModel):
    app_name: str = Field(min_length=1, max_length=255)
    tags: List[str] = Field(default_factory=list, max_length=50)

class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

class TagRename(BaseModel):
    new_name: str = Field(min_length=1, max_length=100)

class SettingsModel(BaseModel):
    images_path: str = Field(min_length=1, max_length=4096)
    screenshot_interval: int = Field(ge=1, le=3600)
    auto_pause_on_idle: bool = True

@app.get("/api/activities")
def get_activities(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    app_name: Optional[str] = None,
    date_range: Optional[str] = "all",
    q: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Activity)
    if app_name:
        query = query.filter(Activity.app_name.ilike(f"%{app_name}%"))
    
    if q:
        query = query.filter(
            (Activity.window_title.ilike(f"%{q}%")) | 
            (Activity.ocr_text.ilike(f"%{q}%")) |
            (Activity.url.ilike(f"%{q}%"))
        )
    
    start = period_start(date_range, ACTIVITY_RANGES)
    if start:
        query = query.filter(Activity.timestamp >= start)

    # Order by timestamp descending (newest first)
    activities = query.order_by(Activity.timestamp.desc()).offset(skip).limit(limit).all()
    
    return [
        {
            "id": a.id,
            "timestamp": a.timestamp.replace(tzinfo=datetime.timezone.utc).isoformat() if a.timestamp else None,
            "image_url": f"/api/image/{a.id}" if a.image_path else None,
            "icon_url": f"/api/icon/{a.id}" if a.icon_path else None,
            "app_name": a.app_name,
            "window_title": a.window_title,
            "url": a.url,
            "mouse_x": a.mouse_x,
            "mouse_y": a.mouse_y,
            "is_idle": getattr(a, 'is_idle', False)
        } for a in activities
    ]

@app.get("/api/apps")
def get_unique_apps(db: Session = Depends(get_db)):
    # Get distinct app names for filtering
    apps = db.query(Activity.app_name).distinct().all()
    return [app[0] for app in apps if app[0]]

@app.get("/api/tags")
def get_tags(db: Session = Depends(get_db)):
    from sqlalchemy import func

    sync_tags_from_assignments(db)
    db.commit()

    rows = db.query(
        Tag.name,
        func.count(AppTag.app_name).label("app_count")
    ).outerjoin(AppTag, Tag.name == AppTag.tag_name).group_by(Tag.name).order_by(Tag.name.asc()).all()

    return [{"name": name, "app_count": app_count} for name, app_count in rows]

@app.post("/api/tags")
def create_tag(payload: TagCreate, db: Session = Depends(get_db)):
    tag_name = payload.name.strip()
    if not tag_name:
        raise HTTPException(status_code=400, detail="Tag name cannot be empty")

    existing = next((tag for tag in db.query(Tag).all() if tag.name.lower() == tag_name.lower()), None)
    if existing:
        raise HTTPException(status_code=409, detail="Tag already exists")

    db.add(Tag(name=tag_name))
    db.commit()
    return {"status": "success", "name": tag_name}

@app.put("/api/tags/{tag_name}")
def rename_tag(tag_name: str, payload: TagRename, db: Session = Depends(get_db)):
    current_name = tag_name.strip()
    new_name = payload.new_name.strip()

    if not current_name or not new_name:
        raise HTTPException(status_code=400, detail="Tag names cannot be empty")

    tag = db.query(Tag).filter(Tag.name == current_name).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    existing_target = next((item for item in db.query(Tag).all() if item.name.lower() == new_name.lower()), None)
    if existing_target and existing_target.name.lower() != current_name.lower():
        raise HTTPException(status_code=409, detail="Target tag already exists")

    db.query(AppTag).filter(AppTag.tag_name == current_name).update({"tag_name": new_name})
    tag.name = new_name
    db.commit()
    return {"status": "success", "old_name": current_name, "new_name": new_name}

@app.delete("/api/tags/{tag_name}")
def delete_tag(tag_name: str, db: Session = Depends(get_db)):
    tag = db.query(Tag).filter(Tag.name == tag_name.strip()).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    db.query(AppTag).filter(AppTag.tag_name == tag.name).delete()
    db.delete(tag)
    db.commit()
    return {"status": "success", "deleted": tag.name}

def normalize_tag_names(tags: List[str]) -> List[str]:
    normalized = []
    seen = set()
    for raw_tag in tags:
        tag = raw_tag.strip()
        if not tag:
            continue
        tag_key = tag.lower()
        if tag_key in seen:
            continue
        seen.add(tag_key)
        normalized.append(tag)
    return normalized

def ensure_tags_exist(db: Session, tags: List[str]):
    existing_names = {
        row[0].lower()
        for row in db.query(Tag.name).all()
    }
    for tag in tags:
        if tag.lower() not in existing_names:
            db.add(Tag(name=tag))
            existing_names.add(tag.lower())

def sync_tags_from_assignments(db: Session):
    assigned_tags = [row[0] for row in db.query(AppTag.tag_name).distinct().all() if row[0]]
    if not assigned_tags:
        return
    ensure_tags_exist(db, assigned_tags)

@app.get("/api/settings")
def get_settings():
    return load_config()

@app.post("/api/settings")
def update_settings(settings: SettingsModel):
    config = load_config()
    config.update(settings.model_dump())
    safe_reset_images_path(get_images_path(config))
    success = save_config(config)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save settings")
    return {"message": "Settings updated successfully"}

@app.post("/api/reset")
def reset_all_data(db: Session = Depends(get_db)):
    try:
        cfg = load_config()
        images_path = safe_reset_images_path(get_images_path(cfg))

        # Delete all activities from database
        db.query(Activity).delete()
        db.query(AppTag).delete()
        db.query(Tag).delete()
        db.commit()
        
        # Delete images
        if images_path.is_dir():
            shutil.rmtree(images_path, ignore_errors=True)
            images_path.mkdir(parents=True, exist_ok=True)
            
        # Delete icons
        icons_path = BASE_DIR / "icons"
        if icons_path.is_dir():
            shutil.rmtree(icons_path, ignore_errors=True)
            icons_path.mkdir(parents=True, exist_ok=True)
            
        return {"message": "All data and images have been deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/image/{activity_id}")
def get_activity_image(activity_id: int, db: Session = Depends(get_db)):
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    image_path = resolve_stored_path(activity.image_path) if activity and activity.image_path else None
    if not image_path or not image_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_path)

@app.get("/api/icon/{activity_id}")
def get_activity_icon(activity_id: int, db: Session = Depends(get_db)):
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    icon_path = resolve_stored_path(activity.icon_path) if activity and activity.icon_path else None
    if not icon_path or not icon_path.is_file():
        raise HTTPException(status_code=404, detail="Icon not found")
    return FileResponse(icon_path)

@app.get("/api/stats")
def get_stats(
    range: str = "all",
    db: Session = Depends(get_db)
):
    """Get app usage statistics. range can be: today, 7d, 30d, all"""
    from sqlalchemy import func

    start = period_start(range, STATS_RANGES)
    default_interval = load_config().get("screenshot_interval", 60)
    interval_seconds = func.coalesce(Activity.interval_at_capture, default_interval)

    query = db.query(
        Activity.app_name,
        func.count(Activity.id).label("count"),
        func.sum(interval_seconds).label("total_seconds_sum"),
        func.max(Activity.id).label("last_id") # To get the latest icon
    )

    if start is not None:
        query = query.filter(Activity.timestamp >= start)
    
    results = query.filter(Activity.app_name != None, Activity.app_name != "", Activity.app_name != "System Idle").group_by(Activity.app_name).all()
    
    stats = []
    for app_name, count, total_seconds_sum, last_id in results:
        total_seconds = total_seconds_sum or 0
        stats.append({
            "app_name": app_name,
            "count": count,
            "total_seconds": total_seconds,
            "icon_url": f"/api/icon/{last_id}"
        })
    
    # Sort by total_seconds descending
    stats.sort(key=lambda x: x["total_seconds"], reverse=True)
    
    # Calculate System Summaries
    summary_query = db.query(
        func.sum(interval_seconds).label("total_seconds_sum"),
        Activity.is_idle,
        func.count(Activity.id).label("count")
    )
    if start is not None:
        summary_query = summary_query.filter(Activity.timestamp >= start)
        
    summary_results = summary_query.group_by(Activity.is_idle).all()
    
    total_active = 0
    total_idle = 0
    total_captures = 0
    
    for total_sec, is_idle, cnt in summary_results:
        sec = total_sec or 0
        total_captures += cnt
        if is_idle:
            total_idle += sec
        else:
            total_active += sec
    
    return {
        "apps": stats,
        "summary": {
            "total_active_seconds": total_active,
            "total_idle_seconds": total_idle,
            "total_captures": total_captures
        }
    }

@app.get("/api/stats/usage-over-time")
def get_usage_over_time(
    range: str = "today",
    db: Session = Depends(get_db)
):
    """Get activity counts over time for charting."""
    from sqlalchemy import func

    start = period_start(range, STATS_RANGES)
    now = datetime.datetime.now(datetime.timezone.utc)
    if range == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        # Group by hour
        strftime_format = "%Y-%m-%d %H:00:00"
    elif range == "all":
        # Keep the all-time chart readable as the database grows.
        strftime_format = "%Y-%m"
    else:
        # Group by day
        strftime_format = "%Y-%m-%d"

    default_interval = load_config().get("screenshot_interval", 60)
    interval_seconds = func.coalesce(Activity.interval_at_capture, default_interval)
    query = db.query(
        func.strftime(strftime_format, Activity.timestamp).label("time_bucket"),
        Activity.is_idle,
        func.sum(interval_seconds).label("seconds")
    )
    if start is not None:
        query = query.filter(Activity.timestamp >= start)
    query = query.group_by("time_bucket", Activity.is_idle).order_by("time_bucket")
    
    results = query.all()
    
    buckets = {}
    for r in results:
        t_bucket = r[0]
        is_idle = r[1]
        seconds = r[2] or 0
        
        if t_bucket not in buckets:
            buckets[t_bucket] = {
                "time": t_bucket,
                "active_seconds": 0,
                "idle_seconds": 0
            }
        if is_idle:
            buckets[t_bucket]["idle_seconds"] += seconds
        else:
            buckets[t_bucket]["active_seconds"] += seconds
        
    # Sort the dictionary values by time
    sorted_buckets = sorted(buckets.values(), key=lambda x: x["time"])
    return sorted_buckets

@app.get("/api/apps/tags")
def get_apps_tags(db: Session = Depends(get_db)):
    """Get all assigned tags for applications."""
    tags = db.query(AppTag).all()
    # group by app_name
    result = {}
    for t in tags:
        if t.app_name not in result:
            result[t.app_name] = []
        result[t.app_name].append(t.tag_name)
    return result

@app.post("/api/apps/tags")
def update_app_tags(payload: AppTagUpdate, db: Session = Depends(get_db)):
    """Update tags for an application."""
    app_name = payload.app_name.strip()
    if not app_name:
        raise HTTPException(status_code=400, detail="App name cannot be empty")

    tags = normalize_tag_names(payload.tags)

    # Delete existing tags for this app
    db.query(AppTag).filter(AppTag.app_name == app_name).delete()

    ensure_tags_exist(db, tags)

    # Add new tags
    for tag in tags:
        new_tag = AppTag(app_name=app_name, tag_name=tag)
        db.add(new_tag)

    db.commit()
    return {"status": "success", "app_name": app_name, "tags": tags}

@app.get("/api/stats/tags")
def get_tag_stats(
    range: str = "all",
    db: Session = Depends(get_db)
):
    from sqlalchemy import func

    start = period_start(range, STATS_RANGES)
    default_interval = load_config().get("screenshot_interval", 60)
    interval_seconds = func.coalesce(Activity.interval_at_capture, default_interval)

    # Join Activity with AppTag
    query = db.query(
        AppTag.tag_name,
        func.count(Activity.id).label("count"),
        func.sum(interval_seconds).label("total_seconds_sum")
    ).join(AppTag, Activity.app_name == AppTag.app_name).filter(Activity.is_idle.is_(False))

    if start is not None:
        query = query.filter(Activity.timestamp >= start)
    
    results = query.group_by(AppTag.tag_name).all()
    
    stats = []
    for tag_name, count, total_seconds_sum in results:
        total_seconds = total_seconds_sum or 0
        app_count = db.query(AppTag.app_name).filter(AppTag.tag_name == tag_name).distinct().count()
        stats.append({
            "tag_name": tag_name,
            "total_seconds": total_seconds,
            "app_count": app_count
        })
    
    stats.sort(key=lambda x: x["total_seconds"], reverse=True)
    return stats

# Serve index.html at root
@app.get("/")
def read_index():
    index_path = STATIC_DIR / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)
    return {"message": "index.html not found in static folder."}
