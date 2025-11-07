<div align="center" style="border: none; padding: 0; margin: 0;">
  <img src="image/logo/thelogo.png" alt="Matplobbot Logo" width="400" style="border: none; outline: none;">
  <h1>Matplobbot & Stats Dashboard</h1>
  <strong>A comprehensive solution: An Aiogram 3 Telegram bot for advanced code interaction and a FastAPI dashboard for real-time analytics.</strong>
  <br>
  </br>
  <p align="center">
    <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker">
    <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
    <img src="https://img.shields.io/badge/Aiogram-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white" alt="Aiogram">
    <img src="https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL">
    <img src="https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black" alt="JavaScript">
    <img src="https://img.shields.io/badge/Pandoc-5A5A5A?style=for-the-badge&logo=pandoc&logoColor=white" alt="Pandoc">
    <img src="https://img.shields.io/badge/LaTeX-008080?style=for-the-badge&logo=latex&logoColor=white" alt="LaTeX">
    <img src ="https://img.shields.io/badge/Tailscale-000000?style=for-the-badge&logo=tailscale&logoColor=white">
    <img src="https://img.shields.io/badge/Jenkins-D24939?style=for-the-badge&logo=jenkins&logoColor=white">
    <img src="https://img.shields.io/badge/Ubuntu-E95420?style=for-the-badge&logo=ubuntu&logoColor=white">
    <img src="https://img.shields.io/badge/markdown-%23000000.svg?style=for-the-badge&logo=markdown&logoColor=white" alt="Markdown">
    <img src="https://img.shields.io/badge/Pydantic-E92063?style=for-the-badge&logo=Pydantic&logoColor=white" alt="Pydantic">
    <img src="https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=github-actions&logoColor=white" alt="GithubActions">
    <img src="https://img.shields.io/badge/redis-%23DD0031.svg?&style=for-the-badge&logo=redis&logoColor=white" alt="Redis">
  </p>
  <h2>Reach it on telegram</h2>
  <p align="center">
  <a href="https://t.me/matplobbot"><img src="https://img.shields.io/badge/STABLE_TELEGRAM_BOT-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white" alt="telegram"></a>
  <a href="https://t.me/test_matplobbot"><img src="https://img.shields.io/badge/DEVELOPEMENT_Telegram_BOT-ff8800?style=for-the-badge&logo=telegram&logoColor=white" alt="telegram"></a>
  </p>
</div>



## 🚀 Project Overview

This project is a powerful, dual-component system designed for advanced interaction with programming content and real-time monitoring, all containerized with Docker for seamless deployment.

1.  **Matplobbot (Telegram Bot)**: The primary user-facing service. A sophisticated asynchronous bot built on `aiogram 3` that serves as an intelligent gateway to programming libraries and educational materials. It handles all user commands, interactions, and on-demand rendering. All user interactions are logged to a shared PostgreSQL database.
2.  **Scheduler Service**: A new, standalone asynchronous service responsible for all background and time-based tasks. Its primary role is to provide proactive daily schedule notifications to users, complete with intelligent change-detection to prevent spam.
3.  **Stats Dashboard (FastAPI Web App)**: A real-time monitoring dashboard powered by `FastAPI`. It features a clean, responsive frontend built with vanilla JavaScript and `Chart.js`. The dashboard provides deep insights into bot usage statistics by querying the shared PostgreSQL database and streams live log events directly from the bot's log file via WebSockets.

The entire ecosystem is orchestrated by Docker Compose, utilizing shared volumes for the database and logs, which ensures data consistency and perfect integration between the three services.

## ✨ Key Features

### 🤖 Telegram Bot

The bot provides a rich, interactive experience for developers, students, and researchers.

#### Content Interaction
-   **Library Browsing**: Interactively navigate the `matplobblib` library by modules and topics (`/matp_all`).
-   **GitHub Repository Browsing**: Explore user-configured GitHub repositories file by file (`/lec_all`).
-   **Full-Text Search**: Perform deep searches within the `matplobblib` source code (`/matp_search`) and across Markdown files in your linked GitHub repositories (`/lec_search`).

#### 🔬 Dynamic On-Demand Rendering
-   **LaTeX Rendering**: Convert LaTeX equations into crisp, high-quality PNG images using the `/latex` command. Results are cached in the database for instant retrieval on subsequent requests.
-   **Mermaid.js Rendering**: Transform Mermaid diagram syntax into PNG images via the `/mermaid` command, utilizing a headless Chrome instance managed by Puppeteer.

