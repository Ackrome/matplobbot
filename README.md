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
</div>

---

## 🚀 Project Overview

This project is a powerful, dual-component system designed for advanced interaction with programming content and real-time monitoring, all containerized with Docker for seamless deployment.

1.  **Matplobbot (Telegram Bot)**: A sophisticated asynchronous bot built on `aiogram 3`. It serves as an intelligent gateway to programming libraries and educational materials. Its core features include interactive library browsing, full-text search, and a powerful on-demand rendering engine for LaTeX equations and Mermaid diagrams. All user interactions are meticulously logged to a shared SQLite database.

2.  **Stats Dashboard (FastAPI Web App)**: A real-time monitoring dashboard powered by `FastAPI`. It features a clean, responsive frontend built with vanilla JavaScript and `Chart.js`. The dashboard provides deep insights into bot usage statistics by querying the shared **PostgreSQL** database and streams live log events directly from the bot's log file via WebSockets.

The entire ecosystem is orchestrated by Docker Compose, utilizing shared volumes for the database and logs, which ensures data consistency and perfect integration between the two services.

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
  <img src="https://github.com/Ackrome/matplobbot/blob/main/image/notes/Dashboard.png" alt="Dashboard Screenshot" width="800">
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
-   **Decoupled Services**: The bot and the web dashboard run in separate Docker containers but communicate through a shared database and log volume, creating a robust, microservice-like architecture.
-   **Modular Handlers**: The bot's logic is cleanly organized into feature-specific modules (`admin`, `rendering`, `settings`, etc.), each with its own `aiogram.Router`.
-   **Service Layer**: Complex business logic, such as rendering documents and interacting with the GitHub API, is abstracted into a dedicated `services` package.
-   **Asynchronous Everywhere**: From database calls (`asyncpg`) to external API requests (`aiohttp`), the entire stack is asynchronous to ensure high performance and scalability.
-   **Intelligent Caching**: In-memory `TTLCache` is used extensively to cache GitHub API responses, reducing rate-limiting and speeding up user-facing operations.

## ⚙️ Installation & Setup

The project is fully containerized, enabling a simple and reproducible setup.

### 1. Prerequisites
-   **Docker** and **Docker Compose** must be installed on your system.

### 2. Environment Variables

Create a `.env` file in the project's root directory. Fill it out using the template below.

```env
# Get this from @BotFather on Telegram
BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11

# Your personal Telegram User ID for admin command access
ADMIN_USER_ID=123456789

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
graph TD
    subgraph "User's First Interaction"
        A[User sends /start] --> B{Is onboarding_completed == false?};
    end

    B -- Yes --> C[Onboarding Starts: Show Welcome Message & 'Next' button];
    B -- No --> Z[Show Regular Welcome Message];

    C --> D{User clicks 'Next'};
    D --> E[Show GitHub Feature & 'Add Repository' button];

    subgraph "Feature Interaction 1: GitHub"
        E --> F{User clicks 'Add Repository'};
        F --> G[User interacts with Repo Management];
        G --> H{User clicks 'Back to Tour'};
    end

    E --> H;

    H --> I[Show Library Feature & 'Next' button];
    I --> J[Show Rendering Feature & 'Try LaTeX' button];

    subgraph "Feature Interaction 2: Rendering"
        J --> K{User can try LaTeX};
    end

    J --> L{User clicks 'Next'};
    I --> L;

    L --> M[Show Final Message & 'Finish Tour' button]

    M --> N{User clicks 'Finish Tour'};
    N --> O[Set onboarding_completed = true];
    O --> P[Show Main Menu Keyboard];

    style Z fill:#f9f,stroke:#333,stroke-width:2px
    style P fill:#ccf,stroke:#333,stroke-width:2px
```

### 🚀 CI/CD Pipeline

The project is built around a modern, secure, and fully automated CI/CD pipeline that handles everything from code validation to production deployment. This pipeline leverages a hybrid approach, using a self-hosted GitHub Runner to securely bridge the public cloud (GitHub) with a private deployment environment (Proxmox/Tailscale).

**Key Technologies:**
*   **Continuous Integration**: GitHub Actions
*   **Continuous Deployment**: Jenkins
*   **Containerization**: Docker & Docker Compose
*   **Secure Networking**: Tailscale

#### The Workflow

The entire process is event-driven, starting with a simple `git push` and ending with the new version of the application running live, with no manual intervention required.

```mermaid
graph TD
    subgraph "GitHub (Public Cloud)"
        A[Developer pushes to main branch] --> B{GitHub Actions Trigger};
    end

    subgraph "Your Proxmox Network (Private & Secure)"
        direction LR
        C(Self-Hosted GitHub Runner VM)
        D(Jenkins VM)
        E(Application VM)

        C -- "Executes Job Locally" --> F{Test, Build & Push};
        F -- "Pushes images" --> G[GitHub Container Registry];
        F -- "Triggers Deploy via Tailscale IP" --> D;
        D -- "Executes Deploy via SSH" --> E;
    end
    
    B -- "Assigns Job" --> C;
    G -- "Images are pulled by App VM" --> E;

    subgraph "Deployment Steps on Application VM"
        direction TB
        E --> H{1. Jenkins creates .env file from secrets};
        H --> I{2. Pull new Docker images};
        I --> J{3. docker-compose up -d};
        J --> K[🚀 New version is live!];
    end
```

#### Step-by-Step Breakdown:

1.  **Commit & Push**: A developer pushes new code to the `main` branch on the GitHub repository.
2.  **Job Assignment**: GitHub Actions detects the push and assigns a new workflow job to the registered **self-hosted runner**.
3.  **CI on Self-Hosted Runner**: The runner, running on a dedicated VM within your private network, picks up the job. It performs the **Continuous Integration** steps locally:
    *   Checks out the source code.
    *   Sets up the Docker Buildx environment.
    *   Builds the `matplobbot-bot` and `matplobbot-api` Docker images.
    *   Pushes the newly tagged images to the GitHub Container Registry (GHCR).
4.  **Secure Trigger for CD**: Upon successful completion of the CI stage, a subsequent step in the same workflow on the self-hosted runner sends a secure webhook (`cURL` request) to the Jenkins server. This communication is safe because the runner and Jenkins are on the same private Tailscale network.
5.  **Deployment Orchestration**: Jenkins receives the webhook and triggers the `matplobbot-deploy` pipeline. This **Continuous Deployment** pipeline performs the final steps:
    *   It securely loads the application's production secrets (like `BOT_TOKEN`) from its encrypted credentials store.
    *   It connects to the dedicated **Application VM** via SSH.
    *   It dynamically writes the secrets into a `.env` file on the Application VM.
    *   It executes the `deploy.sh` script on the Application VM.
6.  **Final Rollout**: The `deploy.sh` script orchestrates the final rollout by:
    *   Pulling the new Docker images from GHCR.
    *   Running `docker-compose up -d` to gracefully restart the services with the updated images and configuration.
    *   Running `docker compose up -d` to gracefully restart the services with the updated images and configuration.