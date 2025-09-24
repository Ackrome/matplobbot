<div align="center">
  <img src="https://github.com/Ackrome/matplobbot/blob/main/image/notes/thelogo.png" alt="Matplobbot Logo" width="400">
  <h1>Matplobbot & Stats Dashboard</h1>
  <strong>A comprehensive solution: An Aiogram 3 Telegram bot for advanced code interaction and a FastAPI dashboard for real-time analytics.</strong>
</div>

---

## 🚀 Project Overview

This project is a system of two tightly integrated, Docker-deployed components:

1.  **Telegram Bot (`matplobbot`)**: An asynchronous bot built with `aiogram 3`. It provides users with access to code examples, remote code execution, rendering of LaTeX formulas and Mermaid diagrams, and much more. All user activities are logged into a shared SQLite database.
2.  **Stats Web Dashboard (`fastapi_stats_app`)**: A `FastAPI` application with a `Vanilla JS` and `Chart.js` frontend. It visualizes bot usage statistics in real-time and streams its logs via WebSockets.

Both services utilize shared Docker volumes for the database and log files, ensuring seamless data flow and consistent operation.

## ✨ Features

### 🤖 Telegram Bot

The bot offers a rich set of features for developers, students, and researchers.

#### Content Interaction
-   **Library Browsing**: Interactive navigation through `matplobblib` modules (`/matp_all`) and user-configured GitHub repositories (`/lec_all`).
-   **Full-Text Search**: Powerful search capabilities across `matplobblib` code (`/matp_search`) and Markdown notes in GitHub repositories (`/lec_search`).

#### Dynamic Rendering
-   **LaTeX Rendering**: Converts LaTeX formulas into high-quality PNG images via the `/latex` command.
-   **Mermaid.js Rendering**: Transforms Mermaid diagram syntax into PNG images using the `/mermaid` command.

#### Advanced Markdown Handling
The bot can display `.md` files from GitHub in multiple user-selectable formats, with full support for embedded LaTeX and Mermaid diagrams.

| Format | Description |
| :--- | :--- |
| 🌐 **Telegra.ph** | Publishes a clean, readable web article. LaTeX and Mermaid diagrams are automatically rendered and embedded. |
| 📄 **Text + Images** | Sends the content directly into the chat as a series of text messages and rendered formula images. |
| 📁 **HTML File** | Generates a self-contained `.html` file with all styles, rendered LaTeX, and interactive Mermaid diagrams. |
| 📁 **MD File** | Sends the original, raw `.md` file. |

#### Code Execution
-   **Remote Execution (`/execute`)**: Executes Python code in an isolated environment. The bot captures and returns:
    -   Standard output and errors.
    -   Generated image files (e.g., Matplotlib plots).
    -   Rich display outputs (Markdown, HTML) via `IPython.display` compatibility.

#### Personalization
-   ⭐ **Favorites (`/favorites`)**: Save and quickly access frequently used code examples.
-   ⚙️ **Settings (`/settings`)**: A comprehensive menu for user-specific preferences:
    -   Toggle docstring visibility for code examples.
    -   Select the preferred Markdown display mode.
    -   Adjust LaTeX rendering quality (DPI) and padding.
    -   Manage a personal list of GitHub repositories for browsing and searching.

#### Administration
-   **Live Updates (`/update`)**: Fetches the latest version of the `matplobblib` library.
-   **Cache Management (`/clear_cache`)**: Clears all application caches (in-memory and database) to ensure fresh data.

---

### 📊 Web Dashboard

The dashboard provides a live, insightful look into the bot's usage and health.

<div align="center">
  <img src="https://github.com/Ackrome/matplobbot/blob/main/image/notes/Dashboard.png" alt="Dashboard Screenshot" width="800">
</div>

-   **Real-time Updates**: All statistics on the page update instantly via **WebSockets** without requiring a page refresh.
-   **Data Visualization**:
    -   Total actions counter.
    -   Leaderboard of the most active users, complete with their Telegram avatars.
    -   Bar charts for popular commands and text messages.
    -   Pie chart showing the distribution of action types.
    -   Line chart illustrating user activity over time.