#### 📄 Advanced Markdown Processing
The bot features a sophisticated pipeline for displaying `.md` files from GitHub. It uses **Pandoc** augmented with **custom Lua and Python filters** to correctly process and render complex documents containing embedded LaTeX and Mermaid code.

| Display Mode | Description |
| :--- | :--- |
| 🖼 **Text + Images** | Renders the document directly into the chat, splitting it into a series of text messages and generated images for equations and diagrams. |
| 📄 **HTML File** | Generates a fully self-contained `.html` file, bundling all necessary CSS and JS. Mermaid diagrams are interactive. |
| ⚫ **MD File** | Sends the original, raw `.md` file without any processing. |

#### 📅 University Schedule Integration
The bot now integrates with the university's schedule API, offering a rich set of features for students and teachers.
-   **Multi-Entity Search**: Users can search for schedules by group, teacher, or auditorium.
-   **Interactive Calendar**: A full inline calendar keyboard allows users to easily select a specific date or navigate by month and year.
-   **Daily & Weekly Views**: Users can view the schedule for a single day or an entire week.
-   **Proactive Notifications**: Users can subscribe to a schedule (e.g., their group) and receive a push notification every day at a chosen time with the schedule for the next day.
-   **Intelligent Change Detection**: The scheduler backend constantly monitors for changes. If a lesson is added, cancelled, or modified, subscribed users receive an immediate notification with a human-readable "diff" of what changed.

##### Schedule pipe view:

<div align="center" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;">

  <!-- First Image -->
  <img src="image/notes/schedule_en_1.png" alt="Step 1: Search Interface" width="420" style="border: 2px solid #24292e; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.12); margin: 8px 0;">

  <!-- Custom Arrow (GitHub-safe) -->
  <div style="color: #0366d6; font-size: 28px; margin: 4px 0;">
    &#x25BC; <!-- Unicode: BLACK DOWN-POINTING TRIANGLE -->
  </div>

  <!-- Second Image -->
  <img src="image/notes/schedule_en_2.png" alt="Step 2: Schedule Results" width="420" style="border: 2px solid #24292e; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.12); margin: 8px 0;">

  <!-- Custom Arrow -->
  <div style="color: #0366d6; font-size: 28px; margin: 4px 0;">
    &#x25BC;
  </div>

  <!-- Third Image -->
  <img src="image/notes/schedule_en_3.png" alt="Step 3: Calendar View" width="420" style="border: 2px solid #24292e; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.12); margin: 8px 0;">

  <div style="color: #0366d6; font-size: 28px; margin: 4px 0;">
    &#x25BC;
  </div>

  <!-- Third Image -->
  <img src="image\notes\calendar_screenshot.png" alt="Step 3: Calendar View" width="420" style="border: 2px solid #24292e; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.12); margin: 8px 0;">

</div>

<!-- <div style="display: flex; flex-direction: column; align-items: center; gap: 25px; margin: 20px auto; max-width: 420px;">
  <img src="image\notes\schedule_en_1.png" alt="Interactive Calendar" width="400" style="border: 2px solid #3498db; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
  
  <div style="position: relative; width: 40px; height: 40px;">
    <div style="position: absolute; top: 0; left: 50%; transform: translateX(-50%); width: 2px; height: 40px; background: #3498db;"></div>
    <div style="position: absolute; bottom: 0; left: 50%; transform: translateX(-50%) translateY(50%) rotate(45deg); width: 12px; height: 12px; border-right: 2px solid #3498db; border-bottom: 2px solid #3498db;"></div>
  </div>
  
  <img src="image\notes\schedule_en_2.png" alt="Interactive Calendar" width="400" style="border: 2px solid #3498db; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
  
  <div style="position: relative; width: 40px; height: 40px;">
    <div style="position: absolute; top: 0; left: 50%; transform: translateX(-50%); width: 2px; height: 40px; background: #3498db;"></div>
    <div style="position: absolute; bottom: 0; left: 50%; transform: translateX(-50%) translateY(50%) rotate(45deg); width: 12px; height: 12px; border-right: 2px solid #3498db; border-bottom: 2px solid #3498db;"></div>
  </div>
  
  <img src="image\notes\schedule_en_3.png" alt="Interactive Calendar" width="400" style="border: 2px solid #3498db; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
    <div style="position: relative; width: 40px; height: 40px;">
    <div style="position: absolute; top: 0; left: 50%; transform: translateX(-50%); width: 2px; height: 40px; background: #3498db;"></div>
    <div style="position: absolute; bottom: 0; left: 50%; transform: translateX(-50%) translateY(50%) rotate(45deg); width: 12px; height: 12px; border-right: 2px solid #3498db; border-bottom: 2px solid #3498db;"></div>
  </div>
  
  <img src="image\notes\calendar_screenshot.png" alt="Interactive Calendar" width="400" style="border: 2px solid #3498db; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
