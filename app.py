import os
import re
import base64
import requests
from flask import Flask, render_template, request
from dotenv import load_dotenv
import json

load_dotenv()

app = Flask(__name__)

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')

IGNORE_FOLDERS = {
    'node_modules', 'venv', '.git', 'dist', 'build', 
    '__pycache__', '.venv', 'env', '.env', '.idea', 
    '.vscode', 'vendor', 'target', '.gradle', 'bin', 'obj'
}

DEPENDENCY_FILES = [
    'requirements.txt', 'pyproject.toml', 'setup.py', 'Pipfile',
    'package.json', 'package-lock.json', 'yarn.lock',
    'pom.xml', 'build.gradle', 'build.gradle.kts',
    'go.mod', 'go.sum',
    'Cargo.toml', 'Gemfile', 'composer.json',
    'Makefile', 'Dockerfile', 'docker-compose.yml', 'docker-compose.yaml'
]


def get_github_headers():
    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'ExplainMyRepo/1.0'
    }
    
    if GITHUB_TOKEN:
        headers['Authorization'] = f'token {GITHUB_TOKEN}'
    
    return headers


def check_rate_limit():
    try:
        response = requests.get(
            'https://api.github.com/rate_limit',
            headers=get_github_headers(),
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            core = data.get('resources', {}).get('core', {})
            return {
                'limit': core.get('limit', 0),
                'remaining': core.get('remaining', 0),
                'reset_time': core.get('reset', 0)
            }
    except Exception:
        pass
    return None


def extract_repo_info(github_url):
    github_url = github_url.strip().rstrip('/')
    
    patterns = [
        r'(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/\s?#]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, github_url)
        if match:
            owner = match.group(1)
            repo = match.group(2).replace('.git', '')
            return owner, repo
    
    return None, None


def fetch_readme(owner, repo, headers):
    readme_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    
    try:
        response = requests.get(readme_url, headers=headers, timeout=10)
        if response.status_code == 200:
            readme_data = response.json()
            content = readme_data.get('content', '')
            encoding = readme_data.get('encoding', 'base64')
            
            if encoding == 'base64' and content:
                decoded = base64.b64decode(content).decode('utf-8', errors='ignore')
                return decoded[:8000] if len(decoded) > 8000 else decoded
        return None
    except Exception:
        return None


def fetch_repo_structure(owner, repo, headers):
    contents_url = f"https://api.github.com/repos/{owner}/{repo}/contents"
    structure = []
    
    try:
        response = requests.get(contents_url, headers=headers, timeout=10)
        if response.status_code == 200:
            contents = response.json()
            for item in contents:
                name = item.get('name', '')
                item_type = item.get('type', '')
                
                if name.lower() in {f.lower() for f in IGNORE_FOLDERS}:
                    continue
                
                structure.append({
                    'name': name,
                    'type': item_type,
                    'path': item.get('path', name)
                })
            
            structure.sort(key=lambda x: (0 if x['type'] == 'dir' else 1, x['name'].lower()))
        
        return structure
    except Exception:
        return []


def fetch_dependency_files(owner, repo, headers, structure):
    dependencies = {}
    
    for item in structure:
        if item['type'] == 'file' and item['name'] in DEPENDENCY_FILES:
            for branch in ['main', 'master']:
                file_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{item['path']}"
                try:
                    response = requests.get(file_url, timeout=10)
                    if response.status_code == 200:
                        content = response.text
                        dependencies[item['name']] = content[:4000] if len(content) > 4000 else content
                        break
                except Exception:
                    continue
    
    return dependencies


def fetch_github_data(owner, repo):
    headers = get_github_headers()
    
    repo_url = f"https://api.github.com/repos/{owner}/{repo}"
    
    try:
        response = requests.get(repo_url, headers=headers, timeout=10)
        
        remaining = response.headers.get('X-RateLimit-Remaining', 'unknown')
        limit = response.headers.get('X-RateLimit-Limit', 'unknown')
        
        if response.status_code == 404:
            return None, f"Repository '{owner}/{repo}' not found. Make sure it exists and is public."
        
        elif response.status_code == 403:
            reset_time = response.headers.get('X-RateLimit-Reset', '')
            if remaining == '0':
                error_msg = "GitHub API rate limit exceeded.\n\n"
                if not GITHUB_TOKEN:
                    error_msg += "💡 TIP: Add a GitHub token to your .env file to get 5000 requests/hour instead of 60.\n"
                    error_msg += "Get one at: https://github.com/settings/tokens"
                else:
                    error_msg += "Please wait a few minutes and try again."
                return None, error_msg
            else:
                return None, "Access forbidden. The repository might be private."
        
        elif response.status_code != 200:
            return None, f"GitHub API error (Status: {response.status_code})"
        
        repo_info = response.json()
        
    except requests.exceptions.Timeout:
        return None, "Request timed out. Please try again."
    except requests.exceptions.RequestException as e:
        return None, f"Network error: {str(e)}"
    
    readme = fetch_readme(owner, repo, headers)
    structure = fetch_repo_structure(owner, repo, headers)
    dependencies = fetch_dependency_files(owner, repo, headers, structure)
    
    languages = {}
    try:
        lang_url = f"https://api.github.com/repos/{owner}/{repo}/languages"
        lang_response = requests.get(lang_url, headers=headers, timeout=10)
        if lang_response.status_code == 200:
            languages = lang_response.json()
    except Exception:
        pass

    return {
        'readme': readme,
        'structure': structure,
        'dependencies': dependencies,
        'languages_stats': languages,
        'description': repo_info.get('description', ''),
        'language': repo_info.get('language', ''),
        'topics': repo_info.get('topics', []),
        'stars': repo_info.get('stargazers_count', 0),
        'forks': repo_info.get('forks_count', 0)
    }, None


def call_gemini_api(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={GEMINI_API_KEY}"
    
    headers = {
        'Content-Type': 'application/json'
    }
    
    data = {
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 2000
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            if 'candidates' in result and len(result['candidates']) > 0:
                candidate = result['candidates'][0]
                if 'content' in candidate and 'parts' in candidate['content']:
                    parts = candidate['content']['parts']
                    if len(parts) > 0 and 'text' in parts[0]:
                        return parts[0]['text'], None
            return None, "Unexpected response format from Gemini API"
        else:
            error_msg = response.json().get('error', {}).get('message', 'Unknown error')
            return None, f"Gemini API error: {error_msg}"
    
    except requests.exceptions.Timeout:
        return None, "Gemini API request timed out. Please try again."
    except requests.exceptions.RequestException as e:
        return None, f"Network error calling Gemini API: {str(e)}"
    except Exception as e:
        return None, f"Error processing Gemini response: {str(e)}"


def generate_analysis(repo_data, owner, repo):
    
    structure_text = '\n'.join([
        f"  {'📁' if item['type'] == 'dir' else '📄'} {item['name']}"
        for item in repo_data.get('structure', [])
    ]) or 'No structure data available'
    
    deps_text = ''
    for filename, content in repo_data.get('dependencies', {}).items():
        deps_text += f"\n--- {filename} ---\n{content}\n"
    
    if not deps_text:
        deps_text = 'No dependency files found'
    
    prompt = f"""You are an expert software analyst helping recruiters and developers understand GitHub projects.
Analyze this repository and provide a clear, accurate analysis in JSON format.

=== REPOSITORY INFO ===
Repository: {owner}/{repo}
Description: {repo_data.get('description') or 'Not provided'}
Primary Language: {repo_data.get('language') or 'Not specified'}
Topics/Tags: {', '.join(repo_data.get('topics', [])) or 'None'}
Stars: {repo_data.get('stars', 0)} | Forks: {repo_data.get('forks', 0)}

=== README CONTENT ===
{repo_data.get('readme') or 'No README found'}

=== REPOSITORY STRUCTURE ===
{structure_text}

=== DEPENDENCY FILES ===
{deps_text}

=== STRICT INSTRUCTIONS ===
1. Analyze the code structure and dependencies to understand the architecture.
2. Output valid JSON ONLY. No markdown formatting, no code blocks around it.
3. The JSON must have these exact keys:
   - "tech_stack": list of strings (frameworks, libs, tools used)
   - "project_type": string (e.g., "Web App", "API", "Library")
   - "architecture_mermaid": string (Mermaid.js graph TD syntax describing the architecture)
   - "architecture_description": string (Brief text explanation of architecture)
   - "what_it_does": string (Main functionality)
   - "recruiter_summary": string (Simple non-technical summary < 100 words)

Example of architecture_mermaid:
    "graph TD; Client-->LoadBalancer; LoadBalancer-->Server1; LoadBalancer-->Server2; Server1-->DB; Server2-->DB;"
    
    === STRICT MERMAID RULES ===
    1. Quote ALL node labels using double quotes: e.g. id["Label Text"]
    2. Remove ALL markdown formatting from labels (no bold, italics, code ticks).
    3. Use only valid arrows: -->, ==>, -.->, --o
    4. Remove or escape special characters in labels.
    5. Do NOT use markdown backticks in the mermaid string.
    6. Ensure the graph is "graph TD" or "graph LR" only.
    7. No emojis in labels.
    """

    return call_gemini_api(prompt)


def parse_analysis(analysis_text):
    try:
        cleaned_text = analysis_text.strip()
        if cleaned_text.startswith('```json'):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.startswith('```'):
            cleaned_text = cleaned_text[3:]
        if cleaned_text.endswith('```'):
            cleaned_text = cleaned_text[:-3]
        
        data = json.loads(cleaned_text.strip())
        
        default_keys = [
            'tech_stack', 'project_type', 'architecture_mermaid', 
            'architecture_description', 'what_it_does', 'recruiter_summary'
        ]
        
        for key in default_keys:
            if key not in data:
                if key == 'architecture_mermaid':
                    data[key] = ""
                else:
                    data[key] = "Not available"

        if 'architecture_mermaid' in data:
            mermaid_code = data['architecture_mermaid']
            mermaid_code = mermaid_code.replace('```mermaid', '').replace('```', '')
            mermaid_code = mermaid_code.strip()
            
            if mermaid_code and not mermaid_code.startswith('graph'):
                mermaid_code = 'graph TD;\n' + mermaid_code
                
            data['architecture_mermaid'] = mermaid_code
            
            if data['architecture_mermaid'].lower() == 'not available':
                data['architecture_mermaid'] = ""
                
        if isinstance(data['tech_stack'], list):
            data['tech_stack'] = ', '.join(data['tech_stack'])
            
        return data
        
    except json.JSONDecodeError:
        return {
            'tech_stack': 'Error parsing analysis',
            'project_type': 'Error parsing analysis',
            'architecture_mermaid': '',
            'architecture_description': 'Error parsing analysis',
            'what_it_does': 'Error parsing analysis',
            'recruiter_summary': 'Error parsing analysis: ' + analysis_text[:100] + '...'
        }


@app.route('/')
def index():
    rate_info = check_rate_limit()
    show_warning = False
    if rate_info and rate_info['remaining'] < 10 and not GITHUB_TOKEN:
        show_warning = True
    return render_template('index.html', show_rate_warning=show_warning, has_token=bool(GITHUB_TOKEN))


@app.route('/analyze', methods=['POST'])
def analyze():
    github_url = request.form.get('github_url', '').strip()
    
    if not github_url:
        return render_template('error.html', 
                             error="Please enter a GitHub repository URL.",
                             error_type="validation")
    
    owner, repo = extract_repo_info(github_url)
    
    if not owner or not repo:
        return render_template('error.html',
                             error="Invalid GitHub URL format. Please use a URL like: https://github.com/username/repository",
                             error_type="validation")
    
    repo_data, fetch_error = fetch_github_data(owner, repo)
    
    if fetch_error:
        return render_template('error.html',
                             error=fetch_error,
                             error_type="github")
    
    analysis_text, gemini_error = generate_analysis(repo_data, owner, repo)
    
    if gemini_error:
        return render_template('error.html',
                             error=gemini_error,
                             error_type="gemini")
    
    sections = parse_analysis(analysis_text)
    
    return render_template('results.html',
                         owner=owner,
                         repo=repo,
                         github_url=f"https://github.com/{owner}/{repo}",
                         sections=sections,
                         repo_data=repo_data)


@app.route('/rate-limit')
def rate_limit():
    rate_info = check_rate_limit()
    return {
        'rate_limit': rate_info,
        'has_token': bool(GITHUB_TOKEN)
    }


@app.route('/health')
def health():
    return {'status': 'healthy'}


@app.errorhandler(404)
def not_found(e):
    return render_template('error.html',
                         error="Page not found.",
                         error_type="404"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('error.html',
                         error="Internal server error. Please try again.",
                         error_type="500"), 500


if __name__ == '__main__':
    
    rate_info = check_rate_limit()
    if rate_info:
        print(f"Github Token Rate Limit: {rate_info['remaining']}/{rate_info['limit']} remaining")
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)


