# flow

Flow is a responsive, AI-powered recruitment orchestration platform built to streamline candidate assessment and evaluation. Designed for both desktop and mobile devices, it guides applicants through a structured multi-step application process, automatically analyzes GitHub profiles to assess technical expertise, and provides recruiters with a centralized dashboard to review, manage, and download candidate data efficiently.

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
- **Avirbhav**: Member of the development and ideation team. Developed the homepage for the base prototype (MVP) and played a key role in integrating the backend with the frontend. He also collaborated closely with the development team to ensure successful project completion. He also took a part in presenting the prototype (MVP).
- **Hardik**: Member of the UI/UX and development team. Contributed to the development of the base prototype (MVP) and assisted Shagun and Shaurya in designing and refining the platform's pages.
- **Harshit**: Member of the UI/UX, development, and ideation team. Contributed to backend development and worked with the ideation team during the creation of the base prototype (MVP). He continued to manage and improve backend functionality while the rest of the team focused on frontend development. He also took a part in presenting the technical side of the prototype (MVP) and answered questions asked. He also prepared the [readme file](README.md) file of the project 
- **Sahil**: Member of the ideation and development team. Contributed to the development of the base prototype (MVP) and conducted market research to better understand the target consumer space and its needs.
- **Shagun**: Member of the ideation and UI/UX team. Led page design efforts and focused on reducing user friction to create a smoother and more intuitive user experience.
- **Shaurya**: Member of the ideation and UI/UX team. Worked on final design refinements, quality-of-life improvements, and overall user experience enhancements to polish the finished product.

Of these **six** students, **three**—Shaurya, Harshit, and Avirbhav—were responsible for prompt engineering across all stages of the applications, *with Harshit specifically developing the models’ backend system prompts*.