</div> -->

#### ⚙️ Personalization & User Management
-   **Favorites (`/favorites`)**: Bookmark useful code examples from your searches for quick access later.
-   **Settings (`/settings`)**: A comprehensive inline menu allows users to:
    -   Toggle the display of code docstrings.
    -   Select their preferred Markdown display mode.
    -   Fine-tune LaTeX rendering quality (DPI and padding).
    -   Manage their personal list of GitHub repositories.

#### 👑 Administration
-   **Live Library Updates (`/update`)**: (Admin-only) Fetches the latest version of the `matplobblib` library from PyPI and dynamically reloads the module without bot downtime.
-   **Cache Management (`/clear_cache`)**: (Admin-only) Instantly purges all application caches, including in-memory `TTLCache` for API calls and the persistent LaTeX cache in the database.

### 📊 Web Dashboard

The dashboard provides a live, data-rich view of the bot's health and user engagement.

<div align="center">
  <img src="image/notes/Dashboard.png" alt="Dashboard Screenshot" width="800">
</div>

-   **Real-time Updates**: All statistical charts and counters update instantly via **WebSocket** connections, providing a true live monitoring experience.
-   **Rich Data Visualization**:
    -   Total user actions counter.
    -   Leaderboard of the most active users, complete with their Telegram avatars.
    -   Bar charts for the most frequently used commands and text messages.
    -   A pie chart visualizing the distribution of action types (e.g., command vs. callback query).
    -   A line chart illustrating user activity over time.
-   **Live Log Streaming**: A live feed of the `bot.log` file is streamed directly to the web UI, enabling real-time operational monitoring.
-   **Modern UI**: A clean, responsive interface with automatic **light and dark theme** support.
-   **Detailed User Profile Pages**: The dashboard is no longer just an aggregate view. Clicking on a user in the leaderboard navigates to a dedicated profile page showing their complete, paginated, sortable, and filterable action history.
-   **CSV Export**: A user's entire action history can be exported to a CSV file directly from their profile page.
-   **API for Deeper Analytics**: New API endpoints have been added to allow for deeper analysis, such as finding all users who have performed a specific action.

## 🛠️ Architecture & Tech Stack



The project is built on modern, asynchronous frameworks with a strong emphasis on modularity and separation of concerns.

| Category | Technology & Key Libraries |
| :--- | :--- |
| **Backend** | Python 3.11+ |
| **Bot Framework** | **Aiogram 3** (utilizing `Router` for modular handlers) |
| **Web Framework** | **FastAPI**, Uvicorn |
| **Database** | **PostgreSQL** (accessed asynchronously via `asyncpg`) |
| **Frontend** | HTML5, CSS3, Vanilla JavaScript, **Chart.js** |
| **Containerization** | **Docker, Docker Compose** |
| **Rendering Pipeline** | **Pandoc** with custom Lua & Python filters, **TeX Live**, dvipng, **Mermaid-CLI**, Puppeteer |
| **Key Libraries** | `aiohttp`, `cachetools`, `python-dotenv` |

### Architectural Highlights
-   **Shared Core Library**: All common code (database, services, i18n, Redis client) is encapsulated in a `matplobbot-shared` library. This library is versioned and published to PyPI automatically, serving as a single source of truth for all services in the ecosystem.
-   **Decoupled Services**: The project runs as three distinct services (Bot, API, Scheduler) in separate Docker containers. They communicate only through the shared PostgreSQL database and Redis cache, creating a robust, microservice-like architecture.
-   **Manager Pattern & Dependency Injection**: The bot's logic is cleanly organized into feature-specific "Manager" classes (`ScheduleManager`, `GitHubManager`, etc.). Dependencies (like the `RuzAPIClient`) are injected at startup, promoting modular and testable code.
-   **Asynchronous Everywhere**: From database calls (`asyncpg`) to external API requests (`aiohttp`), the entire stack is asynchronous to ensure high performance and scalability.
-   **Persistent Caching with Redis**: User-specific data and schedule information are now cached in Redis, providing persistence across bot restarts and significantly improving performance.

