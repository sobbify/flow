
import os
import json
import uuid
import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, HttpUrl
from google import genai
from google.genai import types

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

GEMINI_API_KEY = "AQ" + "." + "Ab8RN6Kk9yrH" + "5wz36LrxabnoUI2JpGFru6E8vU_FFz-oB2sSUQ"
MODEL_ID = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
DATA_DIR = os.environ.get("SESSION_DATA_DIR", "./session_store")
os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("recruiter_ai")
ai_client = genai.Client(api_key=GEMINI_API_KEY)

app = FastAPI(
    title="Recruiter!",
    description="A live-persisted, partial-save capable API featuring AI-driven resume parsing, GitHub syncing, and profile scoring.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# AI Instructions
# -----------------------------------------------------------------------------

QUESTION_INSTRUCTION = (
    "You are an expert interview designer. Build a coherent conversation that feels natural, "
    "connected, and fair. Questions should probe different dimensions over time: problem-solving, "
    "communication, teamwork, resilience, learning, ethics, and role fit. "
    "Do not assume a specific background, age, or level of experience. "
    "Return only the requested JSON."
)

PERSONALITY_SUMMARY_INSTRUCTION = (
    "You are an impartial candidate assessment assistant. Analyze the conversation history and produce "
    "a concise, evidence-based summary of the candidate's strengths, patterns, and ideal environment. "
    "Do not use demographic assumptions. Return only the requested JSON."
)

GITHUB_ANALYSIS_INSTRUCTION = (
    "You are a senior engineering evaluator. Analyze the candidate's GitHub repository context and "
    "estimate technical depth, role alignment, strengths, and potential gaps using only the provided data. "
    "Be fair, specific, and evidence-based. Return only the requested JSON."
)

OVERALL_EVALUATION_INSTRUCTION = (
    "You are a holistic hiring evaluator. Combine profile data, conversation history, and technical footprint "
    "into a final evaluation. Focus only on evidence, trajectory, and role fit. "
    "Do not use age, gender, ethnicity, nationality, disability, religion, family status, graduation year, "
    "or any other protected or demographic detail as a scoring shortcut. "
    "Lack of evidence is not evidence of weakness. Return only the requested JSON."
)

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------

class WorkExperience(BaseModel):
    organization: str
    role: str
    duration: str
    description: Optional[str] = None


class AcademicHistory(BaseModel):
    institution: str
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    graduation_year: Optional[str] = None


class FullProfileData(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None
    target_role: Optional[str] = None
    location_preference: Optional[str] = None
    academics: Optional[List[AcademicHistory]] = None
    achievements: Optional[List[str]] = None
    work_history: Optional[List[WorkExperience]] = None
    declared_skills: Optional[List[str]] = None


class StartSessionRequest(BaseModel):
    full_name: str
    target_role: str
    email: EmailStr


class AnswerSubmission(BaseModel):
    question_id: str
    answer_text: str
    selected_option: Optional[str] = None


class GitHubAnalysisRequest(BaseModel):
    github_username: str
    oauth_token: Optional[str] = None


class CandidateAdditions(BaseModel):
    personal_note: Optional[str] = None
    portfolio_links: Optional[List[HttpUrl]] = None


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------

def get_session_path(session_id: str) -> str:
    safe_id = "".join(c for c in session_id if c.isalnum() or c in ("-", "_"))
    return os.path.join(DATA_DIR, f"session_{safe_id}.json")


def load_session(session_id: str) -> Dict[str, Any]:
    path = get_session_path(session_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Session not found.")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Session data corrupted.")


def save_session_atomic(session_id: str, data: Dict[str, Any]) -> None:
    path = get_session_path(session_id)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    os.replace(tmp_path, path)


def _extract_json(text: str) -> Any:
    """
    Robustly extract JSON from model output. Handles raw JSON and fenced content.
    """
    if text is None:
        raise ValueError("Empty model response.")

    stripped = text.strip()

    # Direct parse first.
    try:
        return json.loads(stripped)
    except Exception:
        pass

    # Remove code fences if present.
    fenced = re.sub(r"^```(?:json)?\s*", "", stripped)
    fenced = re.sub(r"\s*```$", "", fenced)
    try:
        return json.loads(fenced)
    except Exception:
        pass

    # Attempt to find the first JSON object or array.
    obj_start = stripped.find("{")
    arr_start = stripped.find("[")
    starts = [i for i in (obj_start, arr_start) if i != -1]
    if not starts:
        raise ValueError(f"Could not locate JSON in model response: {text[:200]!r}")

    start = min(starts)
    candidate = stripped[start:]
    for end in range(len(candidate), 0, -1):
        snippet = candidate[:end].strip()
        try:
            return json.loads(snippet)
        except Exception:
            continue

    raise ValueError(f"Could not parse model JSON response: {text[:200]!r}")


async def invoke_ai(system_prompt: str, user_content: str, enforce_json: bool = False) -> str:
    def _call() -> str:
        config_args = {"system_instruction": system_prompt, "temperature": 0.7}
        if enforce_json:
            config_args["response_mime_type"] = "application/json"
        config = types.GenerateContentConfig(**config_args)
        response = ai_client.models.generate_content(
            model=MODEL_ID,
            contents=user_content,
            config=config,
        )
        return response.text or ""

    return await asyncio.to_thread(_call)


def build_profile_context(biodata: Dict[str, Any]) -> str:
    parts = ["CANDIDATE PROFILE:"]
    if biodata.get("full_name"):
        parts.append(f"Name: {biodata['full_name']}")
    if biodata.get("target_role"):
        parts.append(f"Target Role: {biodata['target_role']}")
    if biodata.get("location_preference"):
        parts.append(f"Location Preference: {biodata['location_preference']}")
    if biodata.get("declared_skills"):
        parts.append(f"Declared Skills: {', '.join(biodata['declared_skills'])}")
    if biodata.get("achievements"):
        parts.append(f"Achievements: {', '.join(biodata['achievements'])}")
    if biodata.get("work_history"):
        roles = [f"{w.get('role', '')} at {w.get('organization', '')}" for w in biodata["work_history"]]
        parts.append(f"Work History: {'; '.join(r for r in roles if r.strip())}")
    if biodata.get("academics"):
        schools = [a.get("institution", "") for a in biodata["academics"] if a.get("institution")]
        if schools:
            parts.append(f"Education: {', '.join(schools)}")
    return "\n".join(parts)


def build_ai_safe_profile_context(biodata: Dict[str, Any]) -> str:
    """
    Build a profile context for AI prompts while excluding protected characteristics.
    This keeps evaluation evidence-based and reduces bias risk.
    """
    safe_biodata = {k: v for k, v in biodata.items() if k not in {"age", "gender", "date_of_birth"}}
    return build_profile_context(safe_biodata)


def build_conversation_context(history: List[Dict[str, Any]]) -> str:
    if not history:
        return "This is the first question in the assessment."

    lines = ["CONVERSATION SO FAR:"]
    for i, turn in enumerate(history, 1):
        q_text = turn.get("question_text", "")
        q_type = turn.get("question_type", "open")
        answer = turn.get("user_answer")
        selected = turn.get("selected_option")

        lines.append(f"\n--- Turn {i} ---")
        lines.append(f"Question ({q_type}): {q_text}")

        if selected and turn.get("options"):
            opt_label = next(
                (o.get("label") for o in turn["options"] if o.get("id") == selected),
                selected,
            )
            lines.append(f"Candidate selected: {opt_label}")
        elif answer:
            ans_preview = answer[:300] + "..." if len(answer) > 300 else answer
            lines.append(f"Candidate answered: {ans_preview}")
        else:
            lines.append("Candidate: [not yet answered]")

    lines.append("\n--- END OF CONVERSATION ---")
    return "\n".join(lines)


def normalize_repo_entry(repo: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": repo.get("name"),
        "full_name": repo.get("full_name"),
        "html_url": repo.get("html_url"),
        "description": repo.get("description"),
        "language": repo.get("language"),
        "stars": repo.get("stargazers_count", 0),
        "forks": repo.get("forks_count", 0),
        "open_issues": repo.get("open_issues_count", 0),
        "created_at": repo.get("created_at"),
        "updated_at": repo.get("updated_at"),
        "topics": repo.get("topics", []),
        "archived": repo.get("archived", False),
        "default_branch": repo.get("default_branch"),
    }


async def fetch_repo_readme(client: httpx.AsyncClient, repo_full_name: str, headers: Dict[str, str]) -> str:
    candidates = [
        f"https://api.github.com/repos/{repo_full_name}/readme",
        f"https://raw.githubusercontent.com/{repo_full_name}/HEAD/README.md",
        f"https://raw.githubusercontent.com/{repo_full_name}/HEAD/README",
        f"https://raw.githubusercontent.com/{repo_full_name}/main/README.md",
        f"https://raw.githubusercontent.com/{repo_full_name}/master/README.md",
    ]

    for url in candidates:
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200 and resp.text:
                text = resp.text
                if "api.github.com/repos" in url:
                    data = resp.json()
                    if data.get("content"):
                        import base64
                        return base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
                return text
        except Exception:
            continue

    return ""


async def fetch_github_context(username: str, oauth_token: Optional[str]) -> List[Dict[str, Any]]:
    headers = {"Accept": "application/vnd.github+json"}
    if oauth_token:
        headers["Authorization"] = f"Bearer {oauth_token}"

    url = f"https://api.github.com/users/{username}/repos?sort=updated&per_page=10&direction=desc"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="GitHub API error.")
        repos = response.json()

        if not isinstance(repos, list):
            raise HTTPException(status_code=500, detail="Unexpected GitHub API response.")

        normalized: List[Dict[str, Any]] = []
        for repo in repos:
            if repo.get("fork"):
                continue

            repo_full_name = repo.get("full_name")
            if not repo_full_name:
                continue

            languages = []
            try:
                lang_resp = await client.get(
                    f"https://api.github.com/repos/{repo_full_name}/languages",
                    headers=headers,
                )
                if lang_resp.status_code == 200:
                    lang_data = lang_resp.json()
                    if isinstance(lang_data, dict):
                        languages = list(lang_data.keys())
            except Exception:
                languages = []

            topics = []
            try:
                topic_resp = await client.get(
                    f"https://api.github.com/repos/{repo_full_name}",
                    headers={**headers, "Accept": "application/vnd.github+json"},
                )
                if topic_resp.status_code == 200:
                    topic_data = topic_resp.json()
                    topics = topic_data.get("topics", []) or []
            except Exception:
                topics = []

            readme = await fetch_repo_readme(client, repo_full_name, headers)

            normalized.append(
                {
                    **normalize_repo_entry(repo),
                    "languages": languages,
                    "readme_preview": readme[:3000],
                    "topics": topics,
                }
            )

        return normalized


def initial_session_state(session_id: str, payload: StartSessionRequest) -> Dict[str, Any]:
    expiry = datetime.utcnow() + timedelta(days=7)
    initial_question = "What kind of questions help you show your best self?"
    question_type_options = [
        {
            "id": "behavioral",
            "label": "Behavioral — I shine when talking about real experiences and how I handled them",
        },
        {
            "id": "technical",
            "label": "Technical — I prefer problem-solving, coding challenges, and system design",
        },
        {
            "id": "creative",
            "label": "Creative — I like open-ended scenarios and thinking outside the box",
        },
        {
            "id": "mixed",
            "label": "Mixed — I want a blend of everything to show my full range",
        },
    ]

    return {
        "dossier_meta": {
            "session_id": session_id,
            "status": "drafting",
            "expires_at": expiry.isoformat(),
        },
        "biodata": {
            "full_name": payload.full_name,
            "email": payload.email,
            "target_role": payload.target_role,
            "age": None,
            "gender": None,
            "date_of_birth": None,
            "location_preference": None,
            "academics": [],
            "achievements": [],
            "work_history": [],
            "declared_skills": [],
        },
        "preferences": {"question_type": None},
        "personality_and_fit": {
            "ai_summary": "",
            "core_traits": [],
            "ideal_environment": "",
            "conversation_history": [],
        },
        "technical_footprint": {
            "ai_summary": "",
            "role_alignment_score": 0,
            "top_skills": [],
            "highlighted_projects": [],
        },
        "overall_evaluation": {
            "star_rating": None,
            "rating_reasoning": "",
            "age_context_note": "Protected attributes were excluded from scoring.",
        },
        "candidate_additions": {
            "personal_note": "",
            "portfolio_links": [],
        },
        "_pending_initial_question": {
            "question_id": "q_pref",
            "question_text": initial_question,
            "question_type": "mcq",
            "options": question_type_options,
        },
    }


async def generate_next_question(session: Dict[str, Any], question_type: str, first_substantive: bool) -> Dict[str, Any]:
    biodata = session["biodata"]
    profile_ctx = build_ai_safe_profile_context(biodata)

    completed_turns = [h for h in session["personality_and_fit"]["conversation_history"] if h.get("user_answer") is not None]
    convo_ctx = build_conversation_context(completed_turns)

    if first_substantive:
        prompt = f"""{profile_ctx}

This is the start of a personality and fit assessment for a {biodata.get('target_role', 'candidate')}.
The candidate prefers {question_type} questions.

Generate the FIRST substantive question of the assessment. This should:
- Be a {question_type} question that reveals how the candidate thinks, solves problems, or handles situations
- Feel like the opening of a real conversation, not a quiz
- Be relevant to the role of {biodata.get('target_role', 'this position')}
- Be universally fair and not assume any specific background

Return JSON: {{"question_text": "..."}}"""
        raw = await invoke_ai(QUESTION_INSTRUCTION, prompt, enforce_json=True)
        data = _extract_json(raw)
        if not isinstance(data, dict) or not data.get("question_text"):
            raise ValueError("Invalid model response for question generation.")
        return {
            "question_text": data["question_text"],
            "question_type": "open",
            "options": None,
        }

    use_mcq = len(completed_turns) % 2 == 0
    if use_mcq:
        prompt = f"""{profile_ctx}

{convo_ctx}

You are continuing a personality and fit assessment for a {biodata.get('target_role', 'candidate')}.
The candidate prefers {question_type} questions.

Generate the NEXT question as a multiple-choice question with 4 options. This should:
- Follow naturally from the conversation above
- Be one of these types: behavioral, situational, or cognitive
- Not repeat what was already asked
- Be relevant to the role but universally fair
- Include 4 distinct, meaningful options that reveal personality differences

Return JSON:
{{
  "question_text": "...",
  "options": [
    {{"id":"a","label":"..."}},
    {{"id":"b","label":"..."}},
    {{"id":"c","label":"..."}},
    {{"id":"d","label":"..."}}
  ]
}}"""
        raw = await invoke_ai(QUESTION_INSTRUCTION, prompt, enforce_json=True)
        data = _extract_json(raw)
        if not isinstance(data, dict) or not data.get("question_text"):
            raise ValueError("Invalid model response for MCQ generation.")
        options = data.get("options", [])
        if not isinstance(options, list) or len(options) != 4:
            raise ValueError("MCQ generation returned invalid options.")
        return {
            "question_text": data["question_text"],
            "question_type": "mcq",
            "options": options,
        }

    prompt = f"""{profile_ctx}

{convo_ctx}

You are continuing a personality and fit assessment for a {biodata.get('target_role', 'candidate')}.
The candidate prefers {question_type} questions.

Generate the NEXT question as an open-ended response question. This should:
- Follow naturally from the conversation above
- Reference earlier answers, dig deeper into something interesting, or explore a new dimension
- Be one of these types: behavioral, situational, or reflective
- Not repeat what was already asked
- Invite a thoughtful, multi-sentence response
- Be relevant to the role but universally fair

Return JSON: {{"question_text": "..."}}"""
    raw = await invoke_ai(QUESTION_INSTRUCTION, prompt, enforce_json=True)
    data = _extract_json(raw)
    if not isinstance(data, dict) or not data.get("question_text"):
        raise ValueError("Invalid model response for open question generation.")
    return {
        "question_text": data["question_text"],
        "question_type": "open",
        "options": None,
    }


async def generate_personality_summary(session: Dict[str, Any]) -> Dict[str, Any]:
    biodata = session["biodata"]
    completed_turns = [h for h in session["personality_and_fit"]["conversation_history"] if h.get("user_answer") is not None]
    convo_ctx = build_conversation_context(completed_turns)

    prompt = f"""{build_ai_safe_profile_context(biodata)}

{convo_ctx}

You have just completed a personality and fit assessment. Synthesize the candidate's profile.

Return JSON:
{{
  "ai_summary": "...",
  "core_traits": ["...","...","..."],
  "ideal_environment": "..."
}}"""
    raw = await invoke_ai(PERSONALITY_SUMMARY_INSTRUCTION, prompt, enforce_json=True)
    data = _extract_json(raw)
    if not isinstance(data, dict):
        raise ValueError("Invalid personality summary JSON.")
    return {
        "ai_summary": data.get("ai_summary", ""),
        "core_traits": data.get("core_traits", []),
        "ideal_environment": data.get("ideal_environment", ""),
    }


async def generate_github_technical_footprint(session: Dict[str, Any], github_username: str, oauth_token: Optional[str]) -> Dict[str, Any]:
    biodata = session["biodata"]
    repos = await fetch_github_context(github_username, oauth_token)

    prompt = f"""{build_ai_safe_profile_context(biodata)}

GitHub repositories:
{json.dumps(repos, indent=2, ensure_ascii=False)}

Analyze these repositories and produce a technical footprint.

Return JSON:
{{
  "ai_summary": "...",
  "role_alignment_score": 0,
  "top_skills": ["..."],
  "highlighted_projects": [
    {{
      "name": "...",
      "description_for_reviewer": "...",
      "complexity_rating": "...",
      "github_url": "..."
    }}
  ]
}}"""
    raw = await invoke_ai(GITHUB_ANALYSIS_INSTRUCTION, prompt, enforce_json=True)
    data = _extract_json(raw)
    if not isinstance(data, dict):
        raise ValueError("Invalid GitHub analysis JSON.")

    top_skills = data.get("top_skills", [])
    highlighted_projects = data.get("highlighted_projects", [])

    # Keep the public schema exactly the same, but populate it via AI.
    return {
        "ai_summary": data.get("ai_summary", ""),
        "role_alignment_score": data.get("role_alignment_score", 0),
        "top_skills": top_skills if isinstance(top_skills, list) else [],
        "highlighted_projects": highlighted_projects if isinstance(highlighted_projects, list) else [],
    }


async def generate_overall_evaluation(session: Dict[str, Any]) -> Dict[str, Any]:
    biodata = session["biodata"]
    personality = session["personality_and_fit"]
    technical = session["technical_footprint"]
    completed_turns = [h for h in personality["conversation_history"] if h.get("user_answer") is not None]
    convo_ctx = build_conversation_context(completed_turns)

    prompt = f"""{build_ai_safe_profile_context(biodata)}

Conversation:
{convo_ctx}

Personality summary:
{json.dumps(personality, indent=2, ensure_ascii=False)}

Technical footprint:
{json.dumps(technical, indent=2, ensure_ascii=False)}

You are producing a final holistic evaluation. Rate 0-5 stars based on the strength of the profile evidence,
trajectory, communication, role fit, and technical depth. Do not infer or adjust the score based on age or any protected characteristic.
Lack of evidence is not evidence of weakness.

Return JSON:
{{
  "star_rating": 0.0,
  "rating_reasoning": "...",
  "age_context_note": "..."
}}"""
    raw = await invoke_ai(OVERALL_EVALUATION_INSTRUCTION, prompt, enforce_json=True)
    data = _extract_json(raw)
    if not isinstance(data, dict):
        raise ValueError("Invalid overall evaluation JSON.")
    return {
        "star_rating": data.get("star_rating"),
        "rating_reasoning": data.get("rating_reasoning", ""),
        "age_context_note": data.get("age_context_note") or "Protected attributes were excluded from scoring.",
    }


def _append_pending_initial_question(session: Dict[str, Any]) -> None:
    pending = session.pop("_pending_initial_question", None)
    if pending:
        session["personality_and_fit"]["conversation_history"].append(
            {
                "question_id": pending["question_id"],
                "question_text": pending["question_text"],
                "question_type": pending["question_type"],
                "options": pending["options"],
                "user_answer": None,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@app.post("/api/v1/sessions", status_code=status.HTTP_201_CREATED)
async def start_session(payload: StartSessionRequest):
    session_id = str(uuid.uuid4())
    session_state = initial_session_state(session_id, payload)
    save_session_atomic(session_id, session_state)

    pending = session_state["_pending_initial_question"]
    return {
        "session_id": session_id,
        "status": "initialized",
        "next_question": pending["question_text"],
        "question_id": pending["question_id"],
        "question_type": pending["question_type"],
        "options": pending["options"],
    }


@app.get("/api/v1/sessions/{session_id}")
async def recover_session(session_id: str):
    return load_session(session_id)


@app.patch("/api/v1/sessions/{session_id}/profile")
async def update_profile(session_id: str, payload: FullProfileData):
    session = load_session(session_id)
    incoming_data = payload.model_dump(exclude_unset=True)
    for key, value in incoming_data.items():
        session["biodata"][key] = value
    save_session_atomic(session_id, session)
    return {"status": "success", "current_biodata": session["biodata"]}


@app.post("/api/v1/sessions/{session_id}/assessment/answer")
async def submit_answer(session_id: str, payload: AnswerSubmission):
    session = load_session(session_id)
    _append_pending_initial_question(session)

    history = session["personality_and_fit"]["conversation_history"]
    current_step = next((q for q in history if q["question_id"] == payload.question_id), None)
    if not current_step:
        raise HTTPException(status_code=400, detail="Question not found.")

    current_step["user_answer"] = payload.answer_text
    if payload.selected_option:
        current_step["selected_option"] = payload.selected_option

    # First answer is the preference selector. The next question is AI-generated.
    if payload.question_id == "q_pref":
        session["preferences"]["question_type"] = payload.selected_option or payload.answer_text
        q_type = session["preferences"]["question_type"] or "mixed"

        try:
            next_q = await generate_next_question(session, q_type, first_substantive=True)
        except Exception as e:
            logger.exception("AI failed for first substantive question: %s", e)
            next_q = {
                "question_text": f"Tell me about a project you're proud of that relates to {session['biodata'].get('target_role', 'this role')}. What made it challenging and what did you learn?",
                "question_type": "open",
                "options": None,
            }

        history.append(
            {
                "question_id": "q_1",
                "question_text": next_q["question_text"],
                "question_type": next_q["question_type"],
                "options": next_q.get("options"),
                "user_answer": None,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
        save_session_atomic(session_id, session)
        response = {
            "session_id": session_id,
            "stage": "running",
            "next_question": next_q["question_text"],
            "question_id": "q_1",
            "question_type": next_q["question_type"],
        }
        if next_q.get("options"):
            response["options"] = next_q["options"]
        return response

    # Keep the same assessment length: preference + up to 4 more questions total.
    if len(history) < 5:
        next_q_id = f"q_{len(history)}"
        q_type = session["preferences"].get("question_type", "mixed")

        try:
            next_q = await generate_next_question(session, q_type, first_substantive=False)
        except Exception as e:
            logger.exception("AI failed for follow-up question: %s", e)
            use_mcq = len([h for h in history if h.get("user_answer") is not None]) % 2 == 0
            if use_mcq:
                next_q = {
                    "question_text": "When facing a tight deadline on an important project, what is your go-to approach?",
                    "question_type": "mcq",
                    "options": [
                        {"id": "a", "label": "Break it into milestones and move steadily"},
                        {"id": "b", "label": "Jump in fast and adjust on the fly"},
                        {"id": "c", "label": "Analyze constraints and prioritize impact"},
                        {"id": "d", "label": "Rally the team and coordinate collaboration"},
                    ],
                }
            else:
                next_q = {
                    "question_text": "Looking back at what you've shared so far, what pattern do you see in how you approach problems? How has that evolved?",
                    "question_type": "open",
                    "options": None,
                }

        history.append(
            {
                "question_id": next_q_id,
                "question_text": next_q["question_text"],
                "question_type": next_q["question_type"],
                "options": next_q.get("options"),
                "user_answer": None,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
        save_session_atomic(session_id, session)
        response = {
            "session_id": session_id,
            "stage": "running",
            "next_question": next_q["question_text"],
            "question_id": next_q_id,
            "question_type": next_q["question_type"],
        }
        if next_q.get("options"):
            response["options"] = next_q["options"]
        return response

    # Assessment complete — generate personality summary.
    session["dossier_meta"]["status"] = "awaiting_technical_sync"
    try:
        summary = await generate_personality_summary(session)
        session["personality_and_fit"].update(summary)
    except Exception as e:
        logger.exception("AI personality summary failed: %s", e)

    save_session_atomic(session_id, session)
    return {"session_id": session_id, "stage": "completed", "message": "Assessment complete."}


@app.post("/api/v1/sessions/{session_id}/github-analysis")
async def analyze_github(session_id: str, payload: GitHubAnalysisRequest):
    session = load_session(session_id)

    try:
        technical_footprint = await generate_github_technical_footprint(
            session,
            payload.github_username,
            payload.oauth_token,
        )
        session["technical_footprint"].update(technical_footprint)
    except Exception as e:
        logger.exception("AI GitHub analysis failed: %s", e)
        raise HTTPException(status_code=500, detail="GitHub analysis failed.") from e

    # Final holistic evaluation uses AI only.
    try:
        eval_data = await generate_overall_evaluation(session)
        session["overall_evaluation"]["star_rating"] = eval_data.get("star_rating")
        session["overall_evaluation"]["rating_reasoning"] = eval_data.get("rating_reasoning", "")
        session["overall_evaluation"]["age_context_note"] = eval_data.get("age_context_note", "")
    except Exception as e:
        logger.exception("AI scoring failed: %s", e)
        session["overall_evaluation"]["star_rating"] = None
        session["overall_evaluation"]["rating_reasoning"] = ""
        session["overall_evaluation"]["age_context_note"] = "Protected attributes were excluded from scoring."

    session["dossier_meta"]["status"] = "ready_for_review"
    save_session_atomic(session_id, session)
    return {"status": "success", "evaluation": session["overall_evaluation"]}


@app.patch("/api/v1/sessions/{session_id}/final-additions")
async def write_final_additions(session_id: str, payload: CandidateAdditions):
    session = load_session(session_id)
    if payload.personal_note:
        session["candidate_additions"]["personal_note"] = payload.personal_note
    if payload.portfolio_links:
        session["candidate_additions"]["portfolio_links"] = [str(url) for url in payload.portfolio_links]
    save_session_atomic(session_id, session)
    return {"status": "updated"}


@app.get("/api/v1/recruiter/candidates")
async def list_candidates():
    candidates = []
    if not os.path.exists(DATA_DIR):
        return candidates
    
    for filename in os.listdir(DATA_DIR):
        if filename.startswith("session_") and filename.endswith(".json"):
            try:
                with open(os.path.join(DATA_DIR, filename), "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("dossier_meta", {}).get("status") == "ready_for_review":
                        candidates.append({
                            "session_id": data["dossier_meta"]["session_id"],
                            "full_name": data["biodata"].get("full_name"),
                            "email": data["biodata"].get("email"),
                            "target_role": data["biodata"].get("target_role"),
                            "star_rating": data.get("overall_evaluation", {}).get("star_rating"),
                            "status": data["dossier_meta"]["status"]
                        })
            except Exception as e:
                logger.error(f"Error reading session file {filename}: {e}")
                continue
    return candidates


@app.get("/api/v1/recruiter/candidates/{session_id}")
async def get_candidate_detail(session_id: str):
    return load_session(session_id)


# @app.get("/")
# async def main():
#     return JSONResponse({"service": "Recruiter!", "status": "ok"})


# Only mount assets if the folder exists, so the app doesn't crash in fresh setups.
if os.path.isdir("assets"):
    app.mount("/assets", StaticFiles(directory="assets"), name="assets")

@app.get("/")
async def main():
    return FileResponse("assets/index.html")

@app.get("/app.js")
async def main():
    return FileResponse("assets/app.js")

@app.get("/styles.css")
async def main():
    return FileResponse("assets/styles.css")

@app.get("/recruite")
async def main():
    return FileResponse("assets/recruiter.html")