-   **Live Log Streaming**: A live feed of the `bot.log` file is streamed directly to the web interface, allowing for real-time monitoring of the bot's operations.
-   **Modern UI**: A clean, responsive interface with support for both **light and dark themes**.

---

## ⌨️ Bot Commands

Here is a detailed list of all commands available in the bot.

| Command | Description | Usage |
| :--- | :--- | :--- |
| **General** | | |
| `/start` | Initializes the bot and displays the main command keyboard. | Send the command to begin or reset your session. |
| `/help` | Shows an interactive menu with descriptions of all available commands. | Send the command to get a quick overview of the bot's features. |
| `/cancel` | Aborts any ongoing operation or conversation state. | Use this if you get stuck waiting for input or want to return to the main menu. |
| **Content Browsing & Search** | | |
| `/matp_all` | Interactively browse the `matplobblib` library by modules and topics. | Send the command and navigate the library structure using inline buttons. |
| `/matp_search` | Performs a full-text search for code examples within `matplobblib`. | Send the command, then type your search query (e.g., "line plot"). |
| `/lec_all` | Interactively browse files in your configured GitHub repositories. | Send the command. If you have multiple repos, you'll be asked to choose one. |
| `/lec_search` | Performs a full-text search within `.md` files in a chosen GitHub repository. | Send the command, choose a repository, then enter your search query. |
| **Dynamic Rendering** | | |
| `/latex` | Renders a LaTeX formula into a high-quality PNG image. | Send the command, then provide the LaTeX code (e.g., `\frac{a}{b}`). |
| `/mermaid` | Renders a Mermaid.js diagram into a PNG image. | Send the command, then provide the Mermaid diagram code (e.g., `graph TD; A-->B;`). |
| **Tools & Personalization** | | |
| `/execute` | Executes a Python code snippet in an isolated environment. | Send the command, then provide the Python code. The bot will return text output and any generated images. |
| `/favorites` | View, manage, and run your saved favorite code examples. | Send the command to see your list. You can add items from search results or library browsing. |
| `/settings` | Access and modify your personal settings. | Configure docstring visibility, Markdown display format, LaTeX quality, and manage your GitHub repositories. |
| **Admin Commands** | | |
| `/update` | Updates the `matplobblib` library to the latest version from PyPI. | *(Admin only)* Send the command to perform a live update. |
| `/clear_cache` | Clears all application caches (in-memory and database). | *(Admin only)* Useful for forcing the bot to fetch fresh data. |

---

## 🛠️ Tech Stack

| Category | Technology |
| :--- | :--- |
| **Backend** | Python 3.11+ |
| **Bot Framework** | Aiogram 3 |
| **Web Framework** | FastAPI, Uvicorn |
| **Database** | SQLite (via `aiosqlite`) |
| **Frontend** | HTML5, CSS3, Vanilla JavaScript, Chart.js |
| **Containerization** | Docker, Docker Compose |
| **Rendering** | **LaTeX**: TeX Live, dvipng <br> **Mermaid**: Mermaid-CLI, Puppeteer |
| **APIs** | Telegram Bot API, GitHub API, Telegra.ph API |
| **Libraries** | Matplotlib, `matplobblib`, `cachetools`, `aiohttp` |

---

## ⚙️ Installation and Setup

The project is fully containerized, making setup straightforward with Docker.

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

# (Optional) Telegra.ph access token. If not provided, a new account
# will be created on the first run and the token will be logged.
TELEGRAPH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 3. Running with Docker Compose

This is the recommended method for running the project.

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/Ackrome/matplobbot.git
    cd matplobbot
    ```

2.  **Ensure your `.env` file is created and configured** as described above.

3.  **Build and run the services:**
    ```bash
    docker-compose up --build -d
    ```

### 4. Accessing the Services

-   **Telegram Bot**: Will be active and available on Telegram.
-   **Web Dashboard**: Open `http://localhost:9583` in your browser.

### 5. Stopping the Services

To stop all running containers, execute:
```bash
docker-compose down
```

Your database and log files will persist thanks to the named volumes (`bot_db_data`, `bot_logs`). To remove all data, run `docker-compose down -v`.