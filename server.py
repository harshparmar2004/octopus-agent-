import os
import uuid
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import settings, ChannelProfile
from pipeline import ReelsAutomationPipeline
from publisher.octopus_fanout import OctopusFanoutEngine
from publisher.meta_graph_api import MetaReelsPublisher
from bot.octopus_telegram_bot import OctopusTelegramBot
from scrapers.instagram_harvester import InstagramHarvester
from scrapers.content_harvester import ContentHarvester
from processors.ai_enricher import AIEnricher
from processors.llm_manager import LLMManager
from renderers.video_compositor import VideoCompositor
from renderers.niche_templates import (
    list_all_templates,
    get_template_by_id,
    get_template_for_niche,
    register_custom_template,
    NicheTemplate
)
from storage.db import get_niche_template, set_niche_template
from storage.db import (
    init_octopus_db,
    get_all_reels,
    get_reel,
    get_all_accounts,
    get_account_by_id,
    add_or_update_account,
    delete_account,
    get_recent_broadcast_activity,
    get_monitored_sources,
    add_monitored_source,
    delete_monitored_source,
    update_source_last_scraped,
    insert_or_update_reel,
    get_network_stats,
    create_or_update_niche,
    get_all_niches,
    get_niche_by_id,
    delete_niche,
    get_niche_cluster,
    save_niche_automation_config,
    bulk_add_accounts_to_niche,
    bulk_add_sources_to_niche
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OctopusServer")

from fastapi.middleware.cors import CORSMiddleware

init_octopus_db()
app = FastAPI(title="Octopus Agent: Enterprise Multi-Account Reels Engine", version="3.0.0")

# Enable Cross-Origin Resource Sharing (CORS) for Vercel and remote web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount output and assets folders to stream generated videos and logos
app.mount("/output", StaticFiles(directory=str(settings.OUTPUT_DIR)), name="output")
app.mount("/assets", StaticFiles(directory=str(settings.ASSETS_DIR)), name="assets")

fanout_engine = OctopusFanoutEngine()
telegram_bot = OctopusTelegramBot()
telegram_bot.start_background()

TEMPLATE_PATH = settings.BASE_DIR / "templates" / "index.html"

# Request schemas
class IngestRequest(BaseModel):
    url: str
    channel: str = "quantum"
    target_account_ids: Optional[List[str]] = None
    auto_broadcast: bool = False
    dry_run: bool = True

class AccountRequest(BaseModel):
    id: str
    handle: str
    display_name: str
    niche: str
    ig_user_id: Optional[str] = ""
    access_token: Optional[str] = ""
    avatar_initials: Optional[str] = "OC"
    brand_color: Optional[str] = "#f97316"
    profile_pic_url: Optional[str] = None
    is_active: Optional[int] = 1

class BulkAccountsRequest(BaseModel):
    accounts: List[AccountRequest]

class SourceRequest(BaseModel):
    source_type: str
    source_value: str
    category: str = "quantum"
    target_account_id: Optional[str] = None
    auto_publish: Optional[int] = 1

class BroadcastRequest(BaseModel):
    account_ids: Optional[List[str]] = None
    dry_run: bool = True

class InstagramScrapeRequest(BaseModel):
    handle: str
    category: str = "quantum"
    target_account_id: Optional[str] = None
    auto_publish: bool = True
    dry_run: bool = True

class MetaTokenRequest(BaseModel):
    access_token: str

class NicheRequest(BaseModel):
    id: str
    name: str
    description: Optional[str] = ""
    brand_color: Optional[str] = "#ea580c"
    avatar_icon: Optional[str] = "💡"
    default_hashtags: Optional[str] = ""
    cta_text: Optional[str] = ""

class BulkNicheAccountsRequest(BaseModel):
    accounts: List[Dict[str, Any]]

class BulkNicheSourcesRequest(BaseModel):
    sources: List[str]


class TelegramPingRequest(BaseModel):
    chat_id: Optional[str] = None

class TelegramConfigRequest(BaseModel):
    bot_token: str
    chat_id: str

class TelegramDispatchStepRequest(BaseModel):
    step: str
    url: Optional[str] = None
    session_id: Optional[str] = None
    niche_id: Optional[str] = None
    target: Optional[str] = "all"
    chat_id: Optional[str] = None

class PodAutomationConfigRequest(BaseModel):
    source_mode: Optional[str] = "all_sources"
    selected_source: Optional[str] = None
    direct_url: Optional[str] = None
    ai_caption_mode: Optional[str] = "smart_adapt"
    cta_template: Optional[str] = "Follow @{destination_account} for more daily insights!"
    hook_style: Optional[str] = "curiosity"
    custom_headline: Optional[str] = None
    auto_hashtags: Optional[bool] = True
    custom_hashtags: Optional[str] = None
    include_attribution: Optional[bool] = True
    verified_badge: Optional[bool] = True
    video_ratio: Optional[str] = "auto"
    branding_template: Optional[str] = "dynamic"

class RunNicheRequest(BaseModel):
    source_handle: Optional[str] = None
    direct_url: Optional[str] = None
    source_mode: Optional[str] = "all_sources"
    custom_headline: Optional[str] = None
    cta_template: Optional[str] = None
    ai_caption_mode: Optional[str] = "smart_adapt"
    hook_style: Optional[str] = "curiosity"
    dry_run: bool = True

class LLMConfigRequest(BaseModel):
    provider: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: Optional[float] = 0.7
    system_persona: Optional[str] = "viral_curiosity"

class LLMTestRequest(BaseModel):
    provider: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None

class PipelineRunRequest(BaseModel):
    source_handle: Optional[str] = "@dailyfacts"
    niche_id: Optional[str] = "information"
    provider: Optional[str] = None
    model: Optional[str] = None
    dry_run: Optional[bool] = True
    aspect_mode: Optional[str] = "pillarbox"
    voice_tone: Optional[str] = "curiosity"

class PipelineUpdateStepRequest(BaseModel):
    headline: Optional[str] = None
    caption_paragraphs: Optional[List[str]] = None
    credit: Optional[str] = None
    hashtags: Optional[List[str]] = None
    aspect_mode: Optional[str] = None
    source_handle: Optional[str] = None

class PipelineRegenerateRequest(BaseModel):
    source_handle: Optional[str] = "@dailyfacts"
    topic: Optional[str] = "Curiosity & Science"
    voice_tone: Optional[str] = "curiosity"
    niche: Optional[str] = "information"
    niche_id: Optional[str] = "information"

# API Endpoints
@app.get("/api/niches")
def list_niches():
    return get_all_niches()

@app.post("/api/niches")
def create_niche(req: NicheRequest):
    create_or_update_niche(req.dict())
    return {"status": "success", "message": f"Saved niche {req.name}"}

@app.delete("/api/niches/{niche_id}")
def remove_niche(niche_id: str):
    delete_niche(niche_id)
    return {"status": "success"}

@app.get("/api/niches/{niche_id}/cluster")
def get_cluster(niche_id: str):
    return get_niche_cluster(niche_id)

@app.post("/api/niches/{niche_id}/accounts/bulk")
def bulk_add_niche_accounts(niche_id: str, req: BulkNicheAccountsRequest):
    count = bulk_add_accounts_to_niche(niche_id, req.accounts)
    return {"status": "success", "count": count, "message": f"Added {count} accounts to niche {niche_id}"}

@app.post("/api/niches/{niche_id}/sources/bulk")
def bulk_add_niche_sources(niche_id: str, req: BulkNicheSourcesRequest):
    count = bulk_add_sources_to_niche(niche_id, req.sources)
    return {"status": "success", "count": count, "message": f"Added {count} sources to niche {niche_id}"}

@app.post("/api/niches/{niche_id}/automation-config")
def update_niche_automation_config(niche_id: str, req: PodAutomationConfigRequest):
    saved_cfg = save_niche_automation_config(niche_id, req.dict())
    return {
        "status": "success",
        "message": f"Saved automation setup for niche [{niche_id}] successfully!",
        "automation_config": saved_cfg
    }

@app.post("/api/niches/{niche_id}/run")
def run_niche_pipeline(niche_id: str, req: RunNicheRequest, background_tasks: BackgroundTasks):
    cluster = get_niche_cluster(niche_id)
    sources = cluster.get("sources", [])
    if not sources and not req.source_handle and not req.direct_url:
        raise HTTPException(status_code=400, detail="No source handles or direct URL configured for this niche.")

    target_source = req.source_handle or (sources[0]["source_value"] if sources else None)

    def worker():
        fanout_engine.broadcast_source_reel_to_niche_pages(
            source_handle=target_source,
            niche_id=niche_id,
            dry_run=req.dry_run,
            source_mode=req.source_mode or "all_sources",
            direct_url=req.direct_url,
            custom_headline=req.custom_headline,
            cta_template=req.cta_template,
            ai_caption_mode=req.ai_caption_mode or "smart_adapt",
            hook_style=req.hook_style or "curiosity"
        )

    background_tasks.add_task(worker)
    mode_text = "direct URL" if req.direct_url else (f"all {len(sources)} niche sources" if req.source_mode == "all_sources" else f"source @{target_source}")
    return {
        "status": "queued",
        "message": f"Started 1-to-All pipeline for [{niche_id}]: ingesting via {mode_text} and broadcasting to {cluster['total_accounts']} destination pages!"
    }
@app.get("/api/stats")
def get_stats():
    return get_network_stats()

@app.get("/api/accounts")
def list_accounts(niche: Optional[str] = None, search: Optional[str] = None):
    accounts = get_all_accounts(active_only=False)
    if niche and niche != "all":
        accounts = [a for a in accounts if a["niche"].lower() == niche.lower() or niche.lower() in a["niche"].lower()]
    if search:
        s = search.lower()
        accounts = [a for a in accounts if s in a["handle"].lower() or s in a["display_name"].lower()]
    return accounts

@app.post("/api/accounts")
def create_account(acc: AccountRequest):
    add_or_update_account(acc.dict())
    return {"status": "success", "message": f"Saved account {acc.handle}"}

@app.post("/api/accounts/bulk-add")
def bulk_create_accounts(req: BulkAccountsRequest):
    count = 0
    for acc in req.accounts:
        add_or_update_account(acc.dict())
        count += 1
    return {"status": "success", "count": count, "message": f"Successfully imported {count} accounts."}

@app.delete("/api/accounts/{account_id}")
def remove_account(account_id: str):
    delete_account(account_id)
    return {"status": "success"}

@app.get("/api/reels")
def list_reels():
    return get_all_reels()

@app.get("/api/broadcasts")
def list_broadcasts():
    return get_recent_broadcast_activity()

@app.get("/api/sources")
def list_sources():
    return get_monitored_sources()

@app.post("/api/sources")
def create_source(req: SourceRequest):
    add_monitored_source(
        req.source_type,
        req.source_value,
        req.category,
        target_account_id=req.target_account_id or req.category,
        auto_publish=req.auto_publish or 1
    )
    return {"status": "success"}

@app.delete("/api/sources/{source_id}")
def remove_source(source_id: int):
    delete_monitored_source(source_id)
    return {"status": "success"}

@app.get("/api/suggestions/handles")
def get_handle_suggestions(niche: Optional[str] = None):
    return InstagramHarvester().get_recommended_handles(niche)

@app.post("/api/meta/discover")
def discover_meta_pages(req: MetaTokenRequest):
    discovered = MetaReelsPublisher.discover_instagram_accounts(req.access_token)
    return {"discovered": discovered, "count": len(discovered)}

@app.post("/api/meta/test-connection")
def test_meta_connection(req: MetaTokenRequest):
    return MetaReelsPublisher.test_token_validity(req.access_token)

@app.post("/api/telegram/test")
def test_telegram():
    if not telegram_bot.is_configured():
        return {"success": False, "message": "Telegram Bot Token or Chat ID not configured in settings"}
    telegram_bot.send_text_message("🐙 *Octopus Agent Network Online*\nDashboard connection verified successfully!")
    return {"success": True, "message": "Test notification sent to Telegram chat."}

# ==================== LLM BRAIN & PIPELINE STATE API ====================

@app.get("/api/settings/llm")
def get_llm_settings():
    return LLMManager().get_public_config()

@app.post("/api/settings/llm")
def update_llm_settings(req: LLMConfigRequest):
    data = req.dict(exclude_unset=True)
    if not data.get("api_key"):
        data.pop("api_key", None)
    LLMManager().save_config(data)
    return {"status": "success", "message": f"Updated active LLM Brain to {req.provider.upper()} ({req.model})"}

@app.post("/api/settings/llm/test")
def test_llm_connection(req: LLMTestRequest):
    res = LLMManager().test_connection(
        provider=req.provider,
        model=req.model,
        api_key=req.api_key or "",
        base_url=req.base_url
    )
    return res

latest_pipeline_trace = {
    "active_step": 3,
    "status": "READY",
    "updated_at": "Just now",
    "step1_scrape": {
        "title": "1. Source Scrape",
        "handle": "@dailyfacts",
        "shortcode": "DF_2026_98",
        "source_url": "https://www.instagram.com/reel/DF_2026_98/",
        "author": "dailyfacts",
        "duration": "14.2s",
        "resolution": "1080x1080 (1:1 Square)",
        "file_size": "4.6 MB",
        "raw_video_path": "storage/temp/raw_scraped_clip.mp4",
        "status": "COMPLETED"
    },
    "step2_media": {
        "title": "2. Media Ingest & Aspect Fit",
        "input_aspect_ratio": "1:1 Square",
        "output_format": "1080x1920 (9:16 Vertical Reel)",
        "compositing_mode": "Auto-Fit Aspect Ratio (Center Letterbox + Soft Black Matte)",
        "audio_codec": "AAC Stereo 48kHz (Passthrough)",
        "fps": 30,
        "status": "COMPLETED"
    },
    "step3_llm": {
        "title": "3. LLM Brain Synthesizer",
        "provider": "xAI Grok",
        "model": "grok-2",
        "latency_ms": 218,
        "tokens_used": 142,
        "hook_formula": "Viral Curiosity Hook",
        "headline": "Physicists Just Discovered That Superconductors Can Defy Gravity Under These Exact Conditions.",
        "caption_paragraphs": [
            "When examining extreme subzero states, researchers observed a quantum levitation phenomenon that creates a completely frictionless magnetic barrier.",
            "Under flux pinning conditions, magnetic field lines are locked in place through microscopic superconductor defects, trapping the object in mid-air.",
            "This discovery paves the way for next-generation zero-loss power grids and hyperloop transit systems. Follow @info.daily for daily deep-dive breakdowns!"
        ],
        "credit": "via @dailyfacts / physics archives",
        "hashtags": "#information #quantum #physicsfacts #science #deepknowledge #curiosity",
        "status": "COMPLETED"
    },
    "step4_compositor": {
        "title": "4. 9:16 Video Compositor",
        "canvas_size": "1080x1920",
        "branding_mode": "Dynamic Logo Per Destination Page",
        "logo_badge": "/assets/logos/logo_info_01.png",
        "verified_badge": True,
        "rendered_filename": "sample_quantum_reel.mp4",
        "rendered_url": "/output/sample_quantum_reel.mp4",
        "status": "COMPLETED"
    },
    "step5_fanout": {
        "title": "5. Multi-Tentacle Fanout",
        "niche_id": "information",
        "total_pages": 10,
        "mode": "Simulated Dry-Run / Meta API Ready",
        "status": "COMPLETED",
        "destinations": [
            {"handle": "@info.daily", "logo": "/assets/logos/logo_info_01.png", "status": "PUBLISHED", "hash": "0x981F4B"},
            {"handle": "@curious.minds", "logo": "/assets/logos/logo_info_02.png", "status": "PUBLISHED", "hash": "0x442E8A"},
            {"handle": "@daily.knowledge", "logo": "/assets/logos/logo_info_03.png", "status": "PUBLISHED", "hash": "0x19A7BC"},
            {"handle": "@deep.facts", "logo": "/assets/logos/logo_info_04.png", "status": "PUBLISHED", "hash": "0x38F01D"},
            {"handle": "@mind.uncovered", "logo": "/assets/logos/logo_info_05.png", "status": "PUBLISHED", "hash": "0x7C924E"},
            {"handle": "@quick.intel", "logo": "/assets/logos/logo_info_06.png", "status": "PUBLISHED", "hash": "0x2B8D3F"},
            {"handle": "@world.infotainment", "logo": "/assets/logos/logo_info_07.png", "status": "PUBLISHED", "hash": "0x6A19E5"},
            {"handle": "@insight.pulse", "logo": "/assets/logos/logo_info_08.png", "status": "PUBLISHED", "hash": "0x8D3C41"},
            {"handle": "@curiosity.stream", "logo": "/assets/logos/logo_info_09.png", "status": "PUBLISHED", "hash": "0x5E0922"},
            {"handle": "@facts.nexus", "logo": "/assets/logos/logo_info_10.png", "status": "PUBLISHED", "hash": "0x9F418A"}
        ]
    }
}


@app.get("/api/templates")
def get_templates():
    return list_all_templates()

@app.get("/api/templates/{template_id}")
def get_template(template_id: str):
    t = get_template_by_id(template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return t.model_dump()

@app.post("/api/templates")
def create_template(tpl: NicheTemplate):
    register_custom_template(tpl)
    return {"status": "success", "template": tpl.model_dump()}

@app.post("/api/niches/{niche_id}/template")
def assign_niche_template(niche_id: str, payload: Dict[str, str]):
    template_id = payload.get("template_id")
    if not template_id:
        raise HTTPException(status_code=400, detail="template_id required")
    set_niche_template(niche_id, template_id)
    return {"status": "success", "niche_id": niche_id, "template_id": template_id}

@app.get("/api/pipeline/state")
def get_pipeline_state():
    mgr = LLMManager()
    cfg = mgr.get_public_config()
    latest_pipeline_trace["step3_llm"]["provider"] = cfg.get("provider", "gemini").upper()
    latest_pipeline_trace["step3_llm"]["model"] = cfg.get("model", "gemini-1.5-flash")
    if mgr.last_execution_trace:
        t = mgr.last_execution_trace
        latest_pipeline_trace["step3_llm"]["headline"] = t.get("hook_text", latest_pipeline_trace["step3_llm"]["headline"])
        latest_pipeline_trace["step3_llm"]["caption_paragraphs"] = t.get("caption_paragraphs", latest_pipeline_trace["step3_llm"]["caption_paragraphs"])
        latest_pipeline_trace["step3_llm"]["credit"] = t.get("credit", latest_pipeline_trace["step3_llm"]["credit"])
        latest_pipeline_trace["step3_llm"]["hashtags"] = t.get("hashtags", latest_pipeline_trace["step3_llm"]["hashtags"])
        latest_pipeline_trace["step3_llm"]["latency_ms"] = t.get("latency_ms", 185)
        latest_pipeline_trace["step3_llm"]["tokens_used"] = t.get("tokens_used", 140)
    return latest_pipeline_trace

@app.post("/api/pipeline/run")
def run_pipeline(req: PipelineRunRequest):
    handle = req.source_handle or "@dailyfacts"
    niche_id = req.niche_id or "information"
    
    # 1. Update Step 1 (Source)
    clean_handle = handle.lstrip("@")
    shortcode = f"{clean_handle[:3].upper()}_{uuid.uuid4().hex[:6].upper()}"
    latest_pipeline_trace["step1_scrape"]["handle"] = f"@{clean_handle}"
    latest_pipeline_trace["step1_scrape"]["shortcode"] = shortcode
    latest_pipeline_trace["step1_scrape"]["status"] = "COMPLETED"
    
    # 2. Update Step 2 (Aspect & Audio)
    latest_pipeline_trace["step2_media"]["fit_mode"] = req.aspect_mode or "pillarbox"
    
    # 3. Step 3 (LLM Brain)
    mgr = LLMManager()
    cfg = mgr.get_public_config()
    latest_pipeline_trace["step3_llm"]["provider"] = (req.provider or cfg.get("provider", "gemini")).upper()
    latest_pipeline_trace["step3_llm"]["model"] = req.model or cfg.get("model", "gemini-1.5-flash")
    
    # 4. Step 5 (Fanout Destination Accounts)
    cluster = get_niche_cluster(niche_id)
    if cluster and cluster.get("accounts"):
        latest_pipeline_trace["step5_fanout"]["accounts_dispatched"] = len(cluster["accounts"])
        fanout_list = []
        for acct in cluster["accounts"]:
            fanout_list.append({
                "handle": f"@{acct['handle']}" if not acct['handle'].startswith('@') else acct['handle'],
                "logo": acct.get("profile_pic_url") or f"/assets/logos/logo_{niche_id[:4]}_{acct['id'][-2:]}.png",
                "status": "SIMULATED" if req.dry_run else "PUBLISHED",
                "hash": f"0x{uuid.uuid4().hex[:6].upper()}"
            })
        latest_pipeline_trace["step5_fanout"]["destinations"] = fanout_list
    
    return {
        "success": True,
        "message": f"Pipeline pass executed for {handle} ➔ [{niche_id}] ({latest_pipeline_trace['step5_fanout']['accounts_dispatched']} pages)!",
        "state": latest_pipeline_trace
    }

@app.post("/api/pipeline/update-step")
def update_pipeline_step(req: PipelineUpdateStepRequest):
    if req.source_handle:
        latest_pipeline_trace["step1_scrape"]["handle"] = req.source_handle
    if req.aspect_mode:
        latest_pipeline_trace["step2_media"]["fit_mode"] = req.aspect_mode
    if req.headline:
        latest_pipeline_trace["step3_llm"]["headline"] = req.headline
    if req.caption_paragraphs:
        latest_pipeline_trace["step3_llm"]["caption_paragraphs"] = req.caption_paragraphs
    if req.credit:
        latest_pipeline_trace["step3_llm"]["credit"] = req.credit
    if req.hashtags:
        latest_pipeline_trace["step3_llm"]["hashtags"] = req.hashtags
    return {
        "success": True,
        "message": "Pipeline parameters updated successfully!",
        "state": latest_pipeline_trace
    }

@app.post("/api/pipeline/regenerate-copy")
def regenerate_pipeline_copy(req: PipelineRegenerateRequest):
    handle = req.source_handle or "@dailyfacts"
    topic = req.topic or "Educational Viral Reel"
    mgr = LLMManager()
    
    niche_target = req.niche_id or req.niche or "information"
    hook_data = mgr.synthesize_reel(
        title=f"Viral demonstration reel from {handle}",
        description=f"Demonstration illustrating {topic}",
        niche=niche_target,
        channel_handle=handle,
        formula="curiosity"
    )
    
    latest_pipeline_trace["step3_llm"]["headline"] = hook_data.get("hook_text", latest_pipeline_trace["step3_llm"]["headline"])
    latest_pipeline_trace["step3_llm"]["caption_paragraphs"] = hook_data.get("caption_paragraphs", latest_pipeline_trace["step3_llm"]["caption_paragraphs"])
    latest_pipeline_trace["step3_llm"]["credit"] = hook_data.get("credit", latest_pipeline_trace["step3_llm"]["credit"])
    latest_pipeline_trace["step3_llm"]["hashtags"] = hook_data.get("hashtags", latest_pipeline_trace["step3_llm"]["hashtags"])
    latest_pipeline_trace["step3_llm"]["latency_ms"] = hook_data.get("latency_ms", 210)
    latest_pipeline_trace["step3_llm"]["tokens_used"] = hook_data.get("tokens_used", 155)
    
    return {
        "success": True,
        "message": "LLM Brain successfully synthesized new viral hook & 3-paragraph caption!",
        "headline": latest_pipeline_trace["step3_llm"]["headline"],
        "caption_paragraphs": latest_pipeline_trace["step3_llm"]["caption_paragraphs"],
        "state": latest_pipeline_trace
    }

@app.post("/api/instagram/scrape-now")
def scrape_instagram_now(req: InstagramScrapeRequest, background_tasks: BackgroundTasks):
    def worker():
        harvester = InstagramHarvester()
        enricher = AIEnricher()
        compositor = VideoCompositor()
        
        reel = harvester.get_latest_reel_from_handle(req.handle)
        if not reel:
            logger.warning(f"Could not discover latest reel for @{req.handle}")
            return
            
        task_id = f"ig_{req.handle.lstrip('@').replace('.', '_')}_{str(uuid.uuid4())[:6]}"
        dl = harvester.download_reel(reel["permalink"], task_id)
        if not dl or not dl.get("filepath"):
            dl = ContentHarvester().download_video(reel["permalink"], task_id)
            
        if dl and dl.get("filepath"):
            target_acc = get_account_by_id(req.target_account_id or req.category)
            if not target_acc:
                all_accs = get_all_accounts(active_only=True)
                target_acc = all_accs[0] if all_accs else None
                
            ch = ChannelProfile(
                handle=target_acc["handle"],
                display_name=target_acc["display_name"],
                niche=target_acc["niche"],
                logo_filename=f"logo_{target_acc['id']}.png",
                subreddits=[], default_hashtags=[], cta_link="bit.ly/free-ai-newsletter"
            )
            enriched = enricher.generate_hook_and_caption(dl.get("title", ""), dl.get("description", ""), ch)
            rendered = compositor.build_reel(
                raw_video_path=dl["filepath"],
                hook_text=enriched["hook_text"],
                channel=ch,
                output_filename=f"{task_id}_{target_acc['id']}.mp4",
                credit_handle=req.handle
            )
            if rendered:
                insert_or_update_reel({
                    "id": task_id,
                    "source_url": reel["permalink"],
                    "original_title": dl.get("title"),
                    "hook_text": enriched["hook_text"],
                    "caption": f"{enriched['full_caption']}\n\nSource: @{req.handle.lstrip('@')}",
                    "raw_video_path": dl["filepath"],
                    "rendered_video_path": rendered,
                    "rendered_filename": f"{task_id}_{target_acc['id']}.mp4",
                    "status": "READY_FOR_PUBLISH"
                })
                if telegram_bot.is_configured():
                    telegram_bot.send_broadcast_preview(
                        video_path=rendered,
                        hook_text=f"Scraped from @{req.handle}: {enriched['hook_text']}",
                        reel_id=task_id,
                        accounts=get_all_accounts(active_only=True)
                    )

    background_tasks.add_task(worker)
    return {"status": "queued", "message": f"Scraping newest reel from @{req.handle} with template logo..."}

@app.post("/api/daemon/cycle")
def run_daemon_cycle(background_tasks: BackgroundTasks):
    from daemon import Octopus24x7Daemon
    daemon = Octopus24x7Daemon()
    background_tasks.add_task(daemon.run_full_cycle, dry_run=True)
    return {"status": "started", "message": "24/7 autonomous monitoring cycle running in background"}

@app.get("/api/swarm/status")
def get_swarm_status():
    from agents.swarm_coordinator import OctopusSwarmCoordinator
    coordinator = OctopusSwarmCoordinator()
    return coordinator.get_swarm_status()

@app.post("/api/swarm/trigger")
def trigger_swarm_cycle(background_tasks: BackgroundTasks):
    from agents.swarm_coordinator import OctopusSwarmCoordinator
    coordinator = OctopusSwarmCoordinator()
    background_tasks.add_task(coordinator.run_swarm_parallel, dry_run=True)
    return {
        "status": "started",
        "message": "Parallel Multi-Agent Swarm cycle initiated across all niches!"
    }

@app.post("/api/ingest")
def ingest_url(req: IngestRequest, background_tasks: BackgroundTasks):
    def worker():
        pipeline = ReelsAutomationPipeline(channel_key=req.channel)
        res = pipeline.process_url(req.url, auto_publish=False, dry_run=req.dry_run)
        if res and req.auto_broadcast:
            fanout_engine.broadcast_to_all_accounts(res["id"], account_ids=req.target_account_ids, dry_run=req.dry_run)
            
        if res and telegram_bot.is_configured():
            accounts = get_all_accounts(active_only=True)
            telegram_bot.send_broadcast_preview(
                video_path=res["rendered_video_path"],
                hook_text=res["hook_text"],
                reel_id=res["id"],
                accounts=accounts
            )

    background_tasks.add_task(worker)
    return {"status": "queued", "message": f"Octopus Agent processing: {req.url}"}

@app.post("/api/broadcast/{reel_id}")
def broadcast_reel(reel_id: str, req: BroadcastRequest):
    res = fanout_engine.broadcast_to_all_accounts(
        reel_id=reel_id,
        account_ids=req.account_ids,
        dry_run=req.dry_run
    )
    return res

# Web UI Dashboard (Beige & Orange Cloud Theme)

# ==================== TELEGRAM REMOTE CONTROL API ====================
@app.get("/api/telegram/status")
def get_telegram_status():
    return telegram_bot.get_status_info()

@app.post("/api/telegram/test_ping")
def test_telegram_ping(req: TelegramPingRequest):
    res = telegram_bot.ping(target_chat_id=req.chat_id)
    return res

@app.post("/api/telegram/save_config")
def save_telegram_config(req: TelegramConfigRequest):
    token = req.bot_token.strip()
    cid = req.chat_id.strip()
    
    settings.TELEGRAM_BOT_TOKEN = token
    settings.TELEGRAM_CHAT_ID = cid
    telegram_bot.bot_token = token
    telegram_bot.chat_id = cid
    telegram_bot.base_url = f"https://api.telegram.org/bot{token}"
    
    # Save/update .env file
    env_path = settings.BASE_DIR / ".env"
    existing_lines = []
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            existing_lines = f.readlines()
            
    updated_token = False
    updated_chat = False
    new_lines = []
    for line in existing_lines:
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            new_lines.append(f"TELEGRAM_BOT_TOKEN={token}\n")
            updated_token = True
        elif line.startswith("TELEGRAM_CHAT_ID="):
            new_lines.append(f"TELEGRAM_CHAT_ID={cid}\n")
            updated_chat = True
        else:
            new_lines.append(line)
            
    if not updated_token:
        new_lines.append(f"TELEGRAM_BOT_TOKEN={token}\n")
    if not updated_chat:
        new_lines.append(f"TELEGRAM_CHAT_ID={cid}\n")
        
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
        
    # Start polling if not already started
    if not telegram_bot.is_running and telegram_bot.is_configured():
        telegram_bot.start_background()
        
    ping_res = telegram_bot.ping()
    return {
        "success": True,
        "message": "Telegram Bot credentials saved & 24/7 background listener activated!",
        "status": telegram_bot.get_status_info(),
        "ping": ping_res
    }

@app.post("/api/telegram/test")
def test_telegram_connection():
    if not telegram_bot.is_configured():
        return {"success": False, "message": "Telegram Bot is not configured yet. Please enter Bot Token and Chat ID."}
    res = telegram_bot.ping()
    if res.get("success"):
        return {"success": True, "message": "✅ Success! Ping message sent and received on your Telegram app."}
    else:
        return {"success": False, "message": f"❌ Could not ping bot: {res.get('error', 'Please check your Bot Token and Chat ID')}"}

@app.post("/api/telegram/dispatch_step")
def dispatch_telegram_step(req: TelegramDispatchStepRequest):
    if req.step == "start":
        return telegram_bot.handle_inbound_url(
            url=req.url or "https://instagram.com/reel/C7x9_science",
            chat_id=req.chat_id
        )
    elif req.step == "select_niche":
        return telegram_bot.handle_niche_selection(
            session_id=req.session_id,
            niche_id=req.niche_id,
            chat_id=req.chat_id
        )
    elif req.step == "execute":
        return telegram_bot.handle_execution(
            session_id=req.session_id,
            niche_id=req.niche_id,
            target=req.target or "all",
            chat_id=req.chat_id
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown step: {req.step}")

@app.get("/api/telegram/logs")
def get_telegram_logs():
    return telegram_bot.dispatch_logs

@app.get("/api/anti-shadowban/preview")
def get_anti_shadowban_preview(niche: str = "information", handle: str = "dailyfacts"):
    from processors.anti_shadowban import AntiShadowbanEngine
    
    clean_niche = niche.lower().strip()
    clean_handle = handle.lstrip("@").strip()
    
    sample_accounts = [
        {"id": "1", "handle": f"@{clean_niche}.daily", "name": f"{clean_niche.title()} Daily"},
        {"id": "2", "handle": f"@{clean_niche}.pulse", "name": f"{clean_niche.title()} Pulse"},
        {"id": "3", "handle": f"@{clean_niche}.nexus", "name": f"{clean_niche.title()} Nexus"},
    ]
    
    base_hook = "Two people can earn the exact same salary and end up living completely different lives"
    base_caption = (
        "Two people can earn the exact same salary and end up living completely different lives.\n\n"
        "The difference is not how much money you earn, but how much you retain. "
        "Furthermore, small daily financial decisions compound exponentially over a decade."
    )
    
    schedule = AntiShadowbanEngine.get_staggered_schedule(len(sample_accounts))
    variations = []
    
    for idx, acc in enumerate(sample_accounts):
        mut_params = AntiShadowbanEngine.get_video_mutation_params(idx)
        mut_caption = AntiShadowbanEngine.mutate_caption(
            base_caption=base_caption,
            hook_headline=base_hook,
            account_handle=acc["handle"],
            niche=clean_niche,
            account_index=idx
        )
        hashtags = AntiShadowbanEngine.generate_niche_hashtags(clean_niche, account_index=idx, count=7)
        
        variations.append({
            "account_index": idx,
            "account_handle": acc["handle"],
            "account_name": acc["name"],
            "caption": mut_caption,
            "hashtags": hashtags,
            "scheduled_offset": schedule[idx]["offset_display"],
            "scheduled_iso": schedule[idx]["scheduled_iso"],
            "video_mutation": {
                "contrast": mut_params["contrast"],
                "brightness": mut_params["brightness"],
                "saturation": mut_params["saturation"],
                "gamma": mut_params["gamma"],
                "crop_offset": mut_params["crop_offset"],
                "device_profile": mut_params["device_profile"]["model"],
                "encoder_tag": mut_params["device_profile"]["encoder"]
            }
        })
        
    return {
        "status": "success",
        "niche": clean_niche,
        "shield_active": True,
        "total_variants_simulated": len(variations),
        "variations": variations
    }


# ==============================================================================
# PEAK-TIME SCHEDULER & CANDIDATE POOL ENDPOINTS
# ==============================================================================
from scheduler.peak_scheduler import get_peak_scheduler
from storage.scheduler_db import (
    get_niche_schedule,
    save_niche_schedule,
    get_candidates,
    update_candidate,
    get_slot_runs,
    get_slot_run,
    utcnow
)
from datetime import timedelta

class NicheScheduleUpdateRequest(BaseModel):
    slot_times: Optional[List[str]] = None
    timezone: Optional[str] = None
    jitter_minutes: Optional[int] = None
    fanout_mode: Optional[str] = None
    approval_mode: Optional[str] = None
    approval_timeout_minutes: Optional[int] = None
    min_score: Optional[float] = None
    evergreen_fallback: Optional[bool] = None
    source_diversity: Optional[bool] = None
    enabled: Optional[bool] = None

class CandidateActionRequest(BaseModel):
    reason: Optional[str] = None

@app.on_event("startup")
def start_scheduler_lifecycle():
    try:
        sched = get_peak_scheduler()
        sched.plan_all()
        if os.getenv("ENABLE_PEAK_SCHEDULER", "true").lower() in ("1", "true", "yes"):
            sched.start()
            logger.info("Peak-Time Scheduler background runner initialized.")
    except Exception as e:
        logger.warning(f"Peak-Time Scheduler background init skipped: {e}")

@app.get("/api/schedule/status")
def get_scheduler_status():
    sched = get_peak_scheduler()
    return {"status": "success", "scheduler": sched.status()}

@app.get("/api/niches/{niche_id}/schedule")
def get_schedule(niche_id: str):
    sched = get_niche_schedule(niche_id)
    return {"status": "success", "schedule": sched}

@app.put("/api/niches/{niche_id}/schedule")
def update_schedule(niche_id: str, req: NicheScheduleUpdateRequest):
    updates = req.dict(exclude_unset=True) if hasattr(req, "dict") else req.model_dump(exclude_unset=True)
    saved = save_niche_schedule(niche_id, updates)
    # Replan slots with the new configuration
    try:
        get_peak_scheduler().plan_niche(niche_id, replan=True)
    except Exception as e:
        logger.warning(f"Error replanning after schedule update: {e}")
    return {"status": "success", "schedule": saved}

@app.get("/api/candidates")
def list_candidates(niche_id: Optional[str] = None, status: Optional[str] = None, limit: int = 50):
    statuses = [s.strip().upper() for s in status.split(",")] if status else None
    target_niche = niche_id or "information"
    cands = get_candidates(target_niche, statuses=statuses, limit=limit)
    return {
        "status": "success",
        "niche_id": target_niche,
        "count": len(cands),
        "candidates": cands
    }

@app.post("/api/candidates/{candidate_id}/pin")
def pin_candidate(candidate_id: int):
    update_candidate(candidate_id, {"pinned": 1})
    return {"status": "success", "candidate_id": candidate_id, "message": "Candidate pinned for next slot."}

@app.post("/api/candidates/{candidate_id}/reject")
def reject_candidate(candidate_id: int, req: Optional[CandidateActionRequest] = None):
    reason = req.reason if req and req.reason else "Manually rejected by operator"
    update_candidate(candidate_id, {"status": "REJECTED", "score_reason": reason, "pinned": 0})
    return {"status": "success", "candidate_id": candidate_id, "message": "Candidate rejected."}

@app.get("/api/schedule/upcoming")
def get_upcoming_schedule(niche_id: Optional[str] = None, hours: int = 24):
    now = utcnow()
    since = now - timedelta(hours=2)
    until = now + timedelta(hours=hours)
    runs = get_slot_runs(since=since, until=until, niche_id=niche_id, limit=200)
    return {
        "status": "success",
        "now_utc": now.isoformat(),
        "count": len(runs),
        "slot_runs": runs
    }

@app.post("/api/schedule/{niche_id}/run-slot-now")
def run_slot_now_endpoint(niche_id: str, dry_run: bool = True):
    run = get_peak_scheduler().run_slot_now(niche_id, dry_run=dry_run, background=True)
    return {
        "status": "success",
        "message": f"Slot initiated for niche [{niche_id}]",
        "slot_run": run
    }

@app.post("/api/harvest/{niche_id}")
def harvest_niche_endpoint(niche_id: str):
    res = get_peak_scheduler().harvest_niche(niche_id)
    return {"status": "success", "harvest": res}

@app.post("/api/schedule/slot/{slot_run_id}/approve")
def approve_slot_endpoint(slot_run_id: int):
    run = get_peak_scheduler().approve_slot(slot_run_id)
    return {"status": "success", "slot_run": run}

@app.post("/api/schedule/slot/{slot_run_id}/swap")
def swap_slot_endpoint(slot_run_id: int):
    run = get_peak_scheduler().swap_slot(slot_run_id)
    return {"status": "success", "slot_run": run}

@app.post("/api/schedule/slot/{slot_run_id}/skip")
def skip_slot_endpoint(slot_run_id: int, req: Optional[CandidateActionRequest] = None):
    reason = req.reason if req and req.reason else "Skipped via API"
    run = get_peak_scheduler().skip_slot(slot_run_id, reason=reason)
    return {"status": "success", "slot_run": run}

@app.get("/", response_class=HTMLResponse)
def dashboard_ui():
    if TEMPLATE_PATH.exists():
        with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Template not found. Please verify templates/index.html</h1>"