## ⚙️ Installation & Setup

The project is fully containerized, enabling a simple and reproducible setup.

### 1. Prerequisites
-   **Docker** and **Docker Compose** must be installed on your system.

### 2. Environment Variables

Create a `.env` file in the project's root directory. Fill it out using the template below.

```env
# Get this from @BotFather on Telegram
BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11

# Comma-separated list of Telegram User IDs for admin command access
ADMIN_USER_IDS=123456789,987654321

# GitHub Personal Access Token with 'repo' scope for reading repositories
# Required for /lec_search, /lec_all, and uploading rendered LaTeX images
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# --- PostgreSQL Credentials ---
POSTGRES_USER=user
POSTGRES_PASSWORD=password
POSTGRES_DB=matplobbot_db
POSTGRES_HOST=postgres # The service name in docker-compose
POSTGRES_PORT=5432
```

### 3. Running with Docker Compose

This is the recommended method for running the project.

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/Ackrome/matplobbot.git
    cd matplobbot
    ```

2.  **Ensure your `.env` file is created and configured** as described above.

3.  **Build and run the services in detached mode:**
    ```bash
    docker compose up --build -d
    ```

### 4. Accessing the Services

-   **Telegram Bot**: Will be active and available on Telegram.
-   **Web Dashboard**: Open `http://localhost:9583` in your browser.

### 5. Stopping the Services

-   To stop all running containers, execute:
    ```bash
    docker compose down
    ```
    -   Your database and log files will persist in named volumes. To remove all data, run `docker-compose down -v`.

## 📚 Bot Command Reference

| Command | Description | Usage |
| :--- | :--- | :--- |
| **General** | | |
| `/start` | Initializes the bot and displays the main command keyboard. | Send to begin or reset your session. |
| `/help` | Shows an interactive inline menu with descriptions of all available commands. | Send to get a quick overview of the bot's features. |
| `/cancel` | Aborts any ongoing operation or conversation state. | Use if you get stuck waiting for input or want to return to the main menu. |
| **University Schedule** | | |
| `/schedule` | Starts an interactive search for a schedule (by group, teacher, etc.). | Send the command to begin the search process. |
| `/myschedule` | Instantly displays today's schedule for your default (subscribed) group or teacher. | A one-click command for daily use. |
| **Content Browsing & Search** | | |
| `/matp_all` | Interactively browse the `matplobblib` library by modules and topics. | Send the command and navigate the library structure using inline buttons. |
| `/matp_search` | Performs a full-text search for code examples within `matplobblib`. | Send the command, then type your search query (e.g., "line plot"). |
| `/lec_all` | Interactively browse files in your configured GitHub repositories. | Send the command. If you have multiple repos, you'll be asked to choose one. |
| `/lec_search` | Performs a full-text search within `.md` files in a chosen GitHub repository. | Send the command, choose a repository, then enter your search query. |
| **Dynamic Rendering** | | |
| `/latex` | Renders a LaTeX formula into a high-quality PNG image. | Send the command, then provide the LaTeX code (e.g., `\frac{a}{b}`). |
| `/mermaid` | Renders a Mermaid.js diagram into a PNG image. | Send the command, then provide the Mermaid diagram code (e.g., `graph TD; A-->B;`). |
| **Personalization** | | |
| `/favorites` | View, manage, and access your saved favorite code examples. | Send the command to see your list. You can add items from search results or library browsing. |
| `/settings` | Access and modify your personal settings. | Configure docstring visibility, Markdown display format, LaTeX quality, and manage your GitHub repositories. |
| **Admin Commands** | | |
| `/update` | Updates the `matplobblib` library to the latest version from PyPI. | *(Admin-only)* Send the command to perform a live update. |
| `/clear_cache` | Clears all application caches (in-memory and database). | *(Admin-only)* Useful for forcing the bot to fetch fresh data. |

