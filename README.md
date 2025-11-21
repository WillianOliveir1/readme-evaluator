# README Evaluator

**README Evaluator** is an AI-powered tool designed to analyze and evaluate GitHub repository README files. It leverages the Google Gemini API to extract structured data based on a comprehensive taxonomy and generates a human-readable report, helping developers improve their project documentation.

## ❓ Why README Evaluator?

Documentation is often the first interaction a user has with a project. A poor README can turn away potential users and contributors. This tool provides:
-   **Automated Quality Assessment**: Objective evaluation against a strict schema.
-   **Structured Feedback**: Identifies missing sections (e.g., Installation, Usage, License).
-   **Actionable Improvements**: Suggests specific changes to enhance clarity and completeness.

## 🚀 Installation

### Prerequisites

-   **Python 3.10+**
-   **Node.js 18+** & npm
-   **Google Gemini API Key**

### Backend Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/WillianOliveir1/readme-evaluator.git
    cd readme-evaluator
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    # Windows
    python -m venv .venv
    .venv\Scripts\activate

    # Linux/Mac
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install --upgrade pip
    pip install -r backend/requirements.txt
    ```

### Frontend Setup

1.  **Navigate to the frontend directory:**
    ```bash
    cd frontend
    ```

2.  **Install dependencies:**
    ```bash
    npm install
    ```

## ⚙️ Configuration

Create a `.env` file in the root directory of the project. You can use the following template:

```env
# Required: Google Gemini API Key
GEMINI_API_KEY=your_gemini_api_key_here

# Optional: MongoDB Atlas Configuration (for saving evaluations)
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB=readme_evaluator
MONGODB_COLLECTION=evaluations
```

> **Note:** If MongoDB variables are not set, the application will default to local storage (saving JSON files in `data/processed/`).

## 💻 Usage

1.  **Start the Backend:**
    From the root directory (with virtual environment activated):
    ```bash
    python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
    ```

2.  **Start the Frontend:**
    From the `frontend` directory:
    ```bash
    npm run dev
    ```

3.  **Evaluate a Repository:**
    -   Open your browser and go to `http://localhost:3000`.
    -   Paste the URL of a public GitHub repository (e.g., `https://github.com/pandas-dev/pandas`).
    -   Click **"Evaluate README"**.
    -   View the real-time progress and the final generated report.

## 📅 Status & Roadmap

**Current Status:** Active Development (Beta).

**Roadmap:**
-   [x] Core extraction pipeline with Gemini.
-   [x] Streaming response (SSE) for real-time feedback.
-   [x] MongoDB integration for persistence.
-   [ ] Support for local LLMs (e.g., Ollama).
-   [ ] Batch processing for multiple repositories.
-   [ ] PDF export of reports.

## 👥 Authors

-   **Willian Oliveira** - *Initial work* - [WillianOliveir1](https://github.com/WillianOliveir1)

## 🤝 Contribution

Contributions are welcome! Please follow these steps:
1.  Fork the repository.
2.  Create a feature branch (`git checkout -b feature/AmazingFeature`).
3.  Commit your changes (`git commit -m 'Add some AmazingFeature'`).
4.  Push to the branch (`git push origin feature/AmazingFeature`).
5.  Open a Pull Request.

## 📄 License

This project is licensed under the MIT License.

## 📚 References

-   **FastAPI Documentation**: https://fastapi.tiangolo.com/
-   **Next.js Documentation**: https://nextjs.org/docs
-   **Google AI Studio**: https://aistudio.google.com/

