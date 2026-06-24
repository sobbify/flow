# flow

**flow** is an AI-driven recruitment orchestrator designed to streamline the candidate assessment process. It features a multi-step applicant flow, automated GitHub profile analysis, and a recruiter dashboard for reviewing and downloading candidate data.

## Features

### Candidate Flow
- **AI-Driven Assessment**: Dynamic, conversational interview questions generated based on the candidate's target role and preferences.
- **GitHub Integration**: Automated analysis of public repositories to estimate technical depth and role alignment.
- **Profile Management**: Partial-save capable profile drafting with auto-save functionality.
- **Holistic Evaluation**: AI-generated summaries and star ratings based on personality, technical footprint, and conversation history.

### Recruiter Dashboard
- **Candidate Overview**: A dedicated interface to see all candidates who have completed their assessment and are "Ready for Review".
- **Star Ratings**: Quick visual indicator of candidate strength based on AI evaluation.
- **Data Export**: Download full candidate dossiers in JSON format for further processing or archival.

## Tech Stack

- **Backend**: FastAPI (Python 3.14)
- **AI Engine**: Google Gemini API
- **Frontend**: Vanilla JS, HTML5, CSS3 (Static Assets)
- **Database**: File-based session persistence (JSON)

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/sobmachine/flow.git
   cd flow
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install email-validator
   ```

3. **Run the server**:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

## Project Structure

- `main.py`: FastAPI backend with AI orchestration and session management.
- `assets/`: Frontend static files.
  - `index.html`: Main candidate application portal.
  - `recruiter.html`: Recruiter dashboard for reviewing candidates.
  - `app.js`: Frontend logic and API integration.
  - `styles.css`: Global styles and theme tokens.
- `session_store/`: Directory where candidate sessions are persisted as JSON files.

## API Endpoints

### Candidate APIs
- `POST /api/v1/sessions`: Initialize a new application session.
- `PATCH /api/v1/sessions/{id}/profile`: Update candidate biodata.
- `POST /api/v1/sessions/{id}/assessment/answer`: Submit assessment answers.
- `POST /api/v1/sessions/{id}/github-analysis`: Trigger AI analysis of GitHub profile.

### Recruiter APIs
- `GET /api/v1/recruiter/candidates`: List all candidates ready for review.
- `GET /api/v1/recruiter/candidates/{id}`: Get full details for a specific candidate.

## The Team
So, we had divided our team into three parts:
- Ideation
- UI/UX
- Development

Most members took part in more than a single team to effectively divide workload

Here follows the team members and what parts they took:
- *Avirbhav*:
- *Hardik*: Part of the UI/UX and development team. Worked on the base prototype (MVP) and also helped Shagun and Shaurya in designing the pages.
- *Sahil*: Part of the ideation and development team. Worked on the base prototype (MVP) and also did market research for the following consumer space.
- *Shaurya*: Part of the ideation and UI/UX team. Worked on the final touchups along with QoL changes.
- *Shagun*: Part of the ideation and UI/UX team. Worked on the page design along with user friction reduction.