### On-boarding users
```mermaid
graph TD;
    subgraph "Start"
        A[User sends /start] --> B{Is onboarding_completed?};
    end

    B -- No --> C[Show Welcome & 'Next' button];
    B -- Yes --> Z[Show Regular Welcome];

    C --> D{User clicks 'Next'};
    D --> E[Show GitHub Feature];

    subgraph "GitHub Step"
        E --> F["'Add Repository' button (manage_repos)"];
        E --> H["'Next' button (onboarding_next)"];
        F --> G[User interacts with Repo Management];
        G --> H;
    end

    H --> I{User clicks 'Next'};
    I --> J[Show Library Feature & 'Next' button];
    J --> K{User clicks 'Next'};
    K --> L[Show Rendering Feature & 'Next' button];
    L --> M{User clicks 'Next'};
    M --> N[Show Schedule Feature & 'Next' button];
    N --> O{User clicks 'Next'};
    O --> P[Show Final Message & 'Finish' button];
    P --> Q{User clicks 'Finish'};
    Q --> R[Set onboarding_completed = true];
    R --> S[Show Main Menu Keyboard];

    style Z fill:#f9f,stroke:#333,stroke-width:2px;
    style S fill:#ccf,stroke:#333,stroke-width:2px;
```

### 🚀 CI/CD Pipeline

The project is built around a modern, secure, and fully automated CI/CD pipeline that handles everything from code validation to production deployment. This pipeline leverages a hybrid approach, using a self-hosted GitHub Runner to securely bridge the public cloud (GitHub) with a private deployment environment (Proxmox/Tailscale).

**Key Technologies:**
*   **Continuous Integration**: GitHub Actions
*   **Continuous Deployment**: Jenkins
*   **Containerization**: Docker & Docker Compose
*   **Secure Networking**: Tailscale


#### The Workflow

The entire process is event-driven and fully automated. It now includes automatic version bumping and publishing of the shared library before the application services are deployed.

```mermaid
graph TD
    subgraph "GitHub (Public Cloud)"
        A[Developer pushes to main] --> B{GitHub Actions: Auto-Version};
        B --> |Commit back to main| C{GitHub Actions: Publish};
        C --> |Pushes package| D[PyPI Repository];
        C --> E{Build & Push Images};
        E --> F[GitHub Container Registry];
    end

    subgraph "Your Proxmox Network (Private & Secure)"
        direction LR
        G(Self-Hosted Runner)
        H(Jenkins VM)
        I(Application VM)

        E -- "Triggers Deploy via Tailscale" --> H;
        H -- "Executes Deploy via SSH" --> I;
    end

    B -- "Assigns Job" --> G;

    subgraph "Deployment on Application VM"
        direction TB
        I --> J{1. Git Pull};
        J --> K{2. Jenkins creates .env};
        K --> L{3. Pull new images};
        L --> M{4. docker-compose up -d};
        M --> N[🚀 New version is live!];
    end
```

#### Step-by-Step Breakdown:

1.  **Commit & Push**: A developer pushes new code to the `main` branch.
2.  **Auto-Versioning**: A GitHub Actions job automatically runs `version_bumper.py`, increments the patch version, and pushes a version commit (e.g., `chore(release): version v0.5.1`) back to the `main` branch.
3.  **Publish Library**: Triggered by the new version commit, a second job builds the `matplobbot-shared` library and publishes the new version to **PyPI**.
4.  **Build & Push Images**: A third job waits for the library to be published. It then builds new Docker images for the `bot`, `api`, and `scheduler` services, installing the newly published library from PyPI. The images are tagged and pushed to GitHub Container Registry (GHCR).
5.  **Secure Trigger for CD**: Upon successful image push, the workflow triggers a job on the **self-hosted runner**, which securely sends a webhook to the Jenkins server over the private Tailscale network.
6.  **Deployment Orchestration**: The Jenkins pipeline takes over, connecting to the **Application VM** via SSH to:
    *   Pull the latest changes from the Git repository (to get the updated `docker-compose.prod.yml`).
    *   Securely create the `.env` file from Jenkins credentials.
    *   Execute the `deploy.sh` script.
7.  **Final Rollout**: The `deploy.sh` script pulls the new Docker images from GHCR and gracefully restarts all services using `docker compose up -d`.
