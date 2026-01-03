# Explain My Repo

Explain My Repo is a web tool that converts any GitHub repository link into a clear, human-readable explanation.  
It helps recruiters, interviewers, and developers understand a project in under a minute—without digging through code.

🌐 Live Website: https://explain-my-repo.vercel.app/  
📦 GitHub Repo: https://github.com/Alpha-778/explain_my_repo

---

## What does it do?

Paste a GitHub repository URL and get:
- A plain-English project summary
- The tech stack used
- The type of project (web app, API, tool, etc.)
- A quick architectural overview

Built to answer the question:  
**“What does this repo actually do?”**

---

## Why this exists

Reading unfamiliar repositories takes time, especially during hiring or collaboration.  
This project removes that friction by summarizing a repo in a way that’s understandable even to non-developers.

---

## Features

- Works with public GitHub repositories
- Generates recruiter-friendly explanations
- No login required
- Fast and simple UI
- Deployed and publicly accessible

---

## How it works (high level)

1. User submits a GitHub repository URL
2. Repository structure and metadata are fetched via GitHub APIs
3. The data is analyzed and summarized using AI
4. A clean explanation is displayed on the frontend

---

## Tech Stack

- **Backend:** Python (Flask)
- **Frontend:** HTML, CSS, JavaScript
- **APIs:** GitHub API + AI summarization
- **Deployment:** Vercel

---

## Project Structure

```text
explain_my_repo/
├── app.py              # Main backend application
├── templates/          # HTML templates
├── static/             # CSS and JS files
├── requirements.txt    # Python dependencies
└── README.md
